"""Tests for the verifier's relevance-based chunk trimming.

When the LLM judge scores a citation, it sees the chunk text as
"excerpt to evaluate the claim against". A whole 500-token chunk
makes the judge fuzzy — it doesn't know which sentence is supposed
to support the claim. Trimming the chunk to the most-overlapping
sentence + neighbours sharpens the judge's input.
"""

from evaluate import (
    _TRIM_MAX_CHARS,
    _TRIM_MIN_CHUNK_CHARS,
    _normalise_words,
    _trim_chunk_to_relevant_passage,
)


class TestNormaliseWords:
    def test_extracts_lowercase_words(self):
        assert _normalise_words("K-means partitioning") == {"k-means", "partitioning"}

    def test_skips_short_tokens(self):
        # Words 1-2 chars skipped; >= 3 chars kept (the regex anchors
        # on at least 3 chars after the leading letter)
        out = _normalise_words("a an i to")
        assert "a" not in out
        assert "an" not in out
        assert "to" not in out


class TestTrimChunkToRelevantPassage:
    def test_short_chunk_returned_unmodified(self):
        chunk = "Short chunk under the threshold."
        assert _trim_chunk_to_relevant_passage(chunk, "anything") == chunk

    def test_empty_chunk_returns_empty(self):
        assert _trim_chunk_to_relevant_passage("", "claim") == ""

    def test_empty_claim_returns_head_truncate(self):
        # A long chunk with no claim → fall back to head
        chunk = "Filler sentence one. " * 100
        out = _trim_chunk_to_relevant_passage(chunk, "")
        assert len(out) <= _TRIM_MAX_CHARS

    def test_picks_most_overlapping_sentence_window(self):
        # Build a long chunk with the relevant sentence in the middle
        irrelevant = (
            "Filler sentence about unrelated topic. " * 20
        )
        relevant = (
            "K-means partitions n observations into k clusters using "
            "nearest-mean assignment in low-dimensional Euclidean space. "
        )
        chunk = irrelevant + relevant + irrelevant
        claim = "K-means partitioning into k clusters using nearest mean."
        out = _trim_chunk_to_relevant_passage(chunk, claim)
        assert "K-means partitions" in out
        # The excerpt should be much shorter than the original chunk
        assert len(out) < len(chunk) // 2

    def test_no_overlap_falls_back_to_head(self):
        chunk = ("Filler about something completely unrelated. " * 30)
        out = _trim_chunk_to_relevant_passage(chunk, "kmeans clustering")
        assert len(out) <= _TRIM_MAX_CHARS

    def test_single_sentence_chunk_not_trimmed(self):
        # When sentence-split yields only one segment, return chunk capped
        chunk = ("one long sentence about clustering algorithms " * 80)
        out = _trim_chunk_to_relevant_passage(chunk, "clustering")
        assert "clustering algorithms" in out

    def test_neighbour_sentences_included_for_context(self):
        # The trimmed excerpt should include a few sentences before and
        # after the best-match sentence so the judge has context.
        chunk = (
            "Sentence one is about preprocessing. "
            "Sentence two introduces clustering. "
            "Sentence three explains the k-means algorithm in detail. "
            "Sentence four discusses convergence. "
            "Sentence five about evaluation metrics. "
        ) * 10  # 50 sentences total
        claim = "the k-means algorithm in detail"
        out = _trim_chunk_to_relevant_passage(chunk, claim)
        # Should include the best-match sentence
        assert "k-means algorithm in detail" in out
        # And at least one neighbour sentence
        assert any(s in out for s in (
            "introduces clustering",
            "discusses convergence",
        ))
