"""Tests for the evidence-block chunk-dedup helper.

The chunker emits OVERLAP_TOKENS of overlap between adjacent prose
chunks, so the retriever can rank two neighboring chunks both in the
top-K. The LLM seeing redundant content sometimes cites the wrong
instance (manifests as wrong_chunk_cited / loose_paraphrase in the
verifier). The dedup helper preserves rank order and drops later
occurrences of:
    1. byte-identical chunks
    2. chunks whose first 40 words match a kept chunk (the overlap
       case)
"""

from types import SimpleNamespace

from src.slides import _dedupe_results


def _result(text: str):
    """Build a minimal RetrievalResult shape for the dedup helper."""
    return SimpleNamespace(chunk=SimpleNamespace(text=text))


class TestDedupeResults:
    def test_empty_input_returns_empty(self):
        assert _dedupe_results([]) == []

    def test_unique_chunks_all_kept(self):
        results = [
            _result("alpha bravo charlie " * 20),
            _result("delta echo foxtrot " * 20),
            _result("golf hotel india " * 20),
        ]
        kept = _dedupe_results(results)
        assert len(kept) == 3

    def test_byte_identical_chunks_deduped(self):
        text = "k-means partitions n observations into k clusters. " * 5
        results = [_result(text), _result(text), _result(text + " different ending")]
        kept = _dedupe_results(results)
        assert len(kept) == 2  # one of the identicals dropped
        assert kept[0].chunk.text == text
        assert "different ending" in kept[1].chunk.text

    def test_overlapping_chunks_with_shared_prefix_deduped(self):
        # Two chunks whose first 40 words are identical → overlap case
        shared_prefix = " ".join(["overlapword"] * 40)
        a = shared_prefix + " " + " ".join(["uniqueA"] * 20)
        b = shared_prefix + " " + " ".join(["uniqueB"] * 20)
        kept = _dedupe_results([_result(a), _result(b)])
        assert len(kept) == 1
        assert "uniqueA" in kept[0].chunk.text

    def test_different_prefixes_kept_even_if_partial_overlap(self):
        # Different START → kept even if mid-content overlaps
        a = "alpha bravo " + " ".join(["shared"] * 30) + " uniqueA"
        b = "completely different starting words " + " ".join(["shared"] * 30) + " uniqueB"
        kept = _dedupe_results([_result(a), _result(b)])
        assert len(kept) == 2

    def test_rank_order_preserved(self):
        # First occurrence of each cluster wins
        text = "shared content here for the dedup case " * 10
        results = [
            _result(text + " ranked first"),
            _result(text + " ranked second"),  # dropped (same prefix)
            _result("a totally different chunk that should rank third"),
        ]
        kept = _dedupe_results(results)
        assert len(kept) == 2
        assert "ranked first" in kept[0].chunk.text
        assert "totally different" in kept[1].chunk.text

    def test_empty_text_chunks_handled_gracefully(self):
        # Defensive: an empty chunk shouldn't crash or all-dedup
        results = [_result(""), _result(""), _result("real content here")]
        kept = _dedupe_results(results)
        # Empty + empty have identical text → second empty dropped.
        # Real content kept.
        assert len(kept) == 2
        assert kept[1].chunk.text == "real content here"

    def test_chunks_shorter_than_prefix_size_still_dedupe_on_full_match(self):
        # Chunk shorter than _DEDUPE_PREFIX_WORDS: dedup falls through
        # to full-text equality
        a = "tiny chunk here"
        results = [_result(a), _result(a), _result("different tiny chunk")]
        kept = _dedupe_results(results)
        assert len(kept) == 2
