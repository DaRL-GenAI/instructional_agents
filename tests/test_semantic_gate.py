"""Tests for v7 SemanticGate (Gate A pre-evidence + Gate B post-emit).

Uses a stub encoder so tests run instantly without downloading the
sentence-transformer model. Production code path uses the real encoder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List
import numpy as np

from src.grounding.semantic_gate import SemanticGate


@dataclass
class _StubChunk:
    section_id: str
    page_start: int = 1
    page_end: int = 1
    textbook_id: str = "han"
    text: str = "passage about K-means clustering with centroids"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [
            f"[{self.textbook_id}:{self.section_id}:p{p:02d}]"
            for p in range(self.page_start, self.page_end + 1)
        ]


@dataclass
class _StubResult:
    chunk: _StubChunk


class _StubKB:
    def __init__(self, chunks):
        self.chunks = chunks


class _StubEncoder:
    """Maps text → fake unit-vector by hashing words. Vectors with
    high word overlap have high cosine similarity, mimicking a
    sentence-transformer for tests."""
    def encode(self, text, convert_to_numpy=True, normalize_embeddings=True):
        # Hash bag-of-words to a deterministic vector
        words = text.lower().split()
        v = np.zeros(64)
        for w in words:
            v[hash(w) % 64] += 1.0
        n = np.linalg.norm(v)
        return v / n if n > 0 else v


def _gate_with_stub(kb_chunks):
    """Construct a SemanticGate with a stub encoder pre-loaded —
    bypasses lazy load + sentence-transformer dependency."""
    g = SemanticGate(kb=_StubKB(kb_chunks))
    g._encoder = _StubEncoder()
    return g


class TestSimilarity:
    def test_identical_strings_sim_one(self):
        g = _gate_with_stub([])
        assert abs(g.similarity("hello world", "hello world") - 1.0) < 1e-6

    def test_disjoint_strings_sim_low(self):
        # Hash-based stub encoder can collide on tiny vocab; use slightly
        # longer disjoint strings to dilute collision noise.
        g = _gate_with_stub([])
        s = g.similarity(
            "apples oranges bananas pears grapes mangoes",
            "automobile train airplane motorcycle bicycle scooter",
        )
        assert s < 0.5  # disjoint vocab → low similarity even with stub noise

    def test_overlapping_strings_sim_high(self):
        g = _gate_with_stub([])
        s = g.similarity(
            "K-means clustering partitions data into clusters",
            "K-means clustering centroids data clusters",
        )
        assert s > 0.5

    def test_empty_strings_returns_one(self):
        # Fail-safe — empty side returns 1 so the gate doesn't drop everything
        g = _gate_with_stub([])
        assert g.similarity("", "anything") == 1.0
        assert g.similarity("anything", "") == 1.0


class TestGateAFilter:
    def test_drops_below_threshold(self):
        chunks = [
            _StubChunk("ch6.s2", text="K-means clustering with centroids"),
            _StubChunk("ch1.s1", text="Database schemas and SQL queries"),
        ]
        g = _gate_with_stub(chunks)
        results = [_StubResult(c) for c in chunks]
        survivors = g.gate_a_filter_results(
            "K-means clustering algorithm", results, threshold=0.4,
        )
        # ch6.s2 matches; ch1.s1 doesn't
        assert any(r.chunk.section_id == "ch6.s2" for r in survivors)
        assert not any(r.chunk.section_id == "ch1.s1" for r in survivors)

    def test_keeps_top_when_all_below(self):
        chunks = [
            _StubChunk("ch1.s1", text="Database schemas"),
            _StubChunk("ch2.s2", text="SQL queries"),
        ]
        g = _gate_with_stub(chunks)
        results = [_StubResult(c) for c in chunks]
        # Query totally unrelated; both would fail strict threshold
        survivors = g.gate_a_filter_results(
            "neural network backpropagation", results, threshold=0.9,
        )
        # Defensive: never returns empty
        assert len(survivors) >= 1

    def test_no_op_on_empty_results(self):
        g = _gate_with_stub([])
        assert g.gate_a_filter_results("q", []) == []


class TestGateBStrip:
    def test_strips_low_similarity_citation(self):
        # Chunk text totally unrelated to the claim → strip
        chunks = [
            _StubChunk("ch99.s99", page_start=1, page_end=1,
                        text="Quantum entanglement and Bell inequalities"),
        ]
        g = _gate_with_stub(chunks)
        text = (
            "K-means clustering partitions data into k clusters "
            "[han:ch99.s99:p01] using nearest-mean assignment."
        )
        out = g.gate_b_strip_low_similarity(text, threshold=0.3)
        assert "[han:ch99.s99:p01]" not in out
        assert "K-means clustering partitions" in out
        assert "nearest-mean assignment" in out

    def test_keeps_high_similarity_citation(self):
        chunks = [
            _StubChunk("ch6.s2", page_start=1, page_end=1,
                        text="K-means clustering partitions data into k clusters using centroids"),
        ]
        g = _gate_with_stub(chunks)
        text = (
            "K-means clustering partitions data into k clusters "
            "[han:ch6.s2:p01]."
        )
        out = g.gate_b_strip_low_similarity(text, threshold=0.2)
        assert "[han:ch6.s2:p01]" in out

    def test_no_op_on_empty_text(self):
        g = _gate_with_stub([])
        assert g.gate_b_strip_low_similarity("") == ""
        assert g.gate_b_strip_low_similarity(None) is None

    def test_unknown_token_left_alone(self):
        chunks = [_StubChunk("ch1.s1")]
        g = _gate_with_stub(chunks)
        text = "Claim [han:ch99.s99:p01] cite that's not in KB."
        out = g.gate_b_strip_low_similarity(text, threshold=0.5)
        # Unknown token — Gate B leaves it (malformed-strip will handle)
        assert "[han:ch99.s99:p01]" in out


class TestEncoderFallback:
    def test_no_encoder_no_op(self):
        # When encoder fails to load, gates should be no-ops
        g = SemanticGate(kb=_StubKB([_StubChunk("ch1.s1")]))
        g._encoder = False  # simulate failed load
        # Gate A: returns results unchanged
        chunks = [_StubChunk("ch1.s1")]
        results = [_StubResult(c) for c in chunks]
        assert g.gate_a_filter_results("q", results) == results
        # Gate B: text unchanged
        text = "Claim [han:ch1.s1:p01]."
        assert g.gate_b_strip_low_similarity(text) == text


class TestClaimWindow:
    def test_takes_last_n_words(self):
        text = "alpha beta gamma delta epsilon zeta eta theta iota"
        out = SemanticGate._extract_claim_window(text, n_words=3)
        assert out == "eta theta iota"

    def test_uses_last_sentence(self):
        text = "First sentence here. Second sentence claims something."
        out = SemanticGate._extract_claim_window(text, n_words=25)
        assert "Second sentence" in out
        assert "First sentence" not in out
