"""Tests for ``split_into_sentences``, the sentence splitter used by the
knowledge-base chunker and the embedder size guard.

Its job is to break prose on GENUINE sentence boundaries — punctuation
followed by whitespace and an uppercase letter — while suppressing
common abbreviations (``e.g.``, ``i.e.``, ``Fig.``, ``Eq.`` …) that end
in a period but do not terminate a sentence. This avoids the truncated
mid-sentence sub-chunks a naive split on ``". "`` produced.
"""

from __future__ import annotations

from src.grounding.claim_window import split_into_sentences


class TestBasicSplit:
    def test_two_sentences_split(self):
        assert split_into_sentences("First sentence. Second sentence.") == [
            "First sentence.",
            "Second sentence.",
        ]

    def test_multiple_sentences_split(self):
        out = split_into_sentences("One thing. Two things. Three things. Four.")
        assert out == ["One thing.", "Two things.", "Three things.", "Four."]

    def test_empty_returns_empty_list(self):
        assert split_into_sentences("") == []

    def test_no_sentence_end_returns_whole_text(self):
        assert split_into_sentences("this text has no full stops within") == [
            "this text has no full stops within"
        ]


class TestBoundaryPunctuation:
    def test_question_mark_terminates(self):
        out = split_into_sentences("What about this? Then more text here.")
        assert out == ["What about this?", "Then more text here."]

    def test_exclamation_terminates(self):
        out = split_into_sentences("Wow there! Then more text here.")
        assert out == ["Wow there!", "Then more text here."]

    def test_newline_between_sentences_splits(self):
        out = split_into_sentences("First line here.\nSecond line here.")
        assert out == ["First line here.", "Second line here."]

    def test_lowercase_after_period_does_not_split(self):
        # The regex requires an uppercase (or quote/paren) start after the
        # break, so a decimal or lowercase continuation stays in one piece.
        assert split_into_sentences("the value is 3.14 and stays here") == [
            "the value is 3.14 and stays here"
        ]


class TestAbbreviationSuppression:
    """Abbreviations that end in a period but are followed by an uppercase
    word must NOT trigger a split — the whole span stays one sentence."""

    def test_eg_does_not_split(self):
        out = split_into_sentences("Methods e.g. Means and medoids work well here.")
        assert out == ["Methods e.g. Means and medoids work well here."]

    def test_ie_does_not_split(self):
        out = split_into_sentences("The mean i.e. Average value pulls the centroid.")
        assert out == ["The mean i.e. Average value pulls the centroid."]

    def test_fig_does_not_split(self):
        out = split_into_sentences("Shown in Fig. Then arrows mark the boundary.")
        assert out == ["Shown in Fig. Then arrows mark the boundary."]

    def test_eq_does_not_split(self):
        out = split_into_sentences("Computed via Eq. Lower values are better here.")
        assert out == ["Computed via Eq. Lower values are better here."]

    def test_real_boundary_still_splits(self):
        # A non-abbreviation word before the period DOES split.
        out = split_into_sentences("Methods include k-means. They share a step.")
        assert out == ["Methods include k-means.", "They share a step."]

    def test_etc_is_a_deliberate_split(self):
        # ``etc.`` is intentionally absent from the suppression set — in real
        # prose it often DOES end a sentence, so it splits.
        out = split_into_sentences("Includes k-means, etc. They share a step.")
        assert out == ["Includes k-means, etc.", "They share a step."]
