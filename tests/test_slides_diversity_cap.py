"""Tests for the v6 Lever A wiring inside SlidesDeliberation.

Verifies (1) the cap filters retrieval results when a chunk is over
cap, (2) the post-output increment fires on every LLM response, and
(3) the vanilla path (tracker=None) leaves behavior unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

from src.grounding.usage_tracker import CitationUsageTracker
from src.slides import SlidesDeliberation


@dataclass
class _StubChunk:
    textbook_id: str
    section_id: str
    page_start: int
    page_end: int
    text: str = "passage"
    chapter_title: str = "Ch"
    section_title: str = "Sec"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [
            f"[{self.textbook_id}:{self.section_id}:p{p:02d}]"
            for p in range(self.page_start, self.page_end + 1)
        ]

    def page_range_label(self) -> str:
        if self.page_start == self.page_end:
            return f"p{self.page_start}"
        return f"p{self.page_start}-p{self.page_end}"


@dataclass
class _StubResult:
    chunk: _StubChunk


class _StubKB:
    def __init__(self, chunks):
        self.chunks = chunks


class _StubRetriever:
    def __init__(self, results, kb):
        self._results = results
        self.kb = kb

    def search(self, query, top_k=6, section_ids=None):
        return list(self._results)


def _build_deliberation_with_cap(chunks, tracker):
    """Construct a SlidesDeliberation bypassing __init__ — wires only
    the fields _build_evidence_block reads."""
    kb = _StubKB(chunks)
    results = [_StubResult(c) for c in chunks]
    retriever = _StubRetriever(results, kb)
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = retriever
    d.section_ids = None
    d.textbook_id = "han"
    d._evidence_top_k = 6
    d.citation_usage_tracker = tracker
    return d


class TestCapFilteringInEvidenceBlock:
    def test_under_cap_chunk_appears_in_evidence(self):
        kb_chunks = [
            _StubChunk("han", "ch1.s1", 1, 1, text="under-cap chunk"),
            _StubChunk("han", "ch2.s1", 5, 5, text="other chunk"),
        ]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        d = _build_deliberation_with_cap(kb_chunks, tracker)
        ev, _ = d._build_evidence_block("query")
        assert "[han:ch1.s1:p01]" in ev
        assert "[han:ch2.s1:p05]" in ev

    def test_over_cap_chunk_dropped_from_evidence(self):
        kb_chunks = [
            _StubChunk("han", "ch1.s1", 1, 1, text="over-cap chunk"),
            _StubChunk("han", "ch2.s1", 5, 5, text="other chunk"),
        ]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        # Push first chunk to cap
        tracker.scan_and_increment("[han:ch1.s1:p01] " * 15)
        d = _build_deliberation_with_cap(kb_chunks, tracker)
        ev, _ = d._build_evidence_block("query")
        assert "[han:ch1.s1:p01]" not in ev
        assert "[han:ch2.s1:p05]" in ev

    def test_all_over_cap_falls_back_to_empty(self):
        # When every candidate is over cap, return empty evidence
        # (vanilla prompt). Beats emitting an empty grounding header.
        kb_chunks = [_StubChunk("han", "ch1.s1", 1, 1)]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        tracker.scan_and_increment("[han:ch1.s1:p01] " * 20)
        d = _build_deliberation_with_cap(kb_chunks, tracker)
        ev, rules = d._build_evidence_block("query")
        assert ev == ""
        assert rules == ""

    def test_vanilla_path_no_tracker(self):
        # tracker=None → no filtering, behavior unchanged
        kb_chunks = [_StubChunk("han", "ch1.s1", 1, 1)]
        d = _build_deliberation_with_cap(kb_chunks, tracker=None)
        ev, _ = d._build_evidence_block("query")
        assert "[han:ch1.s1:p01]" in ev


class TestRecordEmittedCitations:
    def test_vanilla_path_record_is_no_op(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.citation_usage_tracker = None
        # Must not crash, must not increment anything
        d._record_emitted_citations("any text [han:ch1.s1:p01]")

    def test_grounded_path_increments_tracker(self):
        kb_chunks = [_StubChunk("han", "ch1.s1", 1, 1)]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.citation_usage_tracker = tracker
        d._record_emitted_citations(
            "A claim [han:ch1.s1:p01] supported. Another [han:ch1.s1:p01]."
        )
        assert tracker.chunk_count(kb_chunks[0]) == 2

    def test_empty_output_no_op(self):
        kb_chunks = [_StubChunk("han", "ch1.s1", 1, 1)]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.citation_usage_tracker = tracker
        d._record_emitted_citations("")
        d._record_emitted_citations(None)
        assert tracker.chunk_count(kb_chunks[0]) == 0


class TestTrackerSharedAcrossChapters:
    """The tracker is constructed once per ADDIE run and passed to every
    chapter's SlidesDeliberation. Cap state must persist across chapters."""

    def test_two_deliberations_share_counter(self):
        kb_chunks = [_StubChunk("han", "ch1.s1", 1, 1)]
        tracker = CitationUsageTracker(_StubKB(kb_chunks), cap=15)
        d1 = SlidesDeliberation.__new__(SlidesDeliberation)
        d1.citation_usage_tracker = tracker
        d2 = SlidesDeliberation.__new__(SlidesDeliberation)
        d2.citation_usage_tracker = tracker
        d1._record_emitted_citations("[han:ch1.s1:p01] " * 8)
        d2._record_emitted_citations("[han:ch1.s1:p01] " * 8)
        assert tracker.chunk_count(kb_chunks[0]) == 16
        assert tracker.is_over_cap(kb_chunks[0])
