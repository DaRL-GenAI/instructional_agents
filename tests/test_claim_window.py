"""Tests for the sentence-bounded claim window extractor used by the
semantic gate and the write-time verifier.

The extractor's job is to return the trailing sentence of the text
immediately preceding a citation token, so the verifier / similarity
gate scores the citation against its actual surrounding claim rather
than a heuristically truncated tail.
"""

from __future__ import annotations

from src.grounding.claim_window import extract_claim_sentence


class TestBasicSentenceSplit:
    def test_single_period_returns_following_sentence(self):
        text = "First sentence. Second sentence with the claim."
        assert extract_claim_sentence(text) == "Second sentence with the claim."

    def test_multiple_sentences_returns_last(self):
        text = "One. Two. Three. Four sentence is the claim."
        assert extract_claim_sentence(text) == "Four sentence is the claim."

    def test_newline_as_separator(self):
        text = "First line.\nSecond line is the claim."
        assert extract_claim_sentence(text) == "Second line is the claim."

    def test_question_mark_terminates_a_sentence(self):
        text = "What about this? Then the claim happens here."
        assert extract_claim_sentence(text) == "Then the claim happens here."

    def test_exclamation_terminates_a_sentence(self):
        text = "Wow! Then the claim happens here."
        assert extract_claim_sentence(text) == "Then the claim happens here."


class TestAbbreviationSuppression:
    """The legacy heuristic split on every ``". "`` it found, which
    treated ``e.g.``, ``i.e.``, ``Fig.``, ``Eq.`` etc. as sentence
    ends and produced truncated claim windows. The new extractor
    suppresses those."""

    def test_eg_does_not_split(self):
        text = "K-means clusters points around centroids (e.g. by minimising variance) using an iterative procedure."
        result = extract_claim_sentence(text)
        # The whole sentence should come back — `e.g.` did not split it
        assert result.startswith("K-means clusters")
        assert "iterative procedure" in result

    def test_ie_does_not_split(self):
        text = "Outliers can dominate the mean (i.e. they pull the centroid). Robust statistics avoid this."
        result = extract_claim_sentence(text)
        assert result == "Robust statistics avoid this."

    def test_etc_does_not_split(self):
        text = "Common methods include k-means, k-medoids, etc. They share a centroid-update step."
        result = extract_claim_sentence(text)
        assert result == "They share a centroid-update step."

    def test_fig_does_not_split(self):
        text = "The diagram is shown in Fig. 4. The arrows mark the decision boundary."
        result = extract_claim_sentence(text)
        assert result == "The arrows mark the decision boundary."

    def test_eq_does_not_split(self):
        text = "The error is computed via Eq. 12. Lower values are better."
        result = extract_claim_sentence(text)
        assert result == "Lower values are better."


class TestFallbacks:
    def test_no_sentence_end_falls_back_to_trailing_words(self):
        text = "this text has no full stops within"
        assert extract_claim_sentence(text, fallback_word_cap=4) == "no full stops within"

    def test_empty_input_returns_empty(self):
        assert extract_claim_sentence("") == ""
        assert extract_claim_sentence("   ") == ""

    def test_only_sentence_returns_itself(self):
        text = "Only one sentence here."
        # No prior split point — fallback applies
        assert "Only one sentence here." in extract_claim_sentence(text, fallback_word_cap=10)


class TestRealisticClaimWindows:
    """Examples drawn from the kind of LLM output the verifier sees."""

    def test_mid_paragraph_claim_grabs_last_sentence(self):
        text = (
            "The k-means algorithm partitions n observations into k clusters. "
            "Each observation belongs to the cluster with the nearest mean. "
            "This iterative process minimises within-cluster variance"
        )
        result = extract_claim_sentence(text)
        assert result == "This iterative process minimises within-cluster variance"

    def test_after_bullet_with_period_does_not_use_bullet(self):
        text = (
            "Three properties matter for clustering quality. "
            "Cluster purity reflects how cleanly groups separate."
        )
        result = extract_claim_sentence(text)
        assert result == "Cluster purity reflects how cleanly groups separate."

    def test_complex_text_with_abbreviation_and_sentence(self):
        text = (
            "Hierarchical clustering produces a dendrogram (cf. Fig. 3 for an example). "
            "The cut height determines the number of clusters"
        )
        result = extract_claim_sentence(text)
        assert result == "The cut height determines the number of clusters"
