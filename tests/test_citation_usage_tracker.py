"""Tests for the v6 diversity-cap tracker."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from src.grounding.usage_tracker import CitationUsageTracker


@dataclass
class _StubChunk:
    """Minimal Chunk shape — just the citation-token methods the
    tracker reads. Avoids importing the full KB stack in tests."""
    textbook_id: str
    section_id: str
    page_start: int
    page_end: int

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [
            f"[{self.textbook_id}:{self.section_id}:p{p:02d}]"
            for p in range(self.page_start, self.page_end + 1)
        ]


class _StubKB:
    def __init__(self, chunks):
        self.chunks = chunks


def _build_kb():
    return _StubKB([
        _StubChunk("han", "ch1.s1", 1, 1),
        _StubChunk("han", "ch3.s4", 15, 17),  # multi-page
        _StubChunk("han", "ch6.s2", 200, 200),
    ])


class TestCapBehavior:
    def test_under_cap_not_flagged(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        chunk = kb.chunks[0]
        t.scan_and_increment("a [han:ch1.s1:p01] b " * 5)
        assert t.chunk_count(chunk) == 5
        assert not t.is_over_cap(chunk)

    def test_at_cap_is_flagged(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        chunk = kb.chunks[0]
        t.scan_and_increment("[han:ch1.s1:p01] " * 15)
        assert t.chunk_count(chunk) == 15
        assert t.is_over_cap(chunk)

    def test_over_cap_is_flagged(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        chunk = kb.chunks[0]
        t.scan_and_increment("[han:ch1.s1:p01] " * 20)
        assert t.chunk_count(chunk) == 20
        assert t.is_over_cap(chunk)

    def test_default_cap_is_15(self):
        assert CitationUsageTracker.DEFAULT_CAP == 15
        t = CitationUsageTracker(None)
        assert t.cap == 15

    def test_custom_cap(self):
        t = CitationUsageTracker(None, cap=5)
        assert t.cap == 5


class TestMultiPageChunkMapping:
    def test_in_range_tokens_share_chunk_counter(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        multi = kb.chunks[1]  # ch3.s4 spans p15-p17
        # Each of p15, p16, p17 must increment the SAME chunk counter
        t.scan_and_increment(
            "claim [han:ch3.s4:p15]. another [han:ch3.s4:p16]. last [han:ch3.s4:p17]."
        )
        assert t.chunk_count(multi) == 3

    def test_canonical_token_is_page_start(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        multi = kb.chunks[1]  # p15-17, canonical = p15
        assert multi.citation_token() == "[han:ch3.s4:p15]"
        # All three pages increment the same key
        t.scan_and_increment("[han:ch3.s4:p17]")
        assert t.chunk_count(multi) == 1


class TestScanAndIncrement:
    def test_empty_text_no_op(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        assert t.scan_and_increment("") == 0
        assert t.scan_and_increment(None) == 0

    def test_returns_increment_count(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        n = t.scan_and_increment("a [han:ch1.s1:p01] b [han:ch6.s2:p200]")
        assert n == 2

    def test_unresolvable_token_not_counted(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        # ch99.s99 doesn't exist in our KB
        n = t.scan_and_increment("fake [han:ch99.s99:p01] phantom")
        assert n == 0

    def test_multiple_tokens_in_one_text(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        text = (
            "K-means [han:ch6.s2:p200] partitions n observations. "
            "Sum of squared errors [han:ch1.s1:p01] is the objective. "
            "Cluster validity [han:ch6.s2:p200] is harder."
        )
        n = t.scan_and_increment(text)
        assert n == 3
        assert t.chunk_count(kb.chunks[2]) == 2  # ch6.s2 cited twice
        assert t.chunk_count(kb.chunks[0]) == 1  # ch1.s1 cited once


class TestNoKBPath:
    """When kb=None (vanilla path), the tracker still constructs but
    can never report a chunk as over-cap because no chunks exist."""

    def test_construct_without_kb(self):
        t = CitationUsageTracker(None)
        assert t.cap == 15

    def test_scan_with_no_kb_no_op(self):
        t = CitationUsageTracker(None)
        n = t.scan_and_increment("[han:ch1.s1:p01]")
        assert n == 0


class TestReset:
    def test_reset_clears_counts(self):
        kb = _build_kb()
        t = CitationUsageTracker(kb, cap=15)
        t.scan_and_increment("[han:ch1.s1:p01] " * 10)
        assert t.chunk_count(kb.chunks[0]) == 10
        t.reset()
        assert t.chunk_count(kb.chunks[0]) == 0
        assert not t.is_over_cap(kb.chunks[0])
