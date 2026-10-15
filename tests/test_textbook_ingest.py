"""Tests for the markdown textbook ingester.

Covers TOC recall (target >= 0.9 on a labeled fixture), paragraph-kind
classification, paragraph-id format, page-number monotonicity, and Sphinx
directive stripping.

Includes an optional smoke test against the cloned d2l-en repo if present.
"""

import re
from pathlib import Path

import pytest

from src.textbook.ingest_md import (
    _classify_paragraph,
    _strip_sphinx_directives,
    ingest_file,
)
from src.textbook.toc import parse_toc

# Paths are derived from this test file's location so the suite runs on any
# machine without absolute-path assumptions.
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
MINI = FIXTURE_DIR / "mini_textbook.md"

# Optional real-world fixtures from a local d2l-en clone (skipped if missing).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
D2L_ROOT = PROJECT_ROOT / "data" / "repos" / "d2l_en"
D2L_INTRO = D2L_ROOT / "chapter_introduction" / "index.md"
LR_DIR = D2L_ROOT / "chapter_linear-regression"
LR_MAIN = LR_DIR / "linear-regression.md"
LR_SCRATCH = LR_DIR / "linear-regression-scratch.md"


class TestTOC:
    """Heading detection."""

    def test_finds_all_headings_in_fixture(self):
        text = MINI.read_text(encoding="utf-8")
        headings = parse_toc(text)
        # mini_textbook.md has: 2 level-1, 3 level-2, 1 level-3 = 6 total
        assert len(headings) == 6

    def test_first_heading_is_chapter_1(self):
        headings = parse_toc(MINI.read_text(encoding="utf-8"))
        assert headings[0].level == 1
        assert "Chapter 1" in headings[0].title

    def test_toc_recall_meets_target(self):
        """TOC recall must be >= 0.9 on the labeled fixture."""
        headings = parse_toc(MINI.read_text(encoding="utf-8"))
        expected = 6
        recall = len(headings) / expected
        assert recall >= 0.9, f"TOC recall {recall:.2f} below 0.9 target"

    def test_level_distribution(self):
        headings = parse_toc(MINI.read_text(encoding="utf-8"))
        levels = [h.level for h in headings]
        assert levels.count(1) == 2  # 2 chapters
        assert levels.count(2) == 3  # 3 sections
        assert levels.count(3) == 1  # 1 subsection


class TestParagraphClassification:
    """Tests for _classify_paragraph."""

    def test_display_math(self):
        assert _classify_paragraph("$$y = mx + b$$") == "equation"

    def test_display_math_multiline(self):
        assert _classify_paragraph("$$\nE = mc^2\n$$") == "equation"

    def test_image_only(self):
        assert _classify_paragraph("![caption](path/to/image.png)") == "figure_cap"

    def test_definition_bold(self):
        assert _classify_paragraph("**Definition:** A type is a kind of value.") == "definition"

    def test_definition_plain(self):
        assert _classify_paragraph("Definition: A type is a kind of value.") == "definition"

    def test_plain_prose(self):
        assert _classify_paragraph("This is a regular paragraph.") == "prose"

    def test_prose_with_inline_math_stays_prose(self):
        assert _classify_paragraph("The variable $x$ holds a value.") == "prose"


class TestSphinxStripping:
    def test_strips_label_directive(self):
        s = "See :label:`foo` for details."
        assert ":label:" not in _strip_sphinx_directives(s)
        assert "See  for details." == _strip_sphinx_directives(s)

    def test_strips_eqlabel_numref(self):
        s = "Refer to :eqlabel:`eq_x` and :numref:`fig_y`."
        out = _strip_sphinx_directives(s)
        assert ":eqlabel:" not in out
        assert ":numref:" not in out

    def test_leaves_unrelated_text_alone(self):
        s = "A normal sentence with no directives."
        assert _strip_sphinx_directives(s) == s


