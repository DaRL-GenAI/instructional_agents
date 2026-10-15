"""Tests for v6 Lever E — cross-chapter retrieval for assessment files.

The chapter-level + per-slide assessment generators bypass the
chapter's bound section_ids and search the full KB instead. Review
questions in an assessment commonly span the syllabus, so confining
them to the current chapter's bound sections is the wrong scope.
"""

from __future__ import annotations

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
    def __init__(self, kb_chunks):
        self.kb = MagicMock(chunks=kb_chunks)
        self.calls = []

    def search(self, query, top_k=6, section_ids=None):
        self.calls.append({"query": query, "top_k": top_k, "section_ids": section_ids})
        return [_StubResult(c) for c in self.kb.chunks[:top_k]]


def _build_deliberation(retriever, section_ids):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = retriever
    d.section_ids = section_ids
    d.textbook_id = "tb"
    d._evidence_top_k = 6
    return d


class TestCrossChapterFlag:
    def test_cross_chapter_true_bypasses_section_filter(self):
        kb_chunks = [_StubChunk("ch1.s1"), _StubChunk("ch6.s2")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation(retriever, ["ch1.s1"])  # chapter binding
        d._build_evidence_block("q", cross_chapter=True)
        # When cross_chapter=True, retriever called with section_ids=None
        assert retriever.calls[0]["section_ids"] is None

    def test_cross_chapter_false_uses_chapter_binding(self):
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation(retriever, ["ch1.s1", "ch6.s2"])
        d._build_evidence_block("q", cross_chapter=False)
        # Falls back to self.section_ids
        assert retriever.calls[0]["section_ids"] == ["ch1.s1", "ch6.s2"]

    def test_cross_chapter_overrides_section_ids_override(self):
        # If both override and cross_chapter are passed, cross_chapter wins
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation(retriever, ["ch1.s1", "ch6.s2"])
        d._build_evidence_block(
            "q", section_ids_override=["ch6.s2"], cross_chapter=True,
        )
        assert retriever.calls[0]["section_ids"] is None

    def test_default_cross_chapter_is_false(self):
        # No-op default: existing call sites that don't pass cross_chapter
        # should keep the chapter binding behavior.
        kb_chunks = [_StubChunk("ch1.s1")]
        retriever = _RecordingRetriever(kb_chunks)
        d = _build_deliberation(retriever, ["ch1.s1"])
        d._build_evidence_block("q")  # no cross_chapter passed
        assert retriever.calls[0]["section_ids"] == ["ch1.s1"]

    def test_vanilla_path_unaffected(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        d.section_ids = None
        d.textbook_id = None
        d._evidence_top_k = 6
        ev, rules = d._build_evidence_block("q", cross_chapter=True)
        # Vanilla path returns empty regardless of flag
        assert ev == ""
        assert rules == ""
