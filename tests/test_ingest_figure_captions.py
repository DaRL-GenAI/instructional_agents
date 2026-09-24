"""Tests for figure-caption binding at PDF ingest.

The paged ingester previously emitted bare ``[IMAGE_PATH: ...]`` markers,
discarding the figure/caption adjacency that exists on the page. Now each
extracted image is paired (reading order) with the page's i-th ``Figure N.M``
caption so the figure paragraph carries its real caption text — what downstream
figure<->slide matching and figure-query retrieval read. Inline references
("see Figure 10.14") must NOT be mistaken for captions.
"""

from __future__ import annotations

from src.textbook.ingest_pdf_paged import _extract_figure_captions, _MD_IMAGE_REF_RE


class TestMarkdownImageStrip:
    def test_strips_image_ref_keeps_surrounding_text(self):
        t = "Some text ![](my_textbook.pdf-0006-05.png) more text."
        assert _MD_IMAGE_REF_RE.sub("", t) == "Some text  more text."

    def test_image_only_paragraph_becomes_empty(self):
        assert _MD_IMAGE_REF_RE.sub("", "![alt text](x.png)").strip() == ""

    def test_leaves_prose_untouched(self):
        t = "Figure 10.14 shows the DBSCAN result on the spatial dataset."
        assert _MD_IMAGE_REF_RE.sub("", t) == t


class TestExtractFigureCaptions:
    def test_extracts_numbered_captions_in_reading_order(self):
        md = (
            "Some prose about clustering.\n"
            "Figure 10.14 A density-based clustering produced by DBSCAN.\n"
            "More body text here.\n"
            "**Figure 10.17:** OPTICS reachability plot.\n"
        )
        caps = _extract_figure_captions(md)
        assert caps == [
            ("10.14", "A density-based clustering produced by DBSCAN."),
            ("10.17", "OPTICS reachability plot."),
        ]

    def test_strips_markdown_markers(self):
        caps = _extract_figure_captions("**Figure 8.2** *Decision tree* for the example.")
        assert caps[0][0] == "8.2"
        assert "Decision tree" in caps[0][1]
        assert "*" not in caps[0][1]

    def test_inline_reference_not_treated_as_caption(self):
        # mid-line "see Figure 10.14" is a reference, not a caption -> ignored
        caps = _extract_figure_captions("As we saw in Figure 10.14 the clusters merge.")
        assert caps == []

    def test_single_integer_figure_number(self):
        caps = _extract_figure_captions("Figure 3 Overview of the data mining process.")
        assert caps[0][0] == "3"
        assert caps[0][1].startswith("Overview")

    def test_no_figures_returns_empty(self):
        assert _extract_figure_captions("Just prose, no figures here.") == []
        assert _extract_figure_captions("") == []