class TestIngestFile:
    """End-to-end ingestion of the labeled fixture."""

    def test_textbook_metadata(self):
        tb = ingest_file(MINI, textbook_id="mini", title="Mini Textbook",
                         authors=["Test Author"])
        assert tb.textbook_id == "mini"
        assert tb.title == "Mini Textbook"
        assert tb.authors == ["Test Author"]
        assert tb.source_format == "markdown"

    def test_chapter_count(self):
        tb = ingest_file(MINI)
        assert len(tb.chapters) == 2

    def test_section_counts_per_chapter(self):
        tb = ingest_file(MINI)
        # ch1: Section 1.1 (Numbers and Strings) + Section 1.2 (Operators)
        assert len(tb.chapters[0].sections) == 2
        # ch2: Section 2.1 (Conditionals)
        assert len(tb.chapters[1].sections) == 1

    def test_chapter_titles(self):
        tb = ingest_file(MINI)
        assert "Chapter 1" in tb.chapters[0].title
        assert "Foundations" in tb.chapters[0].title
        assert "Chapter 2" in tb.chapters[1].title

    def test_paragraph_kinds_all_present(self):
        tb = ingest_file(MINI)
        all_kinds = {
            p.kind
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
        }
        assert "prose" in all_kinds
        assert "equation" in all_kinds
        assert "example" in all_kinds
        assert "figure_cap" in all_kinds
        assert "definition" in all_kinds

    def test_paragraph_ids_well_formed(self):
        tb = ingest_file(MINI)
        pat = re.compile(r"^ch\d+\.s\d+\.p\d{2}$")
        for ch in tb.chapters:
            for s in ch.sections:
                for p in s.paragraphs:
                    assert pat.match(p.para_id), f"Bad para_id: {p.para_id}"

    def test_chapter_ids_well_formed(self):
        tb = ingest_file(MINI)
        for i, ch in enumerate(tb.chapters, start=1):
            assert ch.chapter_id == f"ch{i}"
            assert ch.number == i

    def test_page_numbers_monotonic(self):
        tb = ingest_file(MINI)
        last = 0
        for ch in tb.chapters:
            for s in ch.sections:
                for p in s.paragraphs:
                    assert p.page >= last
                    last = p.page

    def test_section_spans_valid(self):
        tb = ingest_file(MINI)
        for ch in tb.chapters:
            assert ch.pages.start >= 1
            assert ch.pages.end >= ch.pages.start
            for s in ch.sections:
                assert s.pages.start >= 1
                assert s.pages.end >= s.pages.start

    def test_sphinx_label_stripped_from_chapter(self):
        """The :label:`ch_foundations` directive should not appear in any output text."""
        tb = ingest_file(MINI)
        for ch in tb.chapters:
            for s in ch.sections:
                for p in s.paragraphs:
                    assert ":label:" not in p.text
                    assert ":eqlabel:" not in p.text


@pytest.mark.skipif(
    not D2L_INTRO.exists(),
    reason="d2l-en not cloned (data/repos/d2l_en/ missing)",
)
class TestIngestRealD2LChapter:
    """Smoke test on a single real d2l-en chapter. Asserts plausibility, not exact counts."""

    def test_ingests_without_error(self):
        tb = ingest_file(
            D2L_INTRO,
            textbook_id="d2l",
            title="Dive into Deep Learning",
            authors=["Aston Zhang", "Zachary C. Lipton", "Mu Li", "Alexander J. Smola"],
        )
        assert len(tb.chapters) >= 1

    def test_produces_many_prose_paragraphs(self):
        tb = ingest_file(D2L_INTRO)
        prose_count = sum(
            1
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
            if p.kind == "prose"
        )
        assert prose_count >= 30, f"Only {prose_count} prose paragraphs in d2l intro"

    def test_page_numbers_assigned(self):
        tb = ingest_file(D2L_INTRO)
        all_pages = [
            p.page
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
        ]
        assert all(p >= 1 for p in all_pages)
        assert max(all_pages) >= 2, "Long chapter should span multiple synthetic pages"


