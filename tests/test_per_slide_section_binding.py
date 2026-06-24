"""Tests for v6 Lever D — per-slide section binding.

Validates (1) ``_pick_per_slide_sections`` narrows from the chapter-wide
section_ids to the top-K best-matched sections for a slide query,
(2) the wrapper falls back gracefully on the vanilla path, and (3) the
``section_ids_override`` parameter actually narrows the retriever call.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


@dataclass
class _StubChunk:
    section_id: str
    page_start: int = 1
    page_end: int = 1
    textbook_id: str = "tb"
    chapter_title: str = "Ch"
    section_title: str = "Sec"
    text: str = "passage"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [
            f"[{self.textbook_id}:{self.section_id}:p{p:02d}]"
            for p in range(self.page_start, self.page_end + 1)
        ]

    def page_range_label(self) -> str:
        return f"p{self.page_start}"


@dataclass
class _StubResult:
    chunk: _StubChunk


class _RecordingRetriever:
    """Records search calls so the test can assert what section_ids were
    actually passed. Returns deterministic results per query."""
    def __init__(self, kb_chunks, ranking_by_query=None):
        self.kb = MagicMock(chunks=kb_chunks)
        self.calls = []
        self._ranking_by_query = ranking_by_query or {}

    def search(self, query, top_k=6, section_ids=None):
        self.calls.append({"query": query, "top_k": top_k, "section_ids": section_ids})
        # Return results matching the ranking_by_query mapping, or all chunks
        ranking = self._ranking_by_query.get(query, self.kb.chunks)
        return [_StubResult(c) for c in ranking[:top_k]]


def _build_deliberation_with_retriever(retriever, section_ids):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = retriever
    d.section_ids = section_ids
    d.textbook_id = "tb"
    d._evidence_top_k = 6
    return d


class TestPickPerSlideSections:
    def test_returns_none_when_no_retriever(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        d.section_ids = ["ch1.s1", "ch1.s2"]
        assert d._pick_per_slide_sections("query") is None

    def test_returns_none_when_no_section_ids(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = MagicMock()
        d.section_ids = None
        assert d._pick_per_slide_sections("query") is None

    def test_returns_none_when_empty_section_ids(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = MagicMock()
        d.section_ids = []
        assert d._pick_per_slide_sections("query") is None

    def test_picks_top_section_from_retrieval(self):
        # When all retrieval results point at one section, that section
        # is returned as the per-slide pick.
        kb_chunks = [
            _StubChunk("ch6.s2", page_start=1),
            _StubChunk("ch6.s2", page_start=2),
            _StubChunk("ch6.s2", page_start=3),
        ]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch6.s2", "ch1.s1"])
        sections = d._pick_per_slide_sections("clustering")
        assert sections == ["ch6.s2"]

    def test_picks_top_n_sections(self):
        kb_chunks = [
            _StubChunk("ch6.s2"), _StubChunk("ch1.s1"), _StubChunk("ch3.s4"),
            _StubChunk("ch6.s2"), _StubChunk("ch1.s1"),
        ]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(
            retriever, ["ch6.s2", "ch1.s1", "ch3.s4"]
        )
        sections = d._pick_per_slide_sections("topic")
        # _PER_SLIDE_TOP_SECTIONS default is 2
        assert len(sections) == 2
        # ch6.s2 appears first + most often → highest RRF score
        assert sections[0] == "ch6.s2"

    def test_query_passed_to_retriever(self):
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1"])
        d._pick_per_slide_sections("k-means clustering")
        assert retriever.calls[0]["query"] == "k-means clustering"

    def test_chapter_section_ids_passed_to_retriever(self):
        # The per-slide pick runs WITHIN the chapter's bound sections
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1", "ch2.s3"])
        d._pick_per_slide_sections("q")
        assert retriever.calls[0]["section_ids"] == ["ch1.s1", "ch2.s3"]

    def test_retrieval_exception_returns_none(self):
        retriever = MagicMock()
        retriever.kb = MagicMock(chunks=[])
        retriever.search.side_effect = RuntimeError("boom")
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1"])
        assert d._pick_per_slide_sections("q") is None

    def test_empty_results_returns_none(self):
        kb_chunks = []
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1"])
        assert d._pick_per_slide_sections("q") is None


class TestBuildPerSlideEvidenceWrapper:
    def test_narrows_section_filter_in_evidence_call(self):
        # The wrapper should: (1) call _pick_per_slide_sections, then
        # (2) call _build_evidence_block with that narrower filter.
        kb_chunks = [_StubChunk("ch6.s2")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch6.s2", "ch1.s1"])
        # The wrapper triggers two retriever.search calls:
        #   1st: by _pick_per_slide_sections (returns top section_ids subset)
        #   2nd: by _build_evidence_block (with the narrowed filter)
        d._build_per_slide_evidence("clustering query")
        assert len(retriever.calls) == 2
        # First call is the per-slide pick — uses chapter-wide section_ids
        assert retriever.calls[0]["section_ids"] == ["ch6.s2", "ch1.s1"]
        # Second call is the evidence build — uses the narrowed pick
        assert retriever.calls[1]["section_ids"] == ["ch6.s2"]

    def test_vanilla_path_no_retriever_returns_empty(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        d.section_ids = None
        d.textbook_id = None
        d._evidence_top_k = 6
        ev, rules = d._build_per_slide_evidence("query")
        assert ev == ""
        assert rules == ""


class TestSectionIdsOverrideInBuildEvidenceBlock:
    def test_override_replaces_self_section_ids(self):
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1", "ch2.s3", "ch4.s5"])
        d._build_evidence_block("q", section_ids_override=["ch2.s3"])
        # Only one search call (no per-slide narrowing here)
        assert retriever.calls[0]["section_ids"] == ["ch2.s3"]

    def test_no_override_uses_chapter_section_ids(self):
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation_with_retriever(retriever, ["ch1.s1", "ch2.s3"])
        d._build_evidence_block("q")  # no override
        assert retriever.calls[0]["section_ids"] == ["ch1.s1", "ch2.s3"]
