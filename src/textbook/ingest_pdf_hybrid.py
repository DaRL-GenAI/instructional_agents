"""Hybrid PDF ingestion: PyMuPDF4LLM workhorse + VLM augmentation.

Combines three modules:

1. :mod:`src.textbook.spatial_router` — classifies each page as prose
   or complex from PyMuPDF object metadata.
2. :mod:`src.textbook.ingest_pdf_paged` — extracts clean markdown
   from every page (the workhorse) with real page numbers preserved.
3. :mod:`src.textbook.vlm_adapter` — for pages flagged complex,
   additionally runs GPT-4o-mini vision to extract structured
   figure descriptions, equations as LaTeX, tables, and algorithms.

The two extraction outputs are merged at the BLOCK level before the
chapter builder runs: PyMuPDF4LLM provides the prose surrounding the
complex content, VLM provides the structured visual content. Both end
up as paragraphs in the same Section of the Textbook IR.

VLM-derived paragraphs use the existing kind tags (``figure_cap``,
``equation``, ``example``) and embed a few inline markers in the text
(``[IMAGE_PATH: ...]``, ``[CAPTION: ...]``) so the downstream slide
generator can recover the structured information.

Vanilla preservation invariant: this module is opt-in. The hybrid
ingester is only invoked when a caller explicitly passes a
:class:`VlmExtractor`. When the extractor is None, behavior is
identical to :func:`ingest_pdf_file_paged` from Phase 2.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pymupdf

from .ingest_md import _blocks_to_chapters
from .ingest_pdf import _file_sort_key, _renumber_chapter
from .ingest_pdf_paged import (
    _assign_real_pages,
    _extract_blocks_with_page,
    ingest_pdf_file_paged,
)
from .schema import Chapter, Textbook
from .spatial_router import (
    DEFAULT_DRAWINGS_THRESHOLD,
    PageClass,
    classify_page,
)
from .vlm_adapter import (
    AlgorithmComponent,
    EquationComponent,
    ExtractedPage,
    FigureComponent,
    TableComponent,
    VlmExtractor,
)


def _figure_paragraph_text(comp: FigureComponent, image_path: Optional[Path]) -> str:
    """Render a figure component as a single paragraph string.

    The format includes inline markers the slide generator can parse
    in Phase 6 to emit ``\\includegraphics``, captions, and descriptions
    in the right places. Multiple markers per paragraph keep them all
    grouped on the same Paragraph object.
    """
    parts = []
    label = comp.label.strip() if comp.label else "Figure"
    parts.append(f"{label}: {comp.caption.strip()}")
    if comp.description.strip():
        parts.append(f"[DESCRIPTION: {comp.description.strip()}]")
    if comp.pedagogical_point.strip():
        parts.append(f"[INSIGHT: {comp.pedagogical_point.strip()}]")
    if image_path is not None:
        parts.append(f"[IMAGE_PATH: {image_path}]")
    return " ".join(parts)


def _equation_paragraph_text(comp: EquationComponent) -> str:
    """Render an equation component as a single paragraph string.

    LaTeX source is wrapped in display-math markers so it can be lifted
    straight into a slide via ``\\[ ... \\]``.
    """
    parts = []
    label = comp.label.strip() if comp.label else ""
    if label:
        parts.append(f"Equation {label}:")
    else:
        parts.append("Equation:")
    parts.append(f"[LATEX: {comp.latex.strip()}]")
    if comp.description.strip():
        parts.append(f"[DESCRIPTION: {comp.description.strip()}]")
    return " ".join(parts)


def _table_paragraph_text(comp: TableComponent) -> str:
    """Render a table component as a single paragraph string.

    The table is encoded inline as a pipe-delimited markdown table so
    the downstream prompt can recognise it.
    """
    parts = []
    if comp.label.strip():
        parts.append(f"{comp.label.strip()}:")
    if comp.caption.strip():
        parts.append(comp.caption.strip())
    if comp.headers and comp.rows:
        header = "| " + " | ".join(comp.headers) + " |"
        sep = "| " + " | ".join(["---"] * len(comp.headers)) + " |"
        row_lines = [
            "| " + " | ".join(cell for cell in row) + " |"
            for row in comp.rows
        ]
        parts.append("[TABLE:\n" + "\n".join([header, sep, *row_lines]) + "\n]")
    return " ".join(parts)


def _algorithm_paragraph_text(comp: AlgorithmComponent) -> str:
    """Render an algorithm component as a single paragraph string."""
    parts = []
    label = comp.label.strip() if comp.label else ""
    name = comp.name.strip() if comp.name else ""
    header = " ".join([label, name]).strip() or "Algorithm"
    parts.append(f"{header}:")
    if comp.steps:
        numbered = " ".join(f"{i+1}. {s.strip()}" for i, s in enumerate(comp.steps))
        parts.append(f"[ALGORITHM_STEPS: {numbered}]")
    return " ".join(parts)


def _component_to_block(
    comp,
    *,
    page_num: int,
    image_path: Optional[Path] = None,
) -> dict:
    """Convert a single VLM component to a Textbook-IR block dict.

    The block format matches what :func:`_blocks_to_chapters` consumes:
    a dict with ``type``, ``kind``, ``text``, and ``page`` fields.
    """
    if isinstance(comp, FigureComponent):
        return {
            "type": "paragraph",
            "kind": "figure_cap",
            "text": _figure_paragraph_text(comp, image_path),
            "page": page_num,
        }
    if isinstance(comp, EquationComponent):
        return {
            "type": "paragraph",
            "kind": "equation",
            "text": _equation_paragraph_text(comp),
            "page": page_num,
        }
    if isinstance(comp, TableComponent):
        return {
            "type": "paragraph",
            "kind": "example",
            "text": _table_paragraph_text(comp),
            "page": page_num,
        }
    if isinstance(comp, AlgorithmComponent):
        return {
            "type": "paragraph",
            "kind": "example",
            "text": _algorithm_paragraph_text(comp),
            "page": page_num,
        }
    # Unknown component type — return None so caller can skip.
    return None


def _components_to_blocks(
    extraction: ExtractedPage,
    *,
    page_num: int,
    image_path: Optional[Path] = None,
) -> List[dict]:
    """Convert all components in a page extraction to IR blocks."""
    blocks: List[dict] = []
    for comp in extraction.components:
        blk = _component_to_block(comp, page_num=page_num, image_path=image_path)
        if blk is not None:
            blocks.append(blk)
    return blocks


def ingest_pdf_file_hybrid(
    path,
    *,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
    vlm_extractor: Optional[VlmExtractor] = None,
    drawings_threshold: int = DEFAULT_DRAWINGS_THRESHOLD,
) -> Textbook:
    """Hybrid PDF ingestion: PyMuPDF4LLM + selective VLM augmentation.

    Args:
        path: PDF file path.
        textbook_id / title / authors / edition: Forwarded to the
            Textbook IR.
        vlm_extractor: A :class:`VlmExtractor` instance. When None, this
            function delegates to :func:`ingest_pdf_file_paged` with no
            VLM augmentation (vanilla preservation invariant).
        drawings_threshold: Forwarded to the spatial router. Pages with
            more drawings than this are routed through the VLM.

    Returns:
        A :class:`Textbook` with real per-paragraph page numbers and,
        for any page flagged complex, additional Paragraphs carrying
        structured figure / equation / table / algorithm content.
    """
    # Without a VLM extractor, this is just the paged ingester.
    if vlm_extractor is None:
        return ingest_pdf_file_paged(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )

    try:
        import pymupdf4llm
    except ImportError:
        # Fall back to the paged ingester (which itself falls back to
        # plain text if pymupdf4llm is missing — defense in depth).
        return ingest_pdf_file_paged(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )

    path = Path(path)
    pages_md = pymupdf4llm.to_markdown(
        str(path), page_chunks=True, show_progress=False,
    )

    # Open the same PDF with PyMuPDF for spatial classification + VLM
    # rendering. pymupdf4llm uses PyMuPDF under the hood; this is the
    # same data, accessed twice.
    doc = pymupdf.open(str(path))
    try:
        all_blocks: List[dict] = []
        seen_chapter = False
        for page_idx, page_md in enumerate(pages_md):
            md_text = page_md["text"] if isinstance(page_md, dict) else page_md
            page_num = page_idx + 1

            # PyMuPDF4LLM blocks for the prose surrounding any visual
            # content. These run on EVERY page (including complex ones)
            # because the surrounding prose is still useful.
            if md_text and md_text.strip():
                blocks, seen_chapter = _extract_blocks_with_page(
                    md_text, page_num, seen_chapter,
                )
                all_blocks.extend(blocks)

            # Spatial classification on the underlying PyMuPDF page.
            page = doc[page_idx]
            routing = classify_page(page, drawings_threshold=drawings_threshold,
                                    page_index=page_idx)
            if routing.page_class is PageClass.COMPLEX:
                extraction = vlm_extractor.extract(
                    page, textbook_id=textbook_id, page_num=page_num,
                )
                # Resolve the saved PNG path so figure components carry
                # an [IMAGE_PATH: ...] marker.
                image_path: Optional[Path] = None
                if vlm_extractor.figures_dir is not None:
                    candidate = vlm_extractor.figures_dir / f"{textbook_id}_p{page_num:04d}.png"
                    if candidate.exists():
                        image_path = candidate
                all_blocks.extend(_components_to_blocks(
                    extraction, page_num=page_num, image_path=image_path,
                ))
    finally:
        doc.close()

    chapters = _blocks_to_chapters(all_blocks)
    if not chapters:
        # No chapter structure — fall back to plain text.
        from .ingest_pdf import ingest_pdf_file
        return ingest_pdf_file(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )

    textbook = Textbook(
        textbook_id=textbook_id, title=title,
        authors=authors or [], edition=edition,
        source_format="pdf",
        parser_quality=1.0,
        chapters=chapters,
    )
    _assign_real_pages(textbook)
    return textbook


def ingest_pdf_directory_hybrid(
    path,
    *,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
    vlm_extractor: Optional[VlmExtractor] = None,
    drawings_threshold: int = DEFAULT_DRAWINGS_THRESHOLD,
) -> Textbook:
    """Hybrid PDF ingestion across a directory of per-chapter PDFs.

    Mirrors :func:`src.textbook.ingest_pdf.ingest_pdf_directory` but
    routes each PDF through :func:`ingest_pdf_file_hybrid` so chapters
    are augmented with VLM-extracted visual content where flagged by
    the spatial router.
    """
    path = Path(path)
    pdf_files = sorted(
        (p for p in path.iterdir() if p.suffix.lower() == ".pdf"),
        key=_file_sort_key,
    )
    all_chapters: List[Chapter] = []
    for pf in pdf_files:
        sub = ingest_pdf_file_hybrid(
            pf, textbook_id=textbook_id, title=title,
            vlm_extractor=vlm_extractor,
            drawings_threshold=drawings_threshold,
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
