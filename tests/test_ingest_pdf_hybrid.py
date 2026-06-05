"""Tests for the hybrid PDF ingester (spatial router + paged + VLM).

Covers:
    1. Vanilla preservation: vlm_extractor=None → delegates to paged
       ingester with no behavior change.
    2. Block formatting helpers for each VLM component type.
    3. Inline markers (IMAGE_PATH, LATEX, etc.) appear in the rendered
       paragraph text so the slide generator can parse them.
    4. End-to-end: a mocked VLM returning structured components results
       in paragraphs with the right kind tags inside the Textbook IR.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.textbook.ingest_pdf_hybrid import (
    _algorithm_paragraph_text,
    _component_to_block,
    _components_to_blocks,
    _equation_paragraph_text,
    _figure_paragraph_text,
    _table_paragraph_text,
    ingest_pdf_file_hybrid,
)
from src.textbook.vlm_adapter import (
    AlgorithmComponent,
    EquationComponent,
    ExtractedPage,
    FigureComponent,
    TableComponent,
    VlmExtractor,
)


class TestRenderedParagraphText:
    def test_figure_text_includes_caption_description_insight_and_path(self):
        f = FigureComponent(
            label="Figure 10.16",
            caption="OPTICS terminology",
            description="Point p with core-distance circle.",
            pedagogical_point="Reach-dist combines core-dist and d(p,q).",
        )
        text = _figure_paragraph_text(f, image_path=Path("figures/han_p476.png"))
        assert "Figure 10.16" in text
        assert "OPTICS terminology" in text
        assert "[DESCRIPTION:" in text
        assert "[INSIGHT:" in text
        assert "[IMAGE_PATH: figures/han_p476.png]" in text

    def test_figure_text_omits_path_marker_when_no_image(self):
        f = FigureComponent(
            label="Figure 8.1",
            caption="caption",
            description="d",
            pedagogical_point="p",
        )
        text = _figure_paragraph_text(f, image_path=None)
        assert "[IMAGE_PATH:" not in text

    def test_equation_text_includes_latex_and_description(self):
        e = EquationComponent(
            label="(10.5)",
            latex=r"\sqrt{(p_x-q_x)^2 + (p_y-q_y)^2}",
            description="Euclidean distance",
        )
        text = _equation_paragraph_text(e)
        assert "(10.5)" in text
        assert "[LATEX:" in text
        assert r"\sqrt" in text
        assert "[DESCRIPTION: Euclidean distance]" in text

    def test_table_text_includes_pipe_delimited_table(self):
        t = TableComponent(
            label="Table 2.1",
            caption="Customer data",
            headers=["ID", "Age"],
            rows=[["1", "25"], ["2", "47"]],
        )
        text = _table_paragraph_text(t)
        assert "[TABLE:" in text
        assert "| ID | Age |" in text
        assert "| 1 | 25 |" in text
        assert "| 2 | 47 |" in text

    def test_algorithm_text_numbers_steps(self):
        a = AlgorithmComponent(
            label="Algorithm 8.2",
            name="k-means",
            steps=["Init centroids.", "Assign points.", "Recompute."],
        )
        text = _algorithm_paragraph_text(a)
        assert "Algorithm 8.2 k-means" in text
        assert "1. Init centroids." in text
        assert "2. Assign points." in text
        assert "3. Recompute." in text


class TestComponentToBlock:
    def test_figure_block_has_figure_cap_kind(self):
        f = FigureComponent(label="F1", caption="c", description="d",
                            pedagogical_point="p")
        blk = _component_to_block(f, page_num=42)
        assert blk["type"] == "paragraph"
        assert blk["kind"] == "figure_cap"
        assert blk["page"] == 42

    def test_equation_block_has_equation_kind(self):
        e = EquationComponent(label="(1)", latex="x=y", description="d")
        blk = _component_to_block(e, page_num=10)
        assert blk["kind"] == "equation"

    def test_table_block_has_example_kind(self):
        t = TableComponent(label="T1", caption="c",
                           headers=["A"], rows=[["1"]])
        blk = _component_to_block(t, page_num=5)
        assert blk["kind"] == "example"

    def test_algorithm_block_has_example_kind(self):
        a = AlgorithmComponent(label="A1", name="alg", steps=["one"])
        blk = _component_to_block(a, page_num=3)
        assert blk["kind"] == "example"

    def test_components_to_blocks_emits_one_per_component(self):
        extraction = ExtractedPage(components=[
            FigureComponent(label="F1", caption="c", description="d",
                            pedagogical_point="p"),
            EquationComponent(label="(1)", latex="x=y", description="d"),
        ])
        blocks = _components_to_blocks(extraction, page_num=7)
        assert len(blocks) == 2
        assert blocks[0]["kind"] == "figure_cap"
        assert blocks[1]["kind"] == "equation"
        assert all(b["page"] == 7 for b in blocks)


class TestVanillaPreservation:
    @patch("src.textbook.ingest_pdf_hybrid.ingest_pdf_file_paged")
    def test_no_extractor_delegates_to_paged(self, mock_paged):
        mock_paged.return_value = "sentinel"
        result = ingest_pdf_file_hybrid("/dummy.pdf", textbook_id="t",
                                       title="T", vlm_extractor=None)
        assert result == "sentinel"
        mock_paged.assert_called_once()


class TestHybridIngestion:
    @patch("src.textbook.ingest_pdf_hybrid.pymupdf")
    @patch("pymupdf4llm.to_markdown")
    def test_vlm_components_appear_as_paragraphs_in_ir(self, mock_md, mock_pymupdf):
        # Synthetic 2-page document: page 1 prose, page 2 complex.
        mock_md.return_value = [
            {"text": "## Chapter 1: Intro\n\nIntro paragraph."},
            {"text": "## 1.1 Methods\n\nSection prose paragraph."},
        ]
        # Mock the PyMuPDF doc so classify_page can distinguish prose
        # vs complex via images / drawings counts.
        prose_page = MagicMock()
        prose_page.get_images.return_value = []
        prose_page.get_drawings.return_value = []
        complex_page = MagicMock()
        complex_page.get_images.return_value = [object()]  # has image → complex
        complex_page.get_drawings.return_value = []
        mock_doc = MagicMock()
        mock_doc.__getitem__.side_effect = [prose_page, complex_page]
        mock_doc.__iter__.return_value = iter([prose_page, complex_page])
        mock_pymupdf.open.return_value = mock_doc

        # Mock the VLM extractor: returns an empty extraction for prose
        # pages (it should never be called for them) and a figure for
        # the complex one.
        extractor = MagicMock(spec=VlmExtractor)
        extractor.figures_dir = None
        extractor.extract.return_value = ExtractedPage(components=[
            FigureComponent(
                label="Figure 1.1", caption="Mock figure",
                description="A demonstration figure.",
                pedagogical_point="Pedagogical message.",
            ),
        ])

        tb = ingest_pdf_file_hybrid(
            "/dummy.pdf", textbook_id="t", title="T",
            vlm_extractor=extractor,
        )

        # Extractor should only have been called once — on the complex page.
        assert extractor.extract.call_count == 1
        # Walk the IR and find the figure paragraph
        all_paras = [p for ch in tb.chapters for s in ch.sections for p in s.paragraphs]
        figure_paras = [p for p in all_paras if p.kind == "figure_cap"]
        assert len(figure_paras) == 1
        assert "Figure 1.1" in figure_paras[0].text
        # The figure paragraph should sit on page 2 (the complex page)
        assert figure_paras[0].page == 2

    @patch("src.textbook.ingest_pdf_hybrid.pymupdf")
    @patch("pymupdf4llm.to_markdown")
    def test_prose_pages_skip_vlm_call(self, mock_md, mock_pymupdf):
        # All pages prose → extractor.extract should never be called.
        mock_md.return_value = [
            {"text": "## Chapter 1\n\nP1."},
            {"text": "P2."},
            {"text": "P3."},
        ]
        prose_page = MagicMock()
        prose_page.get_images.return_value = []
        prose_page.get_drawings.return_value = []
        mock_doc = MagicMock()
        mock_doc.__getitem__.return_value = prose_page
        mock_pymupdf.open.return_value = mock_doc

        extractor = MagicMock(spec=VlmExtractor)
        extractor.figures_dir = None
        extractor.extract.return_value = ExtractedPage()

        ingest_pdf_file_hybrid(
            "/dummy.pdf", textbook_id="t", title="T",
            vlm_extractor=extractor,
        )
        assert extractor.extract.call_count == 0
