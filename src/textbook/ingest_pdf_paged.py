"""Paged PyMuPDF4LLM-based PDF ingestion.

Uses ``pymupdf4llm.to_markdown(..., page_chunks=True)`` to get one
markdown chunk per source page, then builds the Textbook IR with REAL
per-paragraph page numbers (the synthetic word-count-based pagination
used by the markdown ingester is bypassed entirely).

This module is the "workhorse" half of the v3 hybrid extraction
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

from pathlib import Path
from typing import List, Optional

from .ingest_md import _blocks_to_chapters, _extract_blocks
from .ingest_pdf import _file_sort_key, _normalize_pdf_markdown_headings, _renumber_chapter
from .schema import Chapter, PageSpan, Textbook


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


def _extract_blocks_with_page(md_text: str, page_num: int,
                              seen_chapter: bool) -> tuple[list[dict], bool]:
    """Extract blocks from one page's markdown and tag them with ``page``.

    Returns ``(blocks, new_seen_chapter)`` so caller can thread the
    ``seen_chapter`` state across pages. The state is now passed INTO
    the heading normaliser as well (previously the normaliser reset
    the flag every call, causing one chapter per page on PDFs whose
    pymupdf4llm output has unnumbered ``##`` headings throughout —
    the chapter-inflation bug observed at v4 measurement time).
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
) -> Textbook:
    """Ingest a single PDF via PyMuPDF4LLM with per-page granularity.

    Args:
        path: PDF file path.
        textbook_id / title / authors / edition: Forwarded to the
            Textbook IR. Caller-supplied identifiers.

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
    pages = pymupdf4llm.to_markdown(
        str(path), page_chunks=True, show_progress=False,
    )

    all_blocks: list[dict] = []
    seen_chapter = False
    for page_idx, page in enumerate(pages):
        # pymupdf4llm returns a list of either dicts (with 'text', etc.)
        # or bare strings depending on the version. Handle both.
        md_text = page["text"] if isinstance(page, dict) else page
        if not md_text or not md_text.strip():
            continue
        # PyMuPDF page numbers are 1-based externally; we report
        # page_idx + 1 to align with what the verifier expects.
        page_num = page_idx + 1
        blocks, seen_chapter = _extract_blocks_with_page(
            md_text, page_num, seen_chapter,
        )
        all_blocks.extend(blocks)

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
    return textbook


def ingest_pdf_directory_paged(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Ingest a directory of per-chapter PDFs via PyMuPDF4LLM paged path.

    Mirrors :func:`src.textbook.ingest_pdf.ingest_pdf_directory` but
    routes each PDF through :func:`ingest_pdf_file_paged` so chapters
    keep real per-page numbering inside each PDF. Top-level chapter
    numbers are reassigned in directory order.
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
