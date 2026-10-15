"""Tests for cross-page sentence stitching.

When a sentence breaks at a physical page boundary in the source PDF,
the PyMuPDF4LLM page-chunked extractor produces two half-paragraphs:
one ending mid-thought on page N, another starting with a lowercase
letter on page N+1. The stitcher merges those halves into a single
paragraph so the full sentence is retrievable as one unit.
"""

from src.textbook.ingest_pdf_paged import (
    _ends_mid_sentence,
    _starts_mid_sentence,
    _stitch_cross_page_dangles,
)


class TestEndStartHeuristics:
    def test_period_ending_is_clean(self):
        assert not _ends_mid_sentence("This is a complete sentence.")

    def test_no_terminator_ending_is_dangling(self):
        assert _ends_mid_sentence(
            "Sentence continues across the page boundary and"
        )

    def test_question_mark_ending_is_clean(self):
        assert not _ends_mid_sentence("Is this complete?")

    def test_empty_text_not_dangling(self):
        assert not _ends_mid_sentence("")
        assert not _ends_mid_sentence("   ")

    def test_lowercase_start_is_continuation(self):
        assert _starts_mid_sentence("then proceeds to the conclusion.")

    def test_capital_start_is_fresh_sentence(self):
        assert not _starts_mid_sentence("New sentence starts here.")

    def test_digit_start_not_continuation(self):
        assert not _starts_mid_sentence("3. Bullet point.")

    def test_punctuation_start_not_continuation(self):
        assert not _starts_mid_sentence("(parenthetical aside)")


class TestStitchCrossPageDangles:
    def _para(self, text: str, page: int) -> dict:
        return {"type": "paragraph", "kind": "prose", "text": text, "page": page}

    def _heading(self, text: str, page: int) -> dict:
        return {"type": "heading", "level": 2, "title": text, "page": page}

    def test_empty_blocks_returns_empty(self):
        assert _stitch_cross_page_dangles([]) == []

    def test_two_paragraphs_on_same_page_not_stitched(self):
        # Even if the first ends without a terminator and the second
        # starts lowercase, they're on the same page → not stitched.
        blocks = [
            self._para("First paragraph ends without terminator", 1),
            self._para("then continues lowercase here.", 1),
        ]
        out = _stitch_cross_page_dangles(blocks)
        assert len(out) == 2

    def test_two_paragraphs_across_pages_with_dangle_stitched(self):
        blocks = [
            self._para(
                "The sentence breaks mid-thought at the page boundary and",
                1,
            ),
            self._para(
                "continues here on the next page with a complete ending.",
                2,
            ),
        ]
        out = _stitch_cross_page_dangles(blocks)
        assert len(out) == 1
        assert "breaks mid-thought" in out[0]["text"]
        assert "continues here" in out[0]["text"]
        # Merged paragraph carries the EARLIER page (where the sentence
        # started)
        assert out[0]["page"] == 1

    def test_clean_break_across_pages_not_stitched(self):
        # First paragraph ends cleanly, second is a new sentence.
        blocks = [
            self._para("First page ends cleanly here.", 1),
            self._para("Second page starts fresh.", 2),
        ]
        out = _stitch_cross_page_dangles(blocks)
        assert len(out) == 2

    def test_heading_across_pages_never_stitched(self):
        # A heading on page 2 must not be glued to the dangle on page 1
        # (headings are structural; dangles only apply to paragraphs).
        blocks = [
            self._para("Dangle ends without terminator", 1),
            self._heading("Section Heading", 2),
        ]
        out = _stitch_cross_page_dangles(blocks)
        assert len(out) == 2
        assert out[1]["type"] == "heading"

    def test_three_consecutive_pages_can_chain_stitch(self):
        # Page 1 dangles into page 2 → merged. Then merged paragraph
        # may dangle into page 3 → merged again.
        blocks = [
            self._para("First fragment ends and", 1),
            self._para("middle fragment also ends and", 2),
            self._para("final fragment completes the thought.", 3),
        ]
        out = _stitch_cross_page_dangles(blocks)
        assert len(out) == 1
        assert "First fragment" in out[0]["text"]
        assert "middle fragment" in out[0]["text"]
        assert "final fragment" in out[0]["text"]

    def test_non_paragraph_block_preserved_unchanged(self):
        # A heading between two dangle-able paragraphs blocks the merge.
        blocks = [
            self._para("Dangle on page 1 ends and", 1),
            self._heading("New Section", 2),
            self._para("new section starts mid-sentence", 2),
        ]
        out = _stitch_cross_page_dangles(blocks)
        # Heading prevents the merge
        assert len(out) == 3
