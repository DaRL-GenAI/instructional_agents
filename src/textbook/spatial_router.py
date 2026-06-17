"""Spatial object routing for PDF pages.

Reads PyMuPDF page metadata (drawings + images) to decide whether a
page contains complex visual content (figures, equations rendered as
vector graphics, diagrams) that PyMuPDF text extraction will
under-recover.

The router runs cheaply — it inspects PDF object metadata, not text —
so it can be applied to every page of a textbook before any expensive
extraction. Pages flagged ``complex`` are candidates for VLM-based
extraction; pages flagged ``prose`` can use the standard text path.

Routing thresholds were chosen empirically against two reference textbooks
(≈21 % and ≈13 % of pages classified complex). They are generic across
textbooks — no per-source tuning.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PageClass(str, Enum):
    """Classification result for a single page."""

    PROSE = "prose"
    COMPLEX = "complex"


# Default thresholds — empirically derived. A page is COMPLEX if it
# contains any embedded image OR more than this many vector drawing
# commands. The drawings threshold is conservative: page borders,
# bullet markers, and headings typically contribute well under 40
# drawings, so the threshold reliably distinguishes "figure / equation
# / diagram pages" from "plain prose pages with light typographic
# decoration". See data/exploration/comparison_report.md "Coverage
# gap" section for the empirical motivation.
DEFAULT_DRAWINGS_THRESHOLD = 40


@dataclass(frozen=True)
class PageRouting:
    """Routing decision plus the signals that produced it.

    Carrying the raw counts (rather than just the class) lets callers
    log per-page diagnostics or tune thresholds without re-inspecting
    the PDF.
    """

    page_index: int          # 0-indexed within its source PDF
    page_class: PageClass
    images: int              # len(page.get_images())
    drawings: int            # len(page.get_drawings())
    threshold_used: int

    @property
    def is_complex(self) -> bool:
        return self.page_class is PageClass.COMPLEX


def classify_page(
    page,
    *,
    drawings_threshold: int = DEFAULT_DRAWINGS_THRESHOLD,
    page_index: Optional[int] = None,
) -> PageRouting:
    """Classify a single PyMuPDF page as ``prose`` or ``complex``.

    Args:
        page: A ``pymupdf.Page`` (a.k.a. ``fitz.Page``) instance.
        drawings_threshold: Pages with more than this many drawing
            commands are flagged as complex.
        page_index: Optional zero-indexed page number for diagnostics.
            If omitted, ``page.number`` is used.

    Returns:
        :class:`PageRouting` carrying the decision and the raw counts.
    """
    images = len(page.get_images())
    drawings = len(page.get_drawings())
    is_complex = images > 0 or drawings > drawings_threshold
    return PageRouting(
        page_index=page_index if page_index is not None else page.number,
        page_class=PageClass.COMPLEX if is_complex else PageClass.PROSE,
        images=images,
        drawings=drawings,
        threshold_used=drawings_threshold,
    )


def classify_pdf(
    doc,
    *,
    drawings_threshold: int = DEFAULT_DRAWINGS_THRESHOLD,
) -> list[PageRouting]:
    """Classify every page of an open PDF document.

    Args:
        doc: A ``pymupdf.Document`` (a.k.a. ``fitz.Document``) instance.
        drawings_threshold: Forwarded to :func:`classify_page`.

    Returns:
        A list of :class:`PageRouting` records, one per page, in order.
    """
    return [
        classify_page(doc[i], drawings_threshold=drawings_threshold, page_index=i)
        for i in range(len(doc))
    ]


def summarise(routings: list[PageRouting]) -> dict:
    """Aggregate per-textbook stats from a list of page routings.

    Useful for the report's "source inventory" layer and for runtime
    cost estimation (count of complex pages → VLM call budget).
    """
    n_total = len(routings)
    n_complex = sum(1 for r in routings if r.is_complex)
    n_prose = n_total - n_complex
    total_images = sum(r.images for r in routings)
    total_drawings = sum(r.drawings for r in routings)
    return {
        "total_pages": n_total,
        "complex_pages": n_complex,
        "prose_pages": n_prose,
        "complex_percentage": (100.0 * n_complex / n_total) if n_total else 0.0,
        "total_embedded_images": total_images,
        "total_drawing_commands": total_drawings,
    }
