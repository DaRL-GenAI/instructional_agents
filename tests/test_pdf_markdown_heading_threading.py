"""Tests for cross-page chapter-state threading in pdf-markdown heading
normalisation.

Before this fix the heading normaliser reset its ``seen_chapter`` flag
on every call. When pymupdf4llm yielded one markdown block per source
page (``page_chunks=True``) and each page had its own first
unnumbered ``##`` heading, EVERY page produced a fresh chapter — Han's
single-PDF-per-chapter source became 7 IR chapters per PDF, and the
6-PDF directory became 36 IR chapters. The downstream retrieval space
was inflated 6x and cross-chapter retrieval confusion drove the v4
retrieval_bad share to 27 % (vs v2's 17 %).

The fix threads ``seen_chapter`` through the per-page calls so the
chapter-promotion happens at most once per PDF file.
"""

from src.textbook.ingest_pdf import _normalize_pdf_markdown_headings
from src.textbook.ingest_pdf_paged import _extract_blocks_with_page


class TestNormaliserSeenChapterArg:
    def test_first_unnumbered_h2_with_seen_false_promotes_to_h1(self):
        md = "## First Heading\nbody"
        out, seen = _normalize_pdf_markdown_headings(md, seen_chapter=False)
        assert out.startswith("# First Heading")
        assert seen is True

    def test_first_unnumbered_h2_with_seen_true_demotes_to_h3(self):
        md = "## First Heading\nbody"
        out, seen = _normalize_pdf_markdown_headings(md, seen_chapter=True)
        assert out.startswith("### First Heading")
        assert seen is True

    def test_chapter_pattern_always_promotes_and_returns_seen_true(self):
        md = "## Chapter 3 Methodology\nbody"
        out, seen = _normalize_pdf_markdown_headings(md, seen_chapter=False)
        assert "# Chapter 3 Methodology" in out
        assert seen is True

    def test_numbered_section_not_promoted(self):
        md = "## 10.4 Density-Based Methods\nbody"
        out, _ = _normalize_pdf_markdown_headings(md, seen_chapter=True)
        assert out.startswith("## 10.4 Density-Based Methods")


class TestThreadingAcrossExtractBlocks:
    def test_first_page_promotes_subsequent_pages_demote(self):
        # Three "pages" each with their own first unnumbered ##
        # heading — pre-fix, each became a separate chapter
        # (3 chapters); post-fix, only the first does.
        page_1 = "## Cluster Analysis\nIntro text."
        page_2 = "## Methods\nMethod text."
        page_3 = "## Evaluation\nEval text."

        blocks_1, seen_after_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False,
        )
        blocks_2, seen_after_2 = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_after_1,
        )
        blocks_3, seen_after_3 = _extract_blocks_with_page(
            page_3, page_num=3, seen_chapter=seen_after_2,
        )

        # Count headings at each level across all blocks
        all_blocks = blocks_1 + blocks_2 + blocks_3
        headings_level_1 = [b for b in all_blocks
                            if b["type"] == "heading" and b["level"] == 1]
        # Should be exactly ONE level-1 heading — the first page only
        assert len(headings_level_1) == 1, (
            f"expected exactly 1 chapter heading, got {len(headings_level_1)}: "
            f"{[b.get('title') for b in headings_level_1]}"
        )
        assert headings_level_1[0]["title"] == "Cluster Analysis"

    def test_explicit_chapter_pattern_on_page_2_still_creates_chapter(self):
        # If pymupdf4llm DOES emit "## Chapter 2 Foo" on a later page,
        # the explicit pattern wins and creates a new chapter.
        page_1 = "## Cluster Analysis\nIntro text."
        page_2 = "## Chapter 2 Classification\nClassification text."

        blocks_1, seen_after_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False,
        )
        blocks_2, seen_after_2 = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_after_1,
        )

        headings_level_1 = [b for b in (blocks_1 + blocks_2)
                            if b["type"] == "heading" and b["level"] == 1]
        # Two chapters: "Cluster Analysis" + "Chapter 2 Classification"
        assert len(headings_level_1) == 2
        titles = {h["title"] for h in headings_level_1}
        assert "Cluster Analysis" in titles
        assert any("Chapter 2" in t for t in titles)

    def test_numbered_h2_on_later_page_stays_section_level(self):
        # A numbered "## 10.4 ..." on a later page should stay as a
        # section, not get promoted.
        page_1 = "## Cluster Analysis\nIntro text."
        page_2 = "## 10.4 Density-Based Methods\nDensity text."

        blocks_1, seen_after_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False,
        )
        blocks_2, _ = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_after_1,
        )

        # Page 1 yields one level-1 (chapter); page 2 yields one
        # level-2 (section)
        headings_level_1 = [b for b in (blocks_1 + blocks_2)
                            if b["type"] == "heading" and b["level"] == 1]
        headings_level_2 = [b for b in (blocks_1 + blocks_2)
                            if b["type"] == "heading" and b["level"] == 2]
        assert len(headings_level_1) == 1
        assert len(headings_level_2) == 1
        assert headings_level_2[0]["title"].startswith("10.4")

    def test_seen_chapter_state_persists_when_no_headings_on_page(self):
        # A page with body text but no headings shouldn't reset the
        # state.
        page_1 = "## Cluster Analysis\nIntro."
        page_2 = "More body text on page 2."
        page_3 = "## Methods Discussion\nMethods text."

        blocks_1, seen_after_1 = _extract_blocks_with_page(
            page_1, page_num=1, seen_chapter=False,
        )
        blocks_2, seen_after_2 = _extract_blocks_with_page(
            page_2, page_num=2, seen_chapter=seen_after_1,
        )
        blocks_3, _ = _extract_blocks_with_page(
            page_3, page_num=3, seen_chapter=seen_after_2,
        )

        # Should still be just ONE chapter heading; page 3's ##
        # demotes to ###
        headings_level_1 = [b for b in (blocks_1 + blocks_2 + blocks_3)
                            if b["type"] == "heading" and b["level"] == 1]
        assert len(headings_level_1) == 1


class TestBackwardCompatDefault:
    def test_normaliser_defaults_to_seen_false(self):
        # Callers using the old single-arg API still work via the
        # default; tuple unpacking is the only breakage and was fixed
        # in the two known callers.
        md = "## First Heading\nbody"
        out, _ = _normalize_pdf_markdown_headings(md)
        assert out.startswith("# First Heading")
