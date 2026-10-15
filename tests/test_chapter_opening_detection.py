"""Tests for chapter-boundary detection in pdf-markdown heading
normalisation.

Covers the three protections added around chapter promotion: page-top
"Title N" opening detection (display-numeral layouts where the chapter
number is printed beside the title instead of "Chapter N"), suppression
of TOC entries (chapter headings carrying a trailing page number), and
dedup of running headers that repeat an already-promoted chapter number.
"""

from src.textbook.ingest_pdf import (
    HeadingState,
    _normalize_pdf_markdown_headings,
)
from src.textbook.ingest_pdf_paged import _extract_blocks_with_page

# Digit-free running prose long enough to pass the body-prose check.
PROSE = (
    "Real-world databases are highly susceptible to noisy, missing, "
    "and inconsistent records due to their typically huge size and "
    "their likely origin from multiple heterogenous sources. "
    "Low-quality inputs will lead to low-quality mining results, and "
    "careful preparation of the material is therefore the first step "
    "of any serious analysis effort undertaken at scale."
)

# Digit-dense TOC-style text: the same length but full of page numbers.
TOC_TEXT = (
    "1.1 What Is This About 5 1.1.1 Early History 6 1.1.2 Later Work 9 "
    "1.2 Kinds of Records 13 1.2.1 Flat Files 14 1.2.2 Stores 17 "
    "1.3 Functionality 21 1.3.1 Descriptions 22 1.3.2 Associations 25 "
    "1.4 Which Technologies 29 1.4.1 Statistics 30 1.4.2 Learning 33 "
    "1.5 Which Kinds of Uses 37 1.5.1 Business 38 1.5.2 Science 41"
)


class TestTitleNumberOpening:
    def test_page_top_opening_promotes_with_synthesized_title(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={1, 2}, max_number=2)
        md = "## **Data Preprocessing 3** \n\n" + PROSE
        out, seen = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert out.splitlines()[0] == "# Chapter 3 Data Preprocessing"
        assert seen is True
        assert 3 in state.promoted_numbers
        assert state.max_number == 3

    def test_number_embedded_mid_title(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={5}, max_number=5)
        md = ("## **Mining Frequent Patterns, Associations, and "
              "Correlations: 6 Basic Concepts and Methods** \n\n" + PROSE)
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert out.splitlines()[0] == (
            "# Chapter 6 Mining Frequent Patterns, Associations, and "
            "Correlations: Basic Concepts and Methods")

    def test_first_chapter_promotes_from_empty_state(self):
        state = HeadingState()
        md = "## **Introduction 1** \n\n" + PROSE
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert out.splitlines()[0] == "# Chapter 1 Introduction"

    def test_out_of_sequence_number_not_promoted(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={1, 2}, max_number=2)
        md = "## **Data Cube Technology 5** \n\n" + PROSE
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert out.splitlines()[0].startswith("### ")

    def test_not_at_page_top_not_promoted(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={2}, max_number=2)
        md = "Some earlier text on the page.\n## **Data Preprocessing 3** \n\n" + PROSE
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert "# Chapter 3" not in out

    def test_without_page_start_not_promoted(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={2}, max_number=2)
        md = "## **Data Preprocessing 3** \n\n" + PROSE
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=False)
        assert "# Chapter 3" not in out

    def test_digit_dense_following_text_blocks_promotion(self):
        state = HeadingState()
        md = "## **Introduction 1** \n\n" + TOC_TEXT
        out, _ = _normalize_pdf_markdown_headings(
            md, state=state, page_start=True)
        assert "# Chapter 1" not in out
        assert not state.promoted_numbers


class TestChapterKeywordSuppression:
    def test_toc_entry_with_trailing_page_number_demoted(self):
        state = HeadingState()
        md = ("## Chapter 4 **Data Warehousing and Online Analytical "
              "Processing 125** ")
        out, seen = _normalize_pdf_markdown_headings(md, state=state)
        assert out.splitlines()[0].startswith("### ")
        assert seen is False
        assert not state.promoted_numbers

    def test_bare_chapter_heading_without_title_still_promotes(self):
        state = HeadingState()
        out, seen = _normalize_pdf_markdown_headings(
            "## Chapter 12\nbody", state=state)
        assert out.splitlines()[0] == "# Chapter 12"
        assert seen is True
        assert 12 in state.promoted_numbers

    def test_running_header_repeat_demoted(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={3}, max_number=3)
        out, _ = _normalize_pdf_markdown_headings(
            "## Chapter 3 Data Preprocessing\nbody", state=state)
        assert out.splitlines()[0].startswith("### ")

    def test_fresh_chapter_number_still_promotes(self):
        state = HeadingState(seen_chapter=True,
                             promoted_numbers={3}, max_number=3)
        out, _ = _normalize_pdf_markdown_headings(
            "## Chapter 4 Data Warehousing\nbody", state=state)
        assert out.splitlines()[0] == "# Chapter 4 Data Warehousing"
        assert state.max_number == 4


class TestPagedThreading:
    def test_successive_opening_pages_become_successive_chapters(self):
        state = HeadingState()
        page_1 = "## **Introduction 1** \n\n" + PROSE
        page_2 = "## **Getting to Know Your Data 2** \n\n" + PROSE
        blocks_1, seen_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False, state=state)
        blocks_2, _ = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_1, state=state)
        h1_titles = [b["title"] for b in blocks_1 + blocks_2
                     if b["type"] == "heading" and b["level"] == 1]
        assert h1_titles == ["Chapter 1 Introduction",
                             "Chapter 2 Getting to Know Your Data"]

    def test_opening_then_running_header_yields_one_chapter(self):
        state = HeadingState()
        page_1 = "## **Introduction 1** \n\n" + PROSE
        page_2 = "## Chapter 1 Introduction\n\n" + PROSE
        blocks_1, seen_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False, state=state)
        blocks_2, _ = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_1, state=state)
        h1_count = sum(1 for b in blocks_1 + blocks_2
                       if b["type"] == "heading" and b["level"] == 1)
        assert h1_count == 1


class TestLegacyBoolSignature:
    def test_bool_only_call_unchanged(self):
        out, seen = _normalize_pdf_markdown_headings(
            "## First Heading\nbody", seen_chapter=False)
        assert out.startswith("# First Heading")
        assert seen is True