@pytest.mark.skipif(
    not D2L_ROOT.exists(),
    reason="d2l-en not cloned (data/repos/d2l_en/ missing)",
)
class TestIngestRealD2LMultiChapter:
    """Thicker Layer-2 tests across multiple real d2l-en chapters.

    Validates the ingester against:
      - the math-heavy `chapter_linear-regression/linear-regression.md` (display math)
      - the code-heavy `chapter_linear-regression/linear-regression-scratch.md` (code fences)
      - the FULL repo via ingest_directory (30 chapter dirs, 209 .md files)

    The full-repo Textbook is built once per class via fixture to keep runtime down.
    """

    @pytest.fixture(scope="class")
    def full_d2l(self):
        """Ingest the entire d2l-en repo once and share across tests."""
        from src.textbook.ingest_md import ingest_directory
        return ingest_directory(
            D2L_ROOT,
            textbook_id="d2l",
            title="Dive into Deep Learning",
            authors=["Aston Zhang", "Zachary C. Lipton", "Mu Li", "Alexander J. Smola"],
        )

    # --- full-repo tests (use the fixture) ---

    def test_full_d2l_chapter_count(self, full_d2l):
        """d2l-en has 30 chapter_*/ dirs; ingester should find most of them."""
        assert len(full_d2l.chapters) >= 25, \
            f"Got only {len(full_d2l.chapters)} chapters"

    def test_full_d2l_every_chapter_has_sections(self, full_d2l):
        """No chapter should be empty after ingestion."""
        for ch in full_d2l.chapters:
            assert len(ch.sections) >= 1, f"Empty chapter: {ch.title}"

    def test_full_d2l_paragraph_count(self, full_d2l):
        """Whole repo should produce thousands of paragraphs."""
        total = sum(
            len(s.paragraphs)
            for ch in full_d2l.chapters
            for s in ch.sections
        )
        assert total >= 1000, f"Only {total} paragraphs across all of d2l-en"

    def test_full_d2l_paragraph_ids_unique(self, full_d2l):
        """Every Paragraph.para_id should be unique across the textbook."""
        all_ids = [
            p.para_id
            for ch in full_d2l.chapters
            for s in ch.sections
            for p in s.paragraphs
        ]
        assert len(all_ids) == len(set(all_ids)), "Duplicate para_ids in full d2l-en"

    def test_full_d2l_pages_monotonic_within_chapter(self, full_d2l):
        """Within any chapter, paragraph pages should be non-decreasing."""
        for ch in full_d2l.chapters:
            last = 0
            for s in ch.sections:
                for p in s.paragraphs:
                    assert p.page >= last, \
                        f"Page went backwards in {ch.title}: {last} -> {p.page}"
                    last = p.page

    # --- per-chapter targeted tests ---

    def test_math_heavy_chapter_has_equations(self):
        """linear-regression.md has 50+ display-math blocks per our grep."""
        tb = ingest_file(LR_MAIN, textbook_id="d2l_lr")
        equation_count = sum(
            1
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
            if p.kind == "equation"
        )
        assert equation_count >= 10, \
            f"Only {equation_count} equations in linear-regression.md (expected ≥10)"

    def test_code_heavy_chapter_has_examples(self):
        """linear-regression-scratch.md is the from-scratch implementation; many code fences."""
        tb = ingest_file(LR_SCRATCH, textbook_id="d2l_lrs")
        example_count = sum(
            1
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
            if p.kind == "example"
        )
        assert example_count >= 5, \
            f"Only {example_count} code blocks in linear-regression-scratch.md (expected ≥5)"

    def test_real_figures_classified_as_figure_cap(self):
        """linear-regression.md has on-own-line figure refs that should classify."""
        tb = ingest_file(LR_MAIN, textbook_id="d2l_lr")
        figure_count = sum(
            1
            for ch in tb.chapters
            for s in ch.sections
            for p in s.paragraphs
            if p.kind == "figure_cap"
        )
        assert figure_count >= 1, "No figure_cap paragraphs found in linear-regression.md"

    def test_sphinx_directives_never_leak_to_output(self):
        """No :label:/:eqlabel:/:numref:/:cite: should appear in any output paragraph text."""
        tb = ingest_file(LR_MAIN, textbook_id="d2l_lr")
        for ch in tb.chapters:
            for s in ch.sections:
                for p in s.paragraphs:
                    for directive in (":label:", ":eqlabel:", ":numref:", ":cite:"):
                        assert directive not in p.text, \
                            f"{directive} leaked into {p.para_id}: {p.text[:80]!r}"

    def test_all_paragraphs_have_nonempty_text(self):
        """No paragraph should be emitted with empty/whitespace-only text."""
        tb = ingest_file(LR_MAIN, textbook_id="d2l_lr")
        for ch in tb.chapters:
            for s in ch.sections:
                for p in s.paragraphs:
                    assert p.text.strip(), f"Empty paragraph: {p.para_id}"

    def test_toc_finds_at_least_one_level_2(self):
        """parse_toc on a substantive d2l-en chapter should find multiple level-2 headings."""
        text = LR_MAIN.read_text(encoding="utf-8")
        headings = parse_toc(text)
        level_2 = sum(1 for h in headings if h.level == 2)
        assert level_2 >= 3, f"Expected ≥3 level-2 headings in linear-regression.md, got {level_2}"
