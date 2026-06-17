"""Equation-only VLM extraction for the grounded ingest path.

When a textbook is supplied, the paged ingester crops embedded images. Most are
figures (kept as images — a model can only describe them, not faithfully
redraw them). But equation/formula blocks render far better as **native
LaTeX** than as a small, non-editable image thumbnail, and ``pymupdf4llm``
either crops them as images or flattens complex inline math into garbled text.

This module turns an equation *crop* into clean LaTeX with a single focused
VLM call, gated by a cheap aspect-ratio pre-filter so figures aren't sent to
the model. **Equation-only by design** — figures keep their image.
**Fail-open** — any error (no API key, network, non-equation) returns ``""``
and the caller keeps the image. The result is cached in the Textbook IR, so
the VLM runs **once per textbook**, not per course run.

No heavy module-level imports (``openai`` is imported lazily) so this stays
importable without the optional grounding extras.
"""
from __future__ import annotations

import base64
import os
import re
import struct
from pathlib import Path

# Equation crops are wider than tall; figures (scatter, flowchart, photo) are
# squarer or taller. Generous threshold — the VLM is the final arbiter, this
# only skips obvious figures to save calls.
_EQUATION_ASPECT_MIN = 1.6

_EQUATION_PROMPT = (
    "You are inspecting a small image cropped from a textbook page. If it is a "
    "single mathematical equation, formula, or formal definition, reply with "
    "ONLY its clean LaTeX source — no $ or \\[ \\] wrappers, no prose. If it is "
    "anything else (a chart, plot, diagram, flowchart, photo, table, or "
    "decorative image), reply with exactly: NONE"
)


def _png_dimensions(path) -> tuple[int, int]:
    """(width, height) from a PNG header, no Pillow dependency. (0,0) if the
    file isn't a readable PNG."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
            return (0, 0)
        w, h = struct.unpack(">II", head[16:24])
        return (int(w), int(h))
    except Exception:
        return (0, 0)


def looks_like_equation(path) -> bool:
    """Cheap pre-filter: True for crops clearly wider than tall (single/few-line
    equations). Skips square/tall figures to avoid wasting a VLM call. Returns
    True when dimensions are unreadable, so a real equation is never silently
    skipped (the VLM is the final arbiter)."""
    w, h = _png_dimensions(path)
    if not w or not h:
        return True
    return (w / h) >= _EQUATION_ASPECT_MIN


def _clean_latex(out: str) -> str:
    """Strip wrappers the VLM sometimes adds despite the prompt."""
    out = out.strip()
    out = re.sub(r"^```(?:latex)?\s*|\s*```$", "", out).strip()
    out = out.strip("$").strip()
    out = re.sub(r"^\\\[\s*|\s*\\\]$", "", out).strip()
    return out


def extract_equation_latex(path, *, model: str = "gpt-4o-mini", client=None) -> str:
    """Return clean LaTeX if the cropped image is a math equation, else ``""``.

    Fail-open: a missing API key, a network error, or a non-equation image all
    return ``""`` so the caller keeps the original image. One VLM call;
    temperature 0 + fixed seed for cache-stable output.
    """
    try:
        b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except Exception:
        return ""
    if client is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            return ""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
        except Exception:
            return ""
    try:
        resp = client.chat.completions.create(
            model=model,
            temperature=0,
            seed=42,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _EQUATION_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        out = (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""
    if not out or out.strip().upper().startswith("NONE"):
        return ""
    return _clean_latex(out)
