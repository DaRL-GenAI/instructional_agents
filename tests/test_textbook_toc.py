"""Tests for `Textbook.toc()` — the formatted TOC string injected into
foundation deliberation prompts to anchor course structure to the source.

Covers the formatting contract (chapter titles + nested sections), the
word-budget degradation (drop sections first, then truncate chapter list),
and the "Untitled chapter" placeholder filtering that keeps slide-deck
ingestion from spamming the prompt with noise.
"""

from __future__ import annotations

import pytest

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
             page_start: int = 1, page_end: int = 1,
             n_paragraphs: int = 6) -> Section:
    # Default to 6 paragraphs per section so the chapter clears the
    # `_MIN_PARAGRAPHS_INSTRUCTIONAL` floor used by the pollution filter.
    # Tests that need a boilerplate-thin chapter can pass `n_paragraphs=1`.
    return Section(
        section_id=f"ch{chapter_num}.s{section_num}",
        title=title,
        pages=PageSpan(start=page_start, end=page_end),
        paragraphs=[_para(chapter_num) for _ in range(n_paragraphs)],
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


class TestPollutionFilter:
    """The pollution filter drops three categories of non-instructional
    chapters before the TOC is formatted:

    * Heading-detector fallback titles (covered by `TestUntitledChapterFiltering`).
    * Front- and back-matter by title pattern (this class).
    * Boilerplate-thin chapters with very few paragraphs.

    Generic — no per-textbook rules. All-or-nothing fallback when the
    filter would leave us with zero chapters.
    """

    @pytest.mark.parametrize("polluted_title", [
        "Acknowledgment", "Acknowledgments", "Acknowledgements",
        "Foreword", "Preface",
        "Appendix A", "Appendix B: Advanced Prompting", "Appendix",
        "Glossary", "Index", "Bibliography", "References", "Errata",
        "Dedication", "Copyright", "Imprint",
        "Table of Contents", "TOC",
        "About the Author", "About the Authors", "About the Editor",
        "Cover", "Title Page", "Half Title",
        # Case-insensitive
        "preface", "GLOSSARY", "appendix c",
    ])
    def test_pollution_title_dropped(self, polluted_title):
        # Pair the polluted chapter with one real chapter so the filter
        # has something to fall back to.
        tb = _textbook([
            _chapter(1, polluted_title),
            _chapter(2, "Real Teaching Chapter"),
        ])
        toc = tb.toc()
        assert polluted_title not in toc
        assert "Real Teaching Chapter" in toc

    def test_real_chapter_titles_with_pollution_words_inside_are_kept(self):
        # The regex anchors to start-of-string, so chapters whose name
        # CONTAINS one of the pollution words (but doesn't START with it)
        # are real teaching chapters and must survive.
        tb = _textbook([
            _chapter(1, "Chapter 1: Introduction to References"),
            _chapter(2, "Chapter 2: Indexes and Catalogs"),
            _chapter(3, "Chapter 3: Bibliography Studies in NLP"),
        ])
        toc = tb.toc()
        # All three should survive — they're real chapters that just
        # happen to contain a pollution word later in the title.
        assert "Chapter 1: Introduction to References" in toc
        assert "Chapter 2: Indexes and Catalogs" in toc
        assert "Chapter 3: Bibliography Studies in NLP" in toc

    def test_boilerplate_thin_chapter_dropped(self):
        # A chapter with only 2 paragraphs total — below the boilerplate
        # floor — is dropped even if its title looks fine.
        tb = _textbook([
            _chapter(1, "Tiny Front Notice", [_section(1, 1, "intro", n_paragraphs=2)]),
            _chapter(2, "Substantive Chapter Two"),
        ])
        toc = tb.toc()
        assert "Tiny Front Notice" not in toc
        assert "Substantive Chapter Two" in toc

    def test_chapter_just_above_threshold_kept(self):
        # The floor is exclusive on the low side: a chapter with exactly
        # `_MIN_PARAGRAPHS_INSTRUCTIONAL` paragraphs (= 5) survives, and a
        # chapter with one fewer (4) does NOT. This tests both edges.
        tb = _textbook([
            _chapter(1, "Five-paragraph chapter",
                     [_section(1, 1, "intro", n_paragraphs=5)]),
            _chapter(2, "Four-paragraph chapter",
                     [_section(2, 1, "intro", n_paragraphs=4)]),
        ])
        toc = tb.toc()
        assert "Five-paragraph chapter" in toc
        assert "Four-paragraph chapter" not in toc

    def test_all_polluted_falls_back_to_unfiltered(self):
        # If pollution-filtering would leave zero chapters, the unfiltered
        # list is returned instead. The TOC must never be empty when the
        # textbook has chapters to show.
        tb = _textbook([
            _chapter(1, "Foreword"),
            _chapter(2, "Glossary"),
            _chapter(3, "Index"),
        ])
        toc = tb.toc()
        assert toc != ""
        # Falls back to unfiltered — all three should appear.
        assert "Foreword" in toc
        assert "Glossary" in toc
        assert "Index" in toc

    def test_realistic_polluted_textbook_keeps_only_real_chapters(self):
        # Mimics the Agentic Design Patterns ingestion: front matter,
        # appendices, glossary, plus the real chapters in between.
        tb = _textbook([
            _chapter(1, "Acknowledgment"),
            _chapter(2, "Foreword"),
            _chapter(3, "Preface"),
            _chapter(4, "Chapter 1: Prompt Chaining"),
            _chapter(5, "Chapter 2: Routing"),
            _chapter(6, "Chapter 3: Tool Use"),
            _chapter(7, "Appendix A: Advanced Prompting"),
            _chapter(8, "Appendix B: Coding Agents"),
            _chapter(9, "Glossary"),
        ])
        toc = tb.toc()
        # 3 real chapters survive.
        assert "Chapter 1: Prompt Chaining" in toc
        assert "Chapter 2: Routing" in toc
        assert "Chapter 3: Tool Use" in toc
        # 6 polluted chapters are dropped.
        for polluted in ("Acknowledgment", "Foreword", "Preface",
                         "Appendix A", "Appendix B", "Glossary"):
            assert polluted not in toc
