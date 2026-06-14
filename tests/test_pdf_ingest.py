"""Tests for the PDF textbook ingester.

Layer 1 — a small labeled PDF fixture (tests/fixtures/mini_textbook.pdf) with
known structure, plus unit tests of the heading / classification helpers.

Layer 2 — optional smoke tests against the real eval PDFs if present
locally; these skip cleanly when absent.
"""

import re
from pathlib import Path

import pytest

from src.textbook.ingest_pdf import (
    _classify_pdf_paragraph,
    _file_sort_key,
    _heading_level,
    _merge_split_headings,
    _merge_wrapped_headings,
    ingest_pdf_directory,
    ingest_pdf_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"
AGENTIC = (PROJECT_ROOT / "data" / "repos" / "agentic_design_patterns"
           / "Agentic_Design_Patterns.pdf")
HAN_DIR = PROJECT_ROOT / "data" / "textbooks" / "han_data_mining_3e"

PARA_ID_RE = re.compile(r"^ch\d+\.s\d+\.p\d{2}$")


class TestHeadingLevel:
    """Unit tests for _heading_level — the core heading detector."""

    def test_chapter_word_is_level_1(self):
        assert _heading_level("Chapter 3: Parallelization", 26.0, 12.0, [26.0, 20.0]) == 1

    def test_appendix_is_level_1(self):
        assert _heading_level("Appendix A: Advanced Prompting", 24.0, 12.0, [24.0]) == 1

    def test_structural_title_is_level_1(self):
        assert _heading_level("Glossary", 26.0, 12.0, [26.0, 20.0]) == 1

    def test_giant_bare_number_is_level_1(self):
        assert _heading_level("3", 119.0, 10.0, [119.0, 20.0]) == 1

    def test_numbered_section_is_level_2(self):
        assert _heading_level("3.2 Data Cleaning", 14.0, 10.0, [35.0, 14.0, 13.0]) == 2

    def test_numbered_subsection_is_level_3(self):
        assert _heading_level("3.2.1 Missing Values", 13.0, 10.0, [35.0, 14.0, 13.0]) == 3

    def test_size_fallback_section(self):
        # no number, but a heading-tier size -> section
        assert _heading_level("Parallelization Pattern Overview", 20.0, 12.0,
                              [26.0, 20.0]) == 2

    def test_body_sized_line_is_not_a_heading(self):
        # size gate: not bigger than body -> None
        assert _heading_level("just a normal sentence of body text", 10.0, 10.0,
                              [20.0]) is None

    def test_small_bare_number_is_not_a_heading(self):
        # a page-number-sized "47" must not become a chapter
        assert _heading_level("47", 11.0, 10.0, [20.0]) is None

    def test_long_line_is_not_a_heading(self):
        # length gate: flowing prose at heading size is still not a heading
        long = "Chapter 1: Prompt Chaining (code), 12 pages [final, last read done] and more"
        assert _heading_level(long, 12.0, 11.0, [20.0]) is None

    def test_body_text_chapter_mention_rejected(self):
        # "In Chapter 2, we saw..." at body size must not match
        assert _heading_level("Chapter 2, we saw how this works", 10.0, 10.0,
                              [20.0]) is None


class TestClassifyPdfParagraph:
    """Unit tests for _classify_pdf_paragraph."""

    def test_math_heavy_is_equation(self):
        assert _classify_pdf_paragraph("garbled math symbols", 0.6) == "equation"

    def test_figure_caption(self):
        assert _classify_pdf_paragraph("Figure 3.2 A decision tree.", 0.0) == "figure_cap"

    def test_table_caption(self):
        assert _classify_pdf_paragraph("Table 1 Summary of results", 0.0) == "figure_cap"

    def test_example_prefix(self):
        assert _classify_pdf_paragraph("Example 3.1 shows the idea.", 0.0) == "example"

    def test_plain_prose(self):
        assert _classify_pdf_paragraph("This is an ordinary sentence.", 0.0) == "prose"


class TestMergeHelpers:
    """Unit tests for the two heading-merge passes."""

    def test_merge_split_number_and_title(self):
        blocks = [
            {"type": "heading", "level": 2, "title": "3.2", "page": 6},
            {"type": "heading", "level": 3, "title": "Data Cleaning", "page": 6},
            {"type": "paragraph", "kind": "prose", "text": "body", "page": 6},
        ]
        out = _merge_split_headings(blocks)
        assert len(out) == 2
        assert out[0]["title"] == "3.2 Data Cleaning"
        assert out[0]["level"] == 2  # keeps the number-derived level

    def test_merge_wrapped_level_1_titles(self):
        blocks = [
            {"type": "heading", "level": 1,
             "title": "Chapter 12: Exception Handling and", "page": 196},
            {"type": "heading", "level": 1, "title": "Recovery", "page": 196},
            {"type": "paragraph", "kind": "prose", "text": "body", "page": 196},
        ]
        out = _merge_wrapped_headings(blocks)
        assert len(out) == 2
        assert out[0]["title"] == "Chapter 12: Exception Handling and Recovery"

    def test_wrapped_merge_only_same_page(self):
        blocks = [
            {"type": "heading", "level": 1, "title": "Chapter 1: A", "page": 5},
            {"type": "heading", "level": 1, "title": "Chapter 2: B", "page": 9},
        ]
        out = _merge_wrapped_headings(blocks)
        assert len(out) == 2  # different pages -> not merged


class TestFileSortKey:
    """Leading-number file ordering (so "2---" sorts before "10---")."""

    def test_numeric_order(self):
        files = [Path("10---x.pdf"), Path("2---y.pdf"), Path("9---z.pdf")]
        ordered = sorted(files, key=_file_sort_key)
        assert [p.name[:2].strip("-") for p in ordered] == ["2", "9", "10"]


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf fixture missing")
class TestIngestFixture:
    """Layer 1 — the labeled mini PDF fixture (known structure)."""

    def _tb(self):
        return ingest_pdf_file(FIXTURE, textbook_id="mini", title="Mini")

    def test_two_chapters(self):
        assert len(self._tb().chapters) == 2

    def test_chapter_titles(self):
        titles = [c.title for c in self._tb().chapters]
        assert "Chapter 1: Foundations" in titles
        assert "Chapter 2: Control Flow" in titles

    def test_section_counts(self):
        tb = self._tb()
        assert len(tb.chapters[0].sections) == 2  # 1.1 Numbers, 1.2 Operators
        assert len(tb.chapters[1].sections) == 1  # 2.1 Conditionals

    def test_section_titles(self):
        sec_titles = [s.title for c in self._tb().chapters for s in c.sections]
        assert any("Numbers" in t for t in sec_titles)
        assert any("Operators" in t for t in sec_titles)
        assert any("Conditionals" in t for t in sec_titles)

    def test_source_format_is_pdf(self):
        assert self._tb().source_format == "pdf"

    def test_parser_quality_high(self):
        assert self._tb().parser_quality >= 0.95

    def test_paragraph_ids_well_formed(self):
        for c in self._tb().chapters:
            for s in c.sections:
                for p in s.paragraphs:
                    assert PARA_ID_RE.match(p.para_id), p.para_id

    def test_pages_are_real_and_positive(self):
        for c in self._tb().chapters:
            for s in c.sections:
                for p in s.paragraphs:
                    assert p.page >= 1


@pytest.mark.skipif(not AGENTIC.exists(), reason="Agentic Design Patterns PDF not present")
class TestIngestAgentic:
    """Layer 2 — real whole-book PDF (Agentic Design Patterns)."""

    def test_finds_all_21_chapters(self):
        tb = ingest_pdf_file(AGENTIC, textbook_id="agentic", title="Agentic")
        chapter_titled = [c for c in tb.chapters
                          if c.title.lower().startswith("chapter ")]
        assert len(chapter_titled) >= 21

    def test_parser_quality_high(self):
        tb = ingest_pdf_file(AGENTIC, textbook_id="agentic", title="Agentic")
        assert tb.parser_quality > 0.9

    def test_no_runaway_chapter_count(self):
        # heading detection must not explode on the glossary / back matter
        tb = ingest_pdf_file(AGENTIC, textbook_id="agentic", title="Agentic")
        assert len(tb.chapters) < 60


@pytest.mark.skipif(not HAN_DIR.exists(), reason="Han chapter PDFs not present")
class TestIngestHanDirectory:
    """Layer 2 — real one-chapter-per-file PDFs from the local data dir."""

    def test_six_chapters(self):
        tb = ingest_pdf_directory(HAN_DIR, textbook_id="han", title="External Textbook")
        assert len(tb.chapters) == 6

    def test_chapters_in_numeric_order(self):
        tb = ingest_pdf_directory(HAN_DIR, textbook_id="han", title="External Textbook")
        # filenames lead with 2,3,6,8,9,10 — chapter titles should start likewise
        leading = [c.title.split()[0] for c in tb.chapters]
        assert leading == ["2", "3", "6", "8", "9", "10"]

    def test_every_chapter_has_sections(self):
        tb = ingest_pdf_directory(HAN_DIR, textbook_id="han", title="External Textbook")
        for c in tb.chapters:
            assert len(c.sections) >= 1

    def test_paragraph_ids_unique(self):
        tb = ingest_pdf_directory(HAN_DIR, textbook_id="han", title="External Textbook")
        ids = [p.para_id for c in tb.chapters for s in c.sections for p in s.paragraphs]
        assert len(ids) == len(set(ids))
