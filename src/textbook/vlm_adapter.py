"""Vision-Language Model adapter for complex-page extraction.

Renders a PDF page to a PNG, sends it to GPT-4o-mini's vision API with
an OpenAI Structured Outputs schema, and returns a parsed list of
components: figures (with cropped image paths + structured
descriptions), equations (as LaTeX), tables (as headers + rows), and
pseudocode/algorithm boxes (as numbered steps).

The cropped PNGs are saved to disk so the downstream course generator
can reference them via ``\\includegraphics`` in the final slides — the
visual content from the source PDF survives to the final material,
not just a textual description.

Vanilla preservation invariant: this module is opt-in. Callers must
explicitly construct a :class:`VlmExtractor` and feed it pages. The
existing extraction pipeline is unaffected.

Defensive on every failure mode: missing API key, network failure,
malformed response, schema-rejection — every failure returns an empty
:class:`ExtractedPage` with a logged warning. The hybrid ingester
(Phase 4) treats an empty extraction as "use PyMuPDF4LLM output only"
so a VLM outage doesn't break a run.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Structured Output schema — what we ask the VLM to return
# ---------------------------------------------------------------------------
#
# OpenAI Structured Outputs (via response_format=...) requires a Pydantic
# model that maps to a strict JSON schema. We use discriminated unions
# (Literal type tags + Field(discriminator=...)) so each component class
# has its own required fields.


class FigureComponent(BaseModel):
    """A figure, diagram, scatter plot, or similar visual element."""

    type: Literal["figure"] = "figure"
    label: str = Field(description="Figure label as printed in the source, e.g. 'Figure 10.16' or empty string if none")
    caption: str = Field(description="The full caption text under the figure")
    description: str = Field(description="2-4 sentence concrete description of what the figure shows visually: axes, plotted shapes, relationships, key data points")
    pedagogical_point: str = Field(description="The single teaching insight the figure conveys, in one sentence")


class EquationComponent(BaseModel):
    """A display equation, definition, or formal mathematical statement."""

    type: Literal["equation"] = "equation"
    label: str = Field(description="Equation label as printed, e.g. '(10.5)' or empty string if none")
    latex: str = Field(description="Pure LaTeX source for the equation, ready to be wrapped in \\[ ... \\]")
    description: str = Field(description="One-sentence description of what the equation defines or computes, in plain English")


class TableComponent(BaseModel):
    """A table with headers and row data."""

    type: Literal["table"] = "table"
    label: str = Field(description="Table label, e.g. 'Table 2.1' or empty string")
    caption: str = Field(description="The table caption text or empty string")
    headers: List[str] = Field(description="Column header strings")
    rows: List[List[str]] = Field(description="Each row is a list of cell strings; row length must match headers length")


class AlgorithmComponent(BaseModel):
    """An algorithm block / pseudocode listing."""

    type: Literal["algorithm"] = "algorithm"
    label: str = Field(description="Algorithm label, e.g. 'Algorithm 8.2' or empty string")
    name: str = Field(description="Algorithm name as printed (e.g. 'k-means') or empty string")
    steps: List[str] = Field(description="Each numbered/lettered step on its own line, as printed in the source")


# Discriminated union so OpenAI structured outputs can validate each
# component against its own shape.
ComponentType = Union[FigureComponent, EquationComponent, TableComponent, AlgorithmComponent]


class ExtractedPage(BaseModel):
    """All structured components found on a single page."""

    components: List[ComponentType] = Field(
        default_factory=list,
        description="Components found on the page, in source order",
    )
    notes: str = Field(
        default="",
        description="Free-text notes about extraction confidence or ambiguity",
    )


# ---------------------------------------------------------------------------
# The extractor
# ---------------------------------------------------------------------------


_DEFAULT_PROMPT = (
    "You are extracting structured content from a single page of a textbook. "
    "The image shows the rendered PDF page.\n\n"
    "For each FIGURE: extract the label, caption, a concrete 2-4 sentence "
    "description of the visual content (axes, plotted shapes, relationships), "
    "and the single pedagogical point it teaches.\n\n"
    "For each EQUATION (display equations only — skip inline math): extract "
    "the equation label if present, the equation as LaTeX (ready for \\[ ... "
    "\\]), and a one-sentence plain-English description.\n\n"
    "For each TABLE: extract the label, caption, column headers, and all data "
    "rows. Row length must match header count.\n\n"
    "For each ALGORITHM / PSEUDOCODE BOX: extract the label, name, and each "
    "step on its own line.\n\n"
    "Skip body prose — that is extracted separately. Return components in "
    "source order. If a field doesn't apply, return an empty string (NOT "
    "null). If you are uncertain about any extraction, note it in the notes "
    "field rather than omitting the component."
)


# Default rendering DPI for the page-image we send to the VLM. 150 DPI
# is a good cost/clarity tradeoff: high enough that equations are
# legible, low enough that the image stays compact (~1500x2000 px for
# letter-sized pages, ~1500 input tokens).
DEFAULT_RENDER_DPI = 150

DEFAULT_MODEL = "gpt-4o-mini"


class VlmExtractor:
    """Extracts structured visual content from a PDF page via GPT-4o-mini.

    Args:
        client: An OpenAI client instance. If None, one is constructed
            lazily on first call (looking at ``OPENAI_API_KEY`` env
            variable).
        model: The vision-capable model. Defaults to ``gpt-4o-mini``.
        figures_dir: Where to save cropped page PNGs. The hybrid
            ingester sets this to ``.grounding_cache/figures/<textbook_id>/``.
            If None, images are NOT saved to disk (description-only mode).
        render_dpi: Rendering resolution for the page image.
        prompt: Override the extraction prompt (rarely needed).
    """

    def __init__(
        self,
        client=None,
        *,
        model: str = DEFAULT_MODEL,
        figures_dir: Optional[Path] = None,
        render_dpi: int = DEFAULT_RENDER_DPI,
        prompt: str = _DEFAULT_PROMPT,
    ) -> None:
        self._client = client
        self.model = model
        self.figures_dir = Path(figures_dir) if figures_dir else None
        self.render_dpi = render_dpi
        self.prompt = prompt
        if self.figures_dir is not None:
            self.figures_dir.mkdir(parents=True, exist_ok=True)

    @property
    def client(self):
        """Lazy client. Lets us construct the extractor without env vars."""
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def render_page_png(self, page, *, save_as: Optional[Path] = None) -> bytes:
        """Render a PyMuPDF page to PNG bytes (and optionally to disk).

        Args:
            page: ``pymupdf.Page`` instance.
            save_as: If set, also writes the PNG to this path. Returns
                the bytes either way.
        """
        # PyMuPDF's get_pixmap takes a matrix scale; DPI / 72 = scale.
        scale = self.render_dpi / 72.0
        # `pymupdf` exposes Matrix at module top-level on recent
        # versions; fall back to fitz.Matrix for older ones.
        try:
            import pymupdf as _mp
            matrix = _mp.Matrix(scale, scale)
        except (ImportError, AttributeError):
            import fitz
            matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        png_bytes = pix.tobytes("png")
        if save_as is not None:
            save_as.parent.mkdir(parents=True, exist_ok=True)
            save_as.write_bytes(png_bytes)
        return png_bytes

    def extract(
        self,
        page,
        *,
        textbook_id: str,
        page_num: int,
    ) -> ExtractedPage:
        """Extract structured visual content from a single page.

        Args:
            page: ``pymupdf.Page`` instance.
            textbook_id: Used to name saved PNG files.
            page_num: 1-based page number; used in PNG filename and
                referenced from the downstream slide LaTeX.

        Returns:
            :class:`ExtractedPage`. Empty (no components) on any
            failure path — never raises.
        """
        # Save full-page PNG to disk if a figures_dir was configured;
        # the slide generator can later reference it via includegraphics.
        save_path: Optional[Path] = None
        if self.figures_dir is not None:
            save_path = self.figures_dir / f"{textbook_id}_p{page_num:04d}.png"

        try:
            png_bytes = self.render_page_png(page, save_as=save_path)
        except Exception as e:
            print(
                f"[vlm] Page render failed for {textbook_id}:p{page_num} "
                f"({type(e).__name__}: {e}); returning empty extraction.",
                flush=True,
            )
            return ExtractedPage()

        return self._call_vlm_with_retry(png_bytes, textbook_id, page_num)

    # Retry budget for transient VLM failures. gpt-4o's 30k TPM cap is
    # hit hard during dense PDF ingestion (~29.5k tokens/page); a single
    # call fails roughly every 2 minutes at saturation. Each attempt
    # backs off proportionally so retries don't pile on the rate limit.
    _VLM_RETRY_MAX_ATTEMPTS = 6
    _VLM_RETRY_BASE_SLEEP_S = 30.0  # 30s, 60s, 90s, 120s, 150s, 180s
    _VLM_RETRY_RATE_LIMIT_SLEEP_S = 65.0  # sleep past the TPM window

    def _call_vlm_with_retry(
        self,
        png_bytes: bytes,
        textbook_id: str,
        page_num: int,
    ) -> ExtractedPage:
        """v7.1 — retry transient VLM failures (rate limits, timeouts).

        Returns an empty ExtractedPage only when ALL retries fail.
        Stays defensive — never raises so the caller's ingestion loop
        can continue even when a page genuinely can't be processed.
        """
        import time as _time
        last_err = None
        for attempt in range(1, self._VLM_RETRY_MAX_ATTEMPTS + 1):
            try:
                return self._call_vlm(png_bytes)
            except Exception as e:
                last_err = e
                err_name = type(e).__name__
                err_str = str(e)
                # Rate-limit handling: parse retry-after if present, else
                # sleep past the 1-min TPM window.
                if "RateLimitError" in err_name or "rate_limit_exceeded" in err_str.lower():
                    sleep_s = self._parse_retry_after(err_str) or self._VLM_RETRY_RATE_LIMIT_SLEEP_S
                    if attempt < self._VLM_RETRY_MAX_ATTEMPTS:
                        print(
                            f"[vlm] Rate limit on {textbook_id}:p{page_num} "
                            f"(attempt {attempt}/{self._VLM_RETRY_MAX_ATTEMPTS}); "
                            f"sleeping {sleep_s:.0f}s before retry.",
                            flush=True,
                        )
                        _time.sleep(sleep_s)
                        continue
                # Other transient errors: exponential-ish backoff.
                if attempt < self._VLM_RETRY_MAX_ATTEMPTS:
                    sleep_s = self._VLM_RETRY_BASE_SLEEP_S * attempt
                    print(
                        f"[vlm] Transient failure on {textbook_id}:p{page_num} "
                        f"({err_name}, attempt {attempt}/{self._VLM_RETRY_MAX_ATTEMPTS}); "
                        f"sleeping {sleep_s:.0f}s before retry.",
                        flush=True,
                    )
                    _time.sleep(sleep_s)
                    continue
        # Exhausted retries — log and return empty.
        print(
            f"[vlm] VLM call failed for {textbook_id}:p{page_num} after "
            f"{self._VLM_RETRY_MAX_ATTEMPTS} attempts "
            f"({type(last_err).__name__}: {last_err}); returning empty extraction.",
            flush=True,
        )
        return ExtractedPage()

    @staticmethod
    def _parse_retry_after(err_str: str) -> Optional[float]:
        """Parse 'try again in 892ms' / 'try again in 30s' from a
        rate-limit message into a seconds-to-sleep value. Returns None
        when no parseable hint is found."""
        import re as _re
        m = _re.search(r"try again in\s+(\d+(?:\.\d+)?)\s*(ms|s)", err_str, _re.IGNORECASE)
        if not m:
            return None
        value = float(m.group(1))
        unit = m.group(2).lower()
        seconds = value / 1000.0 if unit == "ms" else value
        # Always sleep at least 5s — the API's "try again in 892ms" is
        # often optimistic and we hit the limit again immediately.
        return max(5.0, seconds + 2.0)

    def _call_vlm(self, png_bytes: bytes) -> ExtractedPage:
        """Send the page image to the VLM and parse the structured response.

        Encapsulated so tests can mock the OpenAI call cleanly.

        ``temperature=0`` + a fixed ``seed`` push the API toward
        deterministic output across runs. The IR cache pins this
        further: once a textbook has been ingested, subsequent loads
        skip the VLM entirely.
        """
        b64 = base64.b64encode(png_bytes).decode("ascii")
        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": self.prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            }],
            response_format=ExtractedPage,
            temperature=0,
            seed=42,
        )
        parsed = completion.choices[0].message.parsed
        return parsed if parsed is not None else ExtractedPage()
