"""Tests for `Textbook.toc()` — the formatted TOC string injected into
foundation deliberation prompts to anchor course structure to the source.

Covers the formatting contract (chapter titles + nested sections), the
word-budget degradation (drop sections first, then truncate chapter list),
and the "Untitled chapter" placeholder filtering that keeps slide-deck
ingestion from spamming the prompt with noise.
"""

from __future__ import annotations

from src.textbook.schema import (
    Chapter,
    PageSpan,
    Paragraph,
    Section,
    Textbook,
)


def _para(idx: int, page: int = 1) -> Paragraph:
    return Paragraph(
        para_id=f"ch{idx}.s1.p1",
        text=f"placeholder paragraph {idx}",
        page=page,
        kind="prose",
    )


def _section(chapter_num: int, section_num: int, title: str,
             page_start: int = 1, page_end: int = 1) -> Section:
    return Section(
        section_id=f"ch{chapter_num}.s{section_num}",
        title=title,
        pages=PageSpan(start=page_start, end=page_end),
        paragraphs=[_para(chapter_num)],
        concepts=[],
    )


def _chapter(num: int, title: str, sections: list[Section] | None = None) -> Chapter:
    sections = sections or [_section(num, 1, f"Section {num}.1")]
    return Chapter(
        chapter_id=f"ch{num}",
        number=num,
        title=title,
        pages=PageSpan(start=1, end=10),
        sections=sections,
        learning_objectives=[],
    )


def _textbook(chapters: list[Chapter], textbook_id: str = "test") -> Textbook:
    return Textbook(
        textbook_id=textbook_id,
        title="Test Textbook",
        authors=["A"],
        edition=None,
        source_format="pdf",
        parser_quality=1.0,
        chapters=chapters,
    )


class TestTocFormatting:
    def test_empty_textbook_returns_empty_string(self):
        tb = _textbook([])
        assert tb.toc() == ""

    def test_basic_format_has_chapter_and_sections(self):
        tb = _textbook([
            _chapter(2, "Getting to Know Your Data", [
                _section(2, 1, "Data Objects and Attribute Types"),
                _section(2, 2, "Basic Statistical Descriptions"),
            ]),
            _chapter(3, "Data Preprocessing", [
                _section(3, 1, "Data Cleaning"),
            ]),
        ])
        toc = tb.toc(word_budget=200)
        assert "Chapter 2: Getting to Know Your Data" in toc
        assert "ch2.s1 Data Objects and Attribute Types" in toc
        assert "ch2.s2 Basic Statistical Descriptions" in toc
        assert "Chapter 3: Data Preprocessing" in toc
        assert "ch3.s1 Data Cleaning" in toc

    def test_sections_indented_under_chapter(self):
        tb = _textbook([_chapter(1, "Intro", [_section(1, 1, "Welcome")])])
        toc = tb.toc()
        lines = toc.splitlines()
        # First line is the chapter, second line is an indented section bullet
        assert lines[0].startswith("Chapter ")
        assert lines[1].startswith("  - ")


class TestWordBudgetDegradation:
    """When the TOC would overflow the prompt budget, sections degrade first
    (we keep all chapter titles), and only when chapter titles ALONE still
    overflow do we truncate the chapter list with an ellipsis line.
    """

    def test_sections_dropped_when_over_budget(self):
        # Many short sections under a few chapters — chapter titles fit, but
        # sections will spill over a tight budget.
        many_sections = [_section(1, i, f"Section title {i} that uses several words for budget")
                         for i in range(1, 30)]
        tb = _textbook([_chapter(1, "Wide chapter", many_sections)])
        toc = tb.toc(word_budget=20)
        assert "Chapter 1: Wide chapter" in toc
        # Some sections may fit, but not all 29; check we capped it.
        assert toc.count("ch1.s") < 29

    def test_chapter_list_truncated_when_titles_alone_overflow(self):
        # Many chapters, each title long enough that even the chapter list
        # blows the budget. The truncated form ends with an ellipsis line.
        chapters = [_chapter(i, f"Chapter title number {i} with extra padding words")
                    for i in range(1, 40)]
        tb = _textbook(chapters)
        toc = tb.toc(word_budget=30)
        assert "more chapters" in toc  # ellipsis line present
        # Some chapters omitted entirely from the listing.
        assert toc.count("Chapter ") < 40


class TestUntitledChapterFiltering:
    """Slide-deck ingestion produces 'Untitled chapter' placeholders when
    heading detection fails. Showing the model five "Untitled chapter" lines
    is noise — filter them out when there are real titles to fall back on,
    but never end up with an empty TOC.
    """

    def test_untitled_chapters_filtered_when_real_titles_present(self):
        tb = _textbook([
            _chapter(1, "Real Chapter One"),
            _chapter(2, "Untitled chapter"),
            _chapter(3, "Real Chapter Three"),
        ])
        toc = tb.toc()
        assert "Real Chapter One" in toc
        assert "Real Chapter Three" in toc
        assert "Untitled chapter" not in toc

    def test_all_untitled_falls_back_to_showing_them(self):
        # SVVT scenario: heading detector produced "Untitled chapter" for
        # every PDF in the directory. Don't return an empty TOC — show the
        # placeholders so the deliberation at least sees the chapter count.
        tb = _textbook([_chapter(i, "Untitled chapter") for i in range(1, 4)])
        toc = tb.toc()
        assert toc != ""
        assert toc.count("Untitled chapter") == 3
