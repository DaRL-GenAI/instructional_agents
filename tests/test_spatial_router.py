"""Tests for the spatial-object page router.

Covers:
    1. The class-level distinction (prose vs complex) on synthetic
       PyMuPDF pages (mocked) so the unit tests do not depend on a
       real PDF.
    2. The threshold boundary cases (drawings exactly at, just above,
       just below).
    3. Image-only triggering complex regardless of drawings count.
    4. The aggregation helpers.
"""

from unittest.mock import MagicMock

from src.textbook.spatial_router import (
    DEFAULT_DRAWINGS_THRESHOLD,
    PageClass,
    PageRouting,
    classify_page,
    classify_pdf,
    summarise,
)


def _mock_page(*, images: int = 0, drawings: int = 0, number: int = 0):
    """Build a mock PyMuPDF page with the given metadata counts."""
    page = MagicMock()
    page.number = number
    page.get_images.return_value = [object()] * images
    page.get_drawings.return_value = [object()] * drawings
    return page


class TestClassifyPage:
    def test_plain_prose_page_classified_as_prose(self):
        page = _mock_page(images=0, drawings=10)
        r = classify_page(page)
        assert r.page_class is PageClass.PROSE
        assert not r.is_complex

    def test_page_with_any_image_classified_as_complex(self):
        page = _mock_page(images=1, drawings=0)
        r = classify_page(page)
        assert r.page_class is PageClass.COMPLEX
        assert r.is_complex

    def test_drawings_at_threshold_classified_as_prose(self):
        page = _mock_page(images=0, drawings=DEFAULT_DRAWINGS_THRESHOLD)
        r = classify_page(page)
        assert r.page_class is PageClass.PROSE

    def test_drawings_just_above_threshold_classified_as_complex(self):
        page = _mock_page(images=0, drawings=DEFAULT_DRAWINGS_THRESHOLD + 1)
        r = classify_page(page)
        assert r.page_class is PageClass.COMPLEX

    def test_routing_carries_raw_counts(self):
        page = _mock_page(images=3, drawings=42, number=7)
        r = classify_page(page)
        assert r.images == 3
        assert r.drawings == 42
        assert r.page_index == 7
        assert r.threshold_used == DEFAULT_DRAWINGS_THRESHOLD

    def test_custom_threshold_can_relax_or_tighten(self):
        page = _mock_page(images=0, drawings=30)
        # Default threshold 40 → prose
        assert classify_page(page).page_class is PageClass.PROSE
        # Custom tighter threshold 20 → complex
        r = classify_page(page, drawings_threshold=20)
        assert r.page_class is PageClass.COMPLEX
        assert r.threshold_used == 20

    def test_explicit_page_index_overrides_number(self):
        page = _mock_page(number=99)
        r = classify_page(page, page_index=5)
        assert r.page_index == 5


class TestClassifyPdf:
    def test_iterates_every_page_in_order(self):
        pages = [
            _mock_page(images=0, drawings=10, number=0),
            _mock_page(images=1, drawings=0, number=1),
            _mock_page(images=0, drawings=50, number=2),
            _mock_page(images=0, drawings=0, number=3),
        ]
        doc = MagicMock()
        doc.__len__.return_value = len(pages)
        doc.__getitem__.side_effect = lambda i: pages[i]
        routings = classify_pdf(doc)
        assert len(routings) == 4
        assert [r.page_class for r in routings] == [
            PageClass.PROSE,
            PageClass.COMPLEX,
            PageClass.COMPLEX,
            PageClass.PROSE,
        ]
        assert [r.page_index for r in routings] == [0, 1, 2, 3]


class TestSummarise:
    def test_summarise_aggregates_counts_and_percentage(self):
        routings = [
            PageRouting(0, PageClass.PROSE, images=0, drawings=10,
                        threshold_used=DEFAULT_DRAWINGS_THRESHOLD),
            PageRouting(1, PageClass.COMPLEX, images=2, drawings=0,
                        threshold_used=DEFAULT_DRAWINGS_THRESHOLD),
            PageRouting(2, PageClass.COMPLEX, images=0, drawings=80,
                        threshold_used=DEFAULT_DRAWINGS_THRESHOLD),
            PageRouting(3, PageClass.PROSE, images=0, drawings=5,
                        threshold_used=DEFAULT_DRAWINGS_THRESHOLD),
        ]
        out = summarise(routings)
        assert out["total_pages"] == 4
        assert out["complex_pages"] == 2
        assert out["prose_pages"] == 2
        assert out["complex_percentage"] == 50.0
        assert out["total_embedded_images"] == 2
        assert out["total_drawing_commands"] == 95

    def test_summarise_handles_empty_input(self):
        out = summarise([])
        assert out["total_pages"] == 0
        assert out["complex_percentage"] == 0.0
