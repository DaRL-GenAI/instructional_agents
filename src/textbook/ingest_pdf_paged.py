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


def _extract_blocks_with_page(md_text: str, page_num: int,
                              seen_chapter: bool) -> tuple[list[dict], bool]:
    """Extract blocks from one page's markdown and tag them with ``page``.

    Returns ``(blocks, new_seen_chapter)`` so caller can thread the
    ``seen_chapter`` state across pages (the heading normaliser uses
    it to decide whether the first unnumbered ``##`` becomes a chapter
    or a sub-section).
    """
    # Track whether a `# Chapter ...` heading is present anywhere in
    # this page's normalised markdown so we can update seen_chapter.
    md_normalised = _normalize_pdf_markdown_headings(md_text)
    next_seen = seen_chapter or any(
        line.startswith("# ") for line in md_normalised.splitlines()
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
