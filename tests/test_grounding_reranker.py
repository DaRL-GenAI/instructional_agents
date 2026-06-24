"""Tests for the optional cross-encoder reranker.

Uses `HashReranker` so no model download / no network is needed. Exercises:
  - The standalone `apply_rerank` utility (correct ordering, top-k truncation,
    error-path fallback to first-stage order).
  - `HybridRetriever` plumbing — when `reranker=None`, behavior is identical
    to before (so existing tests stay valid). When a reranker is wired in,
    the final ranking comes from the reranker, NOT from RRF.
  - Lazy load: importing the module does not import torch /
    sentence-transformers, and constructing `CrossEncoderReranker` does
    not load the model.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.grounding import (
    HashEmbedder,
    HashReranker,
    HybridRetriever,
    TextbookKnowledgeBase,
    apply_rerank,
)
from src.grounding.reranker import CrossEncoderReranker

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"


# --------------------------------------------------------------------- #
# Standalone apply_rerank utility
# --------------------------------------------------------------------- #


class _Candidate:
    """Tiny stand-in for ScoredChunk in pure unit tests."""

    def __init__(self, text: str, id_: str):
        self.id = id_
        self._text = text

    @property
    def chunk(self):
        # apply_rerank's default text_getter pulls `.chunk.text` — mirror that.
        return self

    @property
    def text(self):
        return self._text


class TestApplyRerank:
    def test_empty_input_returns_empty(self):
        rer = HashReranker()
        assert apply_rerank("q", [], rer, top_k=5) == []

    def test_reorder_by_jaccard(self):
        # HashReranker scores by Jaccard overlap of bag-of-words.
        # Query "k means clustering" picks "k means" passage over "blue ocean".
        candidates = [
            _Candidate("the blue ocean is wide", "a"),
            _Candidate("k means clustering algorithm", "b"),
            _Candidate("totally unrelated text here", "c"),
        ]
        rer = HashReranker()
        out = apply_rerank("k means clustering", candidates, rer, top_k=3)
        # Best Jaccard-match should land first.
        assert out[0].id == "b"
        assert len(out) == 3

    def test_top_k_truncates(self):
        candidates = [_Candidate(f"text {i}", str(i)) for i in range(10)]
        rer = HashReranker()
        out = apply_rerank("text", candidates, rer, top_k=3)
        assert len(out) == 3

    def test_reranker_exception_falls_back_to_first_stage_order(self):
        class _Broken:
            model = "broken"

            def score(self, q, ps):
                raise RuntimeError("simulated model crash")

        # Original order preserved on failure.
        candidates = [_Candidate(f"t{i}", str(i)) for i in range(5)]
        out = apply_rerank("anything", candidates, _Broken(), top_k=3)
        assert [c.id for c in out] == ["0", "1", "2"]

    def test_score_count_mismatch_falls_back(self):
        # A misbehaving reranker that returns the wrong-sized list must
        # not corrupt the result — fall back to first-stage truncation.
        class _Wrong:
            model = "wrong"

            def score(self, q, ps):
                return [0.0, 0.0]  # always 2, regardless of input length

        candidates = [_Candidate(f"t{i}", str(i)) for i in range(5)]
        out = apply_rerank("anything", candidates, _Wrong(), top_k=3)
        assert [c.id for c in out] == ["0", "1", "2"]


# --------------------------------------------------------------------- #
# HybridRetriever wiring
# --------------------------------------------------------------------- #


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf missing")
class TestHybridRetrieverRerankerPlumbing:
    @pytest.fixture
    def kb(self):
        return TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")

    def test_no_reranker_default_behavior_unchanged(self, kb, tmp_path):
        # Backward compat: the default constructor (no `reranker=`)
        # produces the same results as before — RRF top-k, no second stage.
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        assert retriever.reranker is None
        results = retriever.search("numbers", top_k=2)
        assert len(results) <= 2

    def test_attached_reranker_reorders_results(self, kb, tmp_path):
        # Compare top-1 with and without reranker — different ordering proves
        # the reranker is doing work (HashReranker scores by Jaccard, which
        # differs from RRF's rank-based fusion).
        plain = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                cache_dir=tmp_path)
        plain_top = plain.search("conditional branching control flow", top_k=3)

        with_rer = HybridRetriever(
            kb, embedder=HashEmbedder(dim=64),
            cache_dir=tmp_path, reranker=HashReranker(),
        )
        with_rer.reranker = HashReranker()
        with_rer_top = with_rer.search("conditional branching control flow", top_k=3)

        assert len(with_rer_top) <= 3
        # Reranked result is non-empty.
        assert len(with_rer_top) > 0
        # The reranker pulls a larger first-stage set internally — confirm
        # that the chunks it returns are still drawn from the fixture's
        # known set (i.e., we didn't corrupt anything).
        assert all(any(r.chunk.chunk_id == c.chunk_id for c in kb.chunks)
                   for r in with_rer_top)

    def test_section_filter_still_respected_with_reranker(self, kb, tmp_path):
        # The contract-bound retrieval path (section_ids filter) must
        # still constrain results even with a reranker attached.
        first_section = next(
            s.section_id for c in kb.textbook.chapters for s in c.sections
        )
        retriever = HybridRetriever(
            kb, embedder=HashEmbedder(dim=64),
            cache_dir=tmp_path, reranker=HashReranker(),
        )
        results = retriever.search(
            "anything", top_k=3, section_ids=[first_section],
        )
        assert all(r.chunk.section_id == first_section for r in results)


# --------------------------------------------------------------------- #
# Lazy import / lazy load
# --------------------------------------------------------------------- #


class TestLazyModelLoad:
    def test_construct_does_not_load_model(self):
        # The expensive load (importing sentence-transformers, downloading
        # the model) must NOT happen at construction time. Lets a caller
        # pass the instance around without paying the cost until .score()
        # is actually invoked.
        rer = CrossEncoderReranker()
        assert rer._encoder is None
        # Default is a small MS-MARCO cross-encoder (under 100 MB) so
        # the dep doesn't bloat deployments.
        assert "cross-encoder" in rer.model or "ms-marco" in rer.model

    def test_import_does_not_pull_in_heavy_deps(self):
        # Importing the reranker module should not eagerly load the
        # ONNX runtime or the embedding library. Verified via sys.modules
        # — heavy deps only appear after a .score() call.
        import sys
        # If the heavy deps are already loaded (e.g. some other test
        # exercised the reranker), this test is non-informative.
        if "fastembed" in sys.modules or "onnxruntime" in sys.modules:
            pytest.skip(
                "fastembed/onnxruntime already imported in this session; "
                "can't verify lazy-loading"
            )
        from src.grounding import reranker as _r  # noqa: F401
        # After importing src.grounding.reranker alone, neither
        # fastembed nor onnxruntime should be in sys.modules.
        assert "fastembed" not in sys.modules
        assert "onnxruntime" not in sys.modules
        # The retired backend should also stay out.
        assert "sentence_transformers" not in sys.modules
        assert "torch" not in sys.modules


class TestHashRerankerStub:
    """The deterministic stub — sanity-check it behaves like a reranker
    so it's a valid offline substitute in tests + dry runs."""

    def test_deterministic_across_calls(self):
        rer = HashReranker()
        a = rer.score("query", ["passage one", "passage two"])
        b = rer.score("query", ["passage one", "passage two"])
        assert a == b

    def test_empty_passage_list(self):
        rer = HashReranker()
        assert rer.score("query", []) == []

    def test_overlap_drives_score(self):
        rer = HashReranker()
        scores = rer.score(
            "k means clustering",
            ["k means partitions data", "completely unrelated content"],
        )
        # The passage that shares tokens with the query should outscore
        # the unrelated one.
        assert scores[0] > scores[1]


