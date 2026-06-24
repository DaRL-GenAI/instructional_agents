"""Paged PyMuPDF4LLM-based PDF ingestion.

Uses ``pymupdf4llm.to_markdown(..., page_chunks=True)`` to get one
markdown chunk per source page, then builds the Textbook IR with REAL
per-paragraph page numbers (the synthetic word-count-based pagination
used by the markdown ingester is bypassed entirely).

This module is the "workhorse" half of the hybrid extraction
pipeline. It handles prose pages cleanly (markdown preserves headings,
tables, code blocks better than plain-text extraction). Pages flagged
as complex by :mod:`src.textbook.spatial_router` will additionally be
augmented by a VLM in the hybrid ingester (Phase 4).

Differentiation from the prior tried+removed PyMuPDF4LLM-as-default
attempt (documented in LEARNINGS.md): that attempt used
``page_chunks=False`` which produced ONE giant markdown string for the
whole PDF and caused coarse chunks downstream (-11 pp precision). This
module uses ``page_chunks=True`` for per-page granularity AND
preserves real page numbers (the prior attempt also lost page
fidelity by going through the markdown ingester's synthetic
pagination).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .ingest_md import _blocks_to_chapters, _extract_blocks
from .ingest_pdf import _file_sort_key, _normalize_pdf_markdown_headings, _renumber_chapter
from .schema import Chapter, PageSpan, Textbook
from .equation_vlm import (
    looks_like_equation as _looks_like_equation,
    extract_equation_latex as _extract_equation_latex,
)


# Math signal regex — Greek letters, calculus operators, comparison
# operators paired with symbols, subscript/superscript patterns. A
# paragraph that hits >= 3 distinct signals OR carries the keyword
# "equation"/"formula" is tagged kind=equation so the writer's
# evidence block surfaces it via the KIND field. Generic across
# textbooks: any domain whose source PDF describes formulas in
# notation will trigger.
_MATH_SIGNAL_RE = re.compile(
    r"[Α-ω]"               # Greek capitals + lowercase
    r"|[∀-⋿]"              # mathematical operators
    r"|\bsum_\{|\bsum_\b"
    r"|\\frac|\\sum|\\int|\\sqrt|\\lVert|\\partial"
    r"|\\\[|\\\]"
    r"|\b\w+_\{[^}]+\}"              # subscript pattern x_{i}
    r"|\b\w+\^\{?[^\s}]+\}?"         # superscript pattern x^2
)
_MATH_KEYWORD_RE = re.compile(
    r"\b(?:equation|formula|theorem|lemma|proof|kernel function|"
    r"objective function|distance metric)\b",
    re.IGNORECASE,
)

_EXAMPLE_HEADER_RE = re.compile(
    r"(?:^|\n)\s*(?:\*\*)?Example\s+\d+(?:\.\d+)?\b",
    re.IGNORECASE,
)
_EXAMPLE_INLINE_RE = re.compile(
    r"\bFor example,\s|\bAs an example,\s|\bConsider\s+(?:the\s+)?(?:following\s+)?example\b",
    re.IGNORECASE,
)


def _tag_example_paragraphs(textbook: Textbook) -> int:
    """Re-tag prose paragraphs that start a worked example with
    ``kind='example'`` so the slide writer's KIND field surfaces them.

    Triggers on a leading ``Example N`` / ``Example N.M`` header (the
    textbook's own marker for a numbered worked example) — that single
    signal is high-precision because textbook authors reserve the
    pattern for actual worked examples. Inline "for example, …" is
    deliberately NOT enough on its own. Idempotent.
    """
    retagged = 0
    for chapter in textbook.chapters:
        for section in chapter.sections:
            for para in section.paragraphs:
                if para.kind and para.kind != "prose":
                    continue
                text = para.text or ""
                if not text:
                    continue
                if _EXAMPLE_HEADER_RE.search(text):
                    para.kind = "example"
                    retagged += 1
    return retagged


def _tag_equation_paragraphs(textbook: Textbook) -> int:
    """Re-tag prose paragraphs that contain dense math notation with
    ``kind='equation'`` so the slide writer's KIND field surfaces them.

    Returns the count of paragraphs re-tagged. Idempotent and safe to
    call repeatedly — already-tagged paragraphs are left alone.

    Triggers on: 3+ distinct math signals (Greek letters, calculus
    operators, sub/superscript patterns) OR explicit math keywords
    (equation / formula / kernel function / etc.). The detector is
    domain-agnostic — any source PDF that describes equations in
    notation will surface them.
    """
    retagged = 0
    for chapter in textbook.chapters:
        for section in chapter.sections:
            for para in section.paragraphs:
                if para.kind and para.kind != "prose":
                    continue
                text = para.text or ""
                if not text:
                    continue
                signal_matches = _MATH_SIGNAL_RE.findall(text)
                has_keyword = bool(_MATH_KEYWORD_RE.search(text))
                if len(set(signal_matches)) >= 3 or has_keyword:
                    para.kind = "equation"
                    retagged += 1
    return retagged


def _assign_real_pages(textbook: Textbook) -> None:
    """Fill in Section.pages and Chapter.pages from per-paragraph pages.

    Mirrors the post-processing :func:`src.textbook.ingest_md._assign_pages`
    does, except it RESPECTS the per-paragraph page numbers we already
    set (from the source markdown's per-page extraction) rather than
    overwriting them with synthetic pages. Paragraphs without a real
    page number (page == 0) are left as-is.
    """
    for chapter in textbook.chapters:
        chapter_pages = []
        for section in chapter.sections:
            section_pages = [p.page for p in section.paragraphs if p.page]
            if section_pages:
                section.pages = PageSpan(start=min(section_pages),
                                         end=max(section_pages))
                chapter_pages.extend(section_pages)
        if chapter_pages:
            chapter.pages = PageSpan(start=min(chapter_pages),
                                     end=max(chapter_pages))


def _ends_mid_sentence(text: str) -> bool:
    """True if the text appears to break off mid-sentence at its end.

    Heuristic: the last non-whitespace character is NOT one of the
    standard sentence terminators ``. ! ? ; :``. Words ending in
    common abbreviations (``etc.``, ``e.g.``) terminate cleanly under
    this rule (false negatives — they're treated as complete), which
    is the safer direction to err in.
    """
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] not in ".!?;:"


def _starts_mid_sentence(text: str) -> bool:
    """True if the text appears to continue from a prior sentence.

    Heuristic: the first non-whitespace character is a lowercase
    letter. A capital letter, digit, or punctuation signals a fresh
    sentence and we do NOT stitch.
    """
    stripped = text.lstrip()
    if not stripped:
        return False
    return stripped[0].islower()


# Cross-page dangling paragraphs are merged into a single paragraph
# whose total length stays under this many characters. The cap is a
# safety belt against runaway merges on very long pages; in practice
# dangling sentences cap out at ~200-400 chars and won't approach it.
_STITCH_MAX_LEN = 2000


def _stitch_cross_page_dangles(blocks: list[dict]) -> list[dict]:
    """Glue dangling sentences across page boundaries into one paragraph.

    The PyMuPDF4LLM page-chunked extractor produces a separate block
    per page. When a sentence breaks mid-thought at a physical page
    break, it appears as two half-paragraphs in adjacent blocks:
    block N's last paragraph ends without a terminator and block N+1's
    first paragraph starts with a lowercase letter (continuation).
    Neither half retrieves well in isolation — the verifier query
    matches the WHOLE sentence, not either half.

    This helper detects that pattern and merges the two halves into a
    single paragraph that carries the EARLIER page's tag (the sentence
    started there). The chunker's page-range handling absorbs the
    multi-page content cleanly.

    Pure paragraph stitching: heading blocks are NEVER merged with
    paragraph blocks; merges that would exceed ``_STITCH_MAX_LEN`` are
    skipped (safety belt against unlikely degenerate inputs).
    """
    if not blocks:
        return blocks
    out: list[dict] = []
    prev: Optional[dict] = None
    for blk in blocks:
        if prev is None:
            prev = blk
            continue
        if (
            prev["type"] == "paragraph"
            and blk["type"] == "paragraph"
            and prev.get("page") != blk.get("page")
            and _ends_mid_sentence(prev.get("text", ""))
            and _starts_mid_sentence(blk.get("text", ""))
        ):
            merged_text = (
                prev["text"].rstrip() + " " + blk["text"].lstrip()
            )
            if len(merged_text) <= _STITCH_MAX_LEN:
                merged = {**prev, "text": merged_text}
                prev = merged
                continue
        out.append(prev)
        prev = blk
    if prev is not None:
        out.append(prev)
    return out


# Figure caption lines in a page's markdown, e.g. "Figure 10.14 A density-based
# clustering..." or "**Figure 8.2:** ...". Anchored to line start (after optional
# bold markers) so inline references ("see Figure 10.14") are not mistaken for
# captions. Captures (number, caption-text). Textbook-agnostic — the universal
# "Figure N(.M)" convention, no per-book vocabulary.
_FIGURE_CAPTION_RE = re.compile(
    r"(?:^|\n)\s*\**\s*(?:Figure|Fig\.?)\s+(\d+(?:\.\d+)?)\b[:.\s]*([^\n]{0,200})",
    re.IGNORECASE,
)

# pymupdf4llm emits a markdown image ref ![alt](file) for each extracted image,
# pointing at the ORIGINAL filename. We rename those files and re-emit each image
# as an [IMAGE_PATH:] paragraph, so the markdown refs are both duplicate and
# dangling — strip them so every image is represented exactly once.
_MD_IMAGE_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _extract_figure_captions(md_text: str) -> list[tuple[str, str]]:
    """Pull ``(figure_number, caption_text)`` pairs from a page's markdown in
    reading order so each extracted image can be paired with its real caption.
    Caption text is the remainder of the ``Figure N.M ...`` line with markdown
    bold/italic markers stripped."""
    out: list[tuple[str, str]] = []
    for m in _FIGURE_CAPTION_RE.finditer(md_text or ""):
        num = m.group(1)
        cap = re.sub(r"[*_`]+", "", (m.group(2) or "")).strip()
        out.append((num, cap))
    return out


def _extract_blocks_with_page(md_text: str, page_num: int,
                              seen_chapter: bool) -> tuple[list[dict], bool]:
    """Extract blocks from one page's markdown and tag them with ``page``.

    Returns ``(blocks, new_seen_chapter)`` so caller can thread the
    ``seen_chapter`` state across pages. The state is now passed INTO
    the heading normaliser as well (previously the normaliser reset
    the flag every call, causing one chapter per page on PDFs whose
    pymupdf4llm output has unnumbered ``##`` headings throughout —
    the chapter-inflation bug observed at an earlier measurement).
    """
    md_normalised, next_seen = _normalize_pdf_markdown_headings(
        md_text, seen_chapter=seen_chapter,
    )
    blocks = _extract_blocks(md_normalised)
    for blk in blocks:
        blk["page"] = page_num
    return blocks, next_seen


def ingest_pdf_file_paged(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
    figures_dir: Optional[Path] = None,
    extract_equations: bool = True,
    equation_vlm_model: str = "gpt-4o-mini",
) -> Textbook:
    """Ingest a single PDF via PyMuPDF4LLM with per-page granularity.

    Args:
        path: PDF file path.
        textbook_id / title / authors / edition: Forwarded to the
            Textbook IR. Caller-supplied identifiers.
        figures_dir: When set, pymupdf4llm extracts embedded image
            XObjects from the PDF as tight cropped PNGs into this
            directory, and the ingester emits
            ``[IMAGE_PATH: ...]`` markers on the corresponding pages.
            When None (default), no image files are written and no
            image markers appear in the IR — vanilla preservation.
        extract_equations: When True (default) AND images are being
            extracted, equation-shaped crops are converted to native
            ``[LATEX: ...]`` via one focused VLM call each (figures keep
            their image). Bound to the grounded path, not a separate
            flag; fail-open (no API key / error → keep the image); cached
            in the IR so the VLM runs once per textbook.
        equation_vlm_model: model for that equation→LaTeX call.

    Returns:
        A :class:`Textbook` with REAL per-paragraph page numbers
        sourced from PyMuPDF's page boundaries.

    Falls back to the plain-text ingester if pymupdf4llm is unavailable
    OR if the markdown output yields no chapters (rare).
    """
    try:
        import pymupdf4llm
    except ImportError:
        from .ingest_pdf import ingest_pdf_file
        return ingest_pdf_file(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )

    path = Path(path)

    # When figures_dir is set, route through pymupdf4llm's native image
    # extraction. The library writes embedded image XObjects from the
    # PDF as tight cropped PNGs — the actual figure region, not a
    # full-page screenshot. Vanilla path (figures_dir=None) skips this.
    md_kwargs = {"page_chunks": True, "show_progress": False}
    figures_dir_p = Path(figures_dir) if figures_dir is not None else None
    if figures_dir_p is not None:
        figures_dir_p.mkdir(parents=True, exist_ok=True)
        md_kwargs.update({
            "write_images": True,
            "image_path": str(figures_dir_p),
            "image_format": "png",
            "image_size_limit": 0.05,
        })

    pages = pymupdf4llm.to_markdown(str(path), **md_kwargs)

    # pymupdf4llm names extracted images as ``{pdf_stem}.pdf-{page:04d}-
    # {idx:02d}.png``. Walk the directory once after extraction and
    # build a page → list[(idx, renamed_path)] map. We rename each
    # file to ``{textbook_id}_p{page:04d}_{idx:02d}.png`` so the
    # citation surface uses our short textbook_id, not the PDF stem
    # (which can be arbitrary). Renaming is cheap and one-shot.
    images_by_page: dict[int, list[Path]] = {}
    if figures_dir_p is not None:
        pdf_stem = path.stem
        # Regex captures the page number + per-page image index out of
        # pymupdf4llm's default filename convention. Stem is escaped to
        # cope with dots/underscores in real-world PDF names.
        pattern = re.compile(
            rf'^{re.escape(pdf_stem)}\.pdf-(\d+)-(\d+)\.png$'
        )
        for f in sorted(figures_dir_p.iterdir()):
            if not f.is_file():
                continue
            m = pattern.match(f.name)
            if not m:
                continue
            page_num = int(m.group(1))
            img_idx = int(m.group(2))
            new_name = f"{textbook_id}_p{page_num:04d}_{img_idx:02d}.png"
            new_path = figures_dir_p / new_name
            if new_path != f:
                if new_path.exists():
                    new_path.unlink()
                f.rename(new_path)
            images_by_page.setdefault(page_num, []).append(new_path)

    all_blocks: list[dict] = []
    seen_chapter = False
    for page_idx, page in enumerate(pages):
        # pymupdf4llm returns a list of either dicts (with 'text', etc.)
        # or bare strings depending on the version. Handle both.
        md_text = page["text"] if isinstance(page, dict) else page
        # Drop pymupdf4llm's markdown image refs: each image is re-emitted below
        # as an [IMAGE_PATH:] paragraph pointing at the renamed file, so the
        # markdown refs are duplicate AND dangling. Only when images are being
        # extracted (figures_dir_p set); otherwise there are none to strip.
        if figures_dir_p is not None and md_text:
            md_text = _MD_IMAGE_REF_RE.sub("", md_text)
        # PyMuPDF page numbers are 1-based externally; we report
        # page_idx + 1 to align with what the verifier expects.
        page_num = page_idx + 1
        if md_text and md_text.strip():
            blocks, seen_chapter = _extract_blocks_with_page(
                md_text, page_num, seen_chapter,
            )
            all_blocks.extend(blocks)
        # Emit one figure_cap paragraph per image extracted from this
        # page so the downstream chunker can surface visual chunks.
        # Each paragraph carries an [IMAGE_PATH: ...] marker pointing
        # at the saved PNG; the writer's visual-content rules turn it
        # into ``\includegraphics`` on the slide.
        # Pair each extracted image with the page's i-th "Figure N.M" caption
        # (reading order) so the figure paragraph carries its real caption text
        # instead of a bare marker — this is what downstream figure<->slide
        # matching and figure-query retrieval read. Falls back to the bare form
        # when the page has no matching caption (decorative image / count mismatch).
        page_captions = (
            _extract_figure_captions(md_text) if (md_text and md_text.strip()) else []
        )
        for img_idx, img_path in enumerate(images_by_page.get(page_num, []), start=1):
            fig_num, cap_text = ("", "")
            if img_idx - 1 < len(page_captions):
                fig_num, cap_text = page_captions[img_idx - 1]
            marker = f"[IMAGE_PATH: {img_path.resolve()}]"
            # Equation crops → native LaTeX (editable, faithful) instead of a
            # small non-editable image thumbnail. Equation-ONLY + fail-open:
            # the aspect-ratio pre-filter skips figure-shaped crops, and any
            # VLM failure (no key / non-equation / error) returns "" and we
            # fall back to the image path below. Runs only on the grounded
            # path (images exist only when figures_dir is set) and is cached
            # in the IR, so the VLM runs once per textbook, not per run.
            eq_latex = ""
            if extract_equations and _looks_like_equation(img_path):
                eq_latex = _extract_equation_latex(
                    img_path, model=equation_vlm_model
                )
            if eq_latex:
                label = f"Equation {fig_num}: " if fig_num else "Equation: "
                all_blocks.append({
                    "type": "paragraph",
                    "kind": "equation",
                    "text": f"{label}[LATEX: {eq_latex}]",
                    "page": page_num,
                })
                continue
            if fig_num and cap_text:
                text = f"Figure {fig_num}: {cap_text} {marker}"
            elif fig_num:
                text = f"Figure {fig_num}: {marker}"
            else:
                text = f"Figure (p{page_num}, item {img_idx}): {marker}"
            all_blocks.append({
                "type": "paragraph",
                "kind": "figure_cap",
                "text": text,
                "page": page_num,
            })

    # Cross-page sentence stitching: merge dangling-end paragraphs on
    # page N with continuing-start paragraphs on page N+1 so a sentence
    # broken by a physical page break becomes one retrievable unit.
    all_blocks = _stitch_cross_page_dangles(all_blocks)

    chapters = _blocks_to_chapters(all_blocks)
    if not chapters:
        # Markdown output produced nothing structural — fall back to
        # the plain-text ingester so we still get a Textbook.
        from .ingest_pdf import ingest_pdf_file
        return ingest_pdf_file(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )

    textbook = Textbook(
        textbook_id=textbook_id, title=title,
        authors=authors or [], edition=edition,
        source_format="pdf",
        parser_quality=1.0,  # pymupdf4llm doesn't expose a quality score
        chapters=chapters,
    )
    _assign_real_pages(textbook)
    _tag_equation_paragraphs(textbook)
    _tag_example_paragraphs(textbook)
    return textbook


def ingest_pdf_directory_paged(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
    figures_dir: Optional[Path] = None,
) -> Textbook:
    """Ingest a directory of per-chapter PDFs via PyMuPDF4LLM paged path.

    Mirrors :func:`src.textbook.ingest_pdf.ingest_pdf_directory` but
    routes each PDF through :func:`ingest_pdf_file_paged` so chapters
    keep real per-page numbering inside each PDF. Top-level chapter
    numbers are reassigned in directory order. ``figures_dir`` is
    forwarded to each per-chapter ingestion so image extraction works
    across the whole directory.
    """
    path = Path(path)
    pdf_files = sorted(
        (p for p in path.iterdir() if p.suffix.lower() == ".pdf"),
        key=_file_sort_key,
    )
    all_chapters: List[Chapter] = []
    for pf in pdf_files:
        sub = ingest_pdf_file_paged(
            pf, textbook_id=textbook_id, title=title,
            figures_dir=figures_dir,
        )
        all_chapters.extend(sub.chapters)
    for idx, chapter in enumerate(all_chapters, start=1):
        _renumber_chapter(chapter, idx)
    textbook = Textbook(
        textbook_id=textbook_id, title=title,
        authors=authors or [], edition=edition,
        source_format="pdf",
        parser_quality=1.0,
        chapters=all_chapters,
    )
    _assign_real_pages(textbook)
    return textbook
