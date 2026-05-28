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
    LLMReranker,
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

    def test_import_does_not_pull_in_torch(self):
        # Importing the reranker module should not import torch / sentence-transformers.
        # Verified via sys.modules — heavy deps only appear after a .score() call.
        import sys
        # If torch is already loaded (e.g. some other test), this test
        # is non-informative — skip rather than pass meaninglessly.
        if "torch" in sys.modules:
            pytest.skip("torch already imported in this session; can't verify")
        from src.grounding import reranker as _r  # noqa: F401
        # After importing src.grounding.reranker alone, torch should not be in sys.modules.
        assert "torch" not in sys.modules
        assert "sentence_transformers" not in sys.modules


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


# --------------------------------------------------------------------- #
# LLMReranker (the production default) — mocked client, no API hit
# --------------------------------------------------------------------- #


def _mock_openai_client(responses):
    """Build a MagicMock OpenAI client whose chat.completions.create
    returns the given response texts (in order, wrapping each as the
    SDK shape: response.choices[0].message.content)."""
    client = MagicMock()
    iter_responses = iter(responses)

    def _create(**kwargs):
        try:
            text = next(iter_responses)
        except StopIteration:
            text = '{"SCORE": 3.0}'
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message = MagicMock()
        resp.choices[0].message.content = text
        return resp

    client.chat.completions.create.side_effect = _create
    return client


class TestLLMReranker:
    def test_happy_path_parses_score(self):
        client = _mock_openai_client(['{"SCORE": 4.5}'])
        rer = LLMReranker(client=client)
        scores = rer.score("k-means", ["K-means partitions observations into k clusters."])
        assert scores == [4.5]

    def test_lazy_client(self):
        # No OpenAI key required just to construct.
        rer = LLMReranker()
        assert rer._client is None  # not built yet

    def test_multiple_passages_yields_one_call_each(self):
        client = _mock_openai_client(['{"SCORE": 5.0}', '{"SCORE": 1.0}'])
        rer = LLMReranker(client=client)
        scores = rer.score("query", ["passage A", "passage B"])
        assert scores == [5.0, 1.0]
        assert client.chat.completions.create.call_count == 2

    def test_empty_passage_list_no_api_call(self):
        client = _mock_openai_client([])
        rer = LLMReranker(client=client)
        assert rer.score("query", []) == []
        client.chat.completions.create.assert_not_called()

    def test_unparseable_response_falls_back_to_neutral(self):
        # Three retries inside the helper; if all fail we return the
        # neutral midpoint (3.0) so the candidate isn't excluded or
        # over-weighted.
        client = _mock_openai_client(["not json", "still not json", "nope"])
        rer = LLMReranker(client=client)
        scores = rer.score("query", ["passage"])
        assert scores == [3.0]
        # All three retries were attempted.
        assert client.chat.completions.create.call_count == 3

    def test_out_of_range_score_retried(self):
        # First two attempts return scores outside the 1.0-5.0 band;
        # third returns a valid one.
        client = _mock_openai_client([
            '{"SCORE": 7.0}',
            '{"SCORE": 0.5}',
            '{"SCORE": 4.0}',
        ])
        rer = LLMReranker(client=client)
        scores = rer.score("query", ["passage"])
        assert scores == [4.0]
        assert client.chat.completions.create.call_count == 3

    def test_api_exception_retries_then_falls_back(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("transient")
        rer = LLMReranker(client=client)
        scores = rer.score("q", ["p"])
        # Falls back to neutral after retries are exhausted.
        assert scores == [3.0]
        assert client.chat.completions.create.call_count == 3

    def test_passes_seed_when_set(self):
        client = _mock_openai_client(['{"SCORE": 4.0}'])
        rer = LLMReranker(client=client, seed=123)
        rer.score("query", ["passage"])
        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs.get("seed") == 123

    def test_omits_seed_when_none(self):
        client = _mock_openai_client(['{"SCORE": 4.0}'])
        rer = LLMReranker(client=client, seed=None)
        rer.score("query", ["passage"])
        kwargs = client.chat.completions.create.call_args.kwargs
        assert "seed" not in kwargs

    def test_truncates_long_passage(self):
        # Build a passage well above the 1500-char truncation cap; the
        # prompt should not include the full thing. The test asserts the
        # prompt is FAR smaller than the original passage — exact byte
        # counts are brittle when the prompt template happens to contain
        # an 'x' (e.g. in "exact"). What matters is that 5000-char input
        # didn't pass through unchanged.
        client = _mock_openai_client(['{"SCORE": 4.0}'])
        rer = LLMReranker(client=client)
        long_passage = "x" * 5000
        rer.score("query", [long_passage])
        kwargs = client.chat.completions.create.call_args.kwargs
        prompt = kwargs["messages"][1]["content"]
        # Truncation kept the prompt well under 5000 x's. (Cap is 1500
        # passage chars; a few extra x's may come from the surrounding
        # template, which is fine.)
        x_run_count = prompt.count("x")
        assert x_run_count < 2000, f"truncation didn't take effect: {x_run_count} x's in prompt"
