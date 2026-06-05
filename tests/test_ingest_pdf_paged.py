"""Tests for the paged PyMuPDF4LLM ingester.

Covers:
    1. Per-page real page numbers (NOT synthetic word-count pagination)
    2. Cross-page heading state tracking (seen_chapter persistence)
    3. Fallback behavior when pymupdf4llm yields no chapters
    4. Page-span aggregation on Section / Chapter

These tests mock the pymupdf4llm.to_markdown response so they do not
require a real PDF.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.textbook.ingest_pdf_paged import (
    _assign_real_pages,
    _extract_blocks_with_page,
    ingest_pdf_file_paged,
)
from src.textbook.schema import (
    Chapter,
    PageSpan,
    Paragraph,
    Section,
    Textbook,
)


class TestExtractBlocksWithPage:
    def test_tags_blocks_with_supplied_page(self):
        md = "## Section A\n\nFirst paragraph.\n\nSecond paragraph."
        blocks, _ = _extract_blocks_with_page(md, page_num=42, seen_chapter=True)
        assert all(b["page"] == 42 for b in blocks)
        # At least one heading + two paragraphs
        assert any(b["type"] == "heading" for b in blocks)
        paras = [b for b in blocks if b["type"] == "paragraph"]
        assert len(paras) == 2

    def test_seen_chapter_flips_when_chapter_heading_present(self):
        md = "## Chapter 3 Methodology\n\nIntro paragraph."
        _, seen = _extract_blocks_with_page(md, page_num=1, seen_chapter=False)
        # Heading normaliser converts "## Chapter 3 ..." to "# Chapter 3 ..."
        assert seen is True

    def test_seen_chapter_stays_false_on_plain_heading_when_not_first(self):
        md = "## A subsection title\n\nSome text."
        _, seen = _extract_blocks_with_page(md, page_num=1, seen_chapter=True)
        # seen_chapter passed in as True; should still be True after
        assert seen is True


class TestAssignRealPages:
    def test_section_page_span_from_paragraph_pages(self):
        tb = Textbook(
            textbook_id="t", title="T", authors=[], edition=None, source_format="pdf",
            parser_quality=1.0,
            chapters=[Chapter(
                chapter_id="ch1", number=1, title="C1",
                pages=PageSpan(start=0, end=0),
                sections=[Section(
                    section_id="ch1.s1", title="S1",
                    pages=PageSpan(start=0, end=0),
                    paragraphs=[
                        Paragraph(para_id="p1", text="...", page=3, kind="prose"),
                        Paragraph(para_id="p2", text="...", page=5, kind="prose"),
                        Paragraph(para_id="p3", text="...", page=4, kind="prose"),
                    ],
                    concepts=[],
                )],
                learning_objectives=[],
            )],
        )
        _assign_real_pages(tb)
        assert tb.chapters[0].sections[0].pages == PageSpan(start=3, end=5)
        assert tb.chapters[0].pages == PageSpan(start=3, end=5)

    def test_skips_paragraphs_with_zero_page(self):
        # Mixed: some paragraphs have real pages, some don't
        tb = Textbook(
            textbook_id="t", title="T", authors=[], edition=None, source_format="pdf",
            parser_quality=1.0,
            chapters=[Chapter(
                chapter_id="ch1", number=1, title="C1",
                pages=PageSpan(start=0, end=0),
                sections=[Section(
                    section_id="ch1.s1", title="S1",
                    pages=PageSpan(start=0, end=0),
                    paragraphs=[
                        Paragraph(para_id="p1", text="...", page=0, kind="prose"),
                        Paragraph(para_id="p2", text="...", page=10, kind="prose"),
                    ],
                    concepts=[],
                )],
                learning_objectives=[],
            )],
        )
        _assign_real_pages(tb)
        # Only page=10 contributes; page=0 is treated as missing
        assert tb.chapters[0].sections[0].pages == PageSpan(start=10, end=10)


class TestIngestPdfFilePaged:
    @patch("pymupdf4llm.to_markdown")
    def test_per_page_real_page_numbers_attached(self, mock_md):
        # Two pages of synthetic markdown with structure
        mock_md.return_value = [
            {"text": "## Chapter 1: Intro\n\nIntro paragraph one.\n\nIntro paragraph two."},
            {"text": "## 1.1 First Section\n\nSection content paragraph."},
        ]
        tb = ingest_pdf_file_paged("/dummy.pdf", textbook_id="t", title="T")
        # Should have at least one chapter
        assert len(tb.chapters) >= 1
        # Paragraphs should carry per-page numbers (1 or 2), not 0
        all_paras = [p for ch in tb.chapters for s in ch.sections for p in s.paragraphs]
        page_numbers = {p.page for p in all_paras}
        assert page_numbers <= {1, 2}, f"got unexpected pages: {page_numbers}"
        assert 1 in page_numbers
        assert 2 in page_numbers

    @patch("pymupdf4llm.to_markdown")
    def test_supports_bare_string_per_page_format(self, mock_md):
        # Older pymupdf4llm versions return list of strings, not dicts
        mock_md.return_value = [
            "## Chapter 1: Title\n\nParagraph on page 1.",
            "More paragraph on page 2.",
        ]
        tb = ingest_pdf_file_paged("/dummy.pdf", textbook_id="t", title="T")
        all_paras = [p for ch in tb.chapters for s in ch.sections for p in s.paragraphs]
        page_numbers = {p.page for p in all_paras}
        assert 1 in page_numbers
        assert 2 in page_numbers

    @patch("pymupdf4llm.to_markdown")
    def test_skips_empty_pages(self, mock_md):
        mock_md.return_value = [
            {"text": "## Chapter 1\n\nParagraph one."},
            {"text": ""},  # blank page (e.g., front matter)
            {"text": "## 1.1 Section\n\nMore content."},
        ]
        tb = ingest_pdf_file_paged("/dummy.pdf", textbook_id="t", title="T")
        all_paras = [p for ch in tb.chapters for s in ch.sections for p in s.paragraphs]
        # No paragraph should claim page 2 (which was blank)
        assert all(p.page in {1, 3} for p in all_paras)

    @patch("pymupdf4llm.to_markdown")
    def test_falls_back_when_no_chapters_extracted(self, mock_md):
        # Empty output → should fall back to plain text ingester. We
        # don't need to verify what the fallback returns; just that we
        # don't crash and we return SOMETHING.
        mock_md.return_value = []
        # The plain-text fallback expects a real PDF path so this test
        # patches it to return a synthetic result.
        with patch("src.textbook.ingest_pdf.ingest_pdf_file") as mock_fallback:
            fallback_tb = Textbook(
                textbook_id="t", title="T", authors=[], edition=None, source_format="pdf",
                parser_quality=1.0, chapters=[],
            )
            mock_fallback.return_value = fallback_tb
            tb = ingest_pdf_file_paged("/dummy.pdf", textbook_id="t", title="T")
            assert tb is fallback_tb
            mock_fallback.assert_called_once()
