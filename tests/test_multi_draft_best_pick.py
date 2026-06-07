"""Tests for v6 Lever G — multi-draft + best-pick on _generate_slide_draft.

The slide-draft step generates two drafts and selects the one with more
resolvable citation tokens (higher grounding density). Tracker state
must reflect ONLY the winner's citations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

from src.grounding.usage_tracker import CitationUsageTracker
from src.slides import SlidesDeliberation


@dataclass
class _StubChunk:
    section_id: str
    page_start: int = 1
    page_end: int = 1
    textbook_id: str = "han"
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


class _StubKB:
    def __init__(self, chunks):
        self.chunks = chunks


def _build_deliberation_with_tracker(tracker):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = MagicMock()
    d.citation_usage_tracker = tracker
    d.time_slides = 0.0
    d.token_slides = 0
    return d


class TestBestOfNDraft:
    def test_winner_has_more_citations(self):
        kb = _StubKB([
            _StubChunk("ch1.s1", page_start=1, page_end=1),
            _StubChunk("ch2.s2", page_start=5, page_end=5),
            _StubChunk("ch3.s3", page_start=9, page_end=9),
        ])
        tracker = CitationUsageTracker(kb)
        d = _build_deliberation_with_tracker(tracker)

        # Stub agent returns 2 drafts: first has 1 cite, second has 3
        agent = MagicMock()
        agent.generate_response.side_effect = [
            ("draft 1: [han:ch1.s1:p01]", 0.1, 10),
            ("draft 2: [han:ch1.s1:p01] [han:ch2.s2:p05] [han:ch3.s3:p09]", 0.1, 10),
        ]
        winner = d._generate_best_of_n_draft(agent, "prompt", n=2)
        assert winner == "draft 2: [han:ch1.s1:p01] [han:ch2.s2:p05] [han:ch3.s3:p09]"
        # Only winner's increments stick — 1 each for the 3 distinct chunks
        assert tracker.chunk_count(kb.chunks[0]) == 1
        assert tracker.chunk_count(kb.chunks[1]) == 1
        assert tracker.chunk_count(kb.chunks[2]) == 1

    def test_loser_increments_rolled_back(self):
        # Even if loser had citations, those don't count toward cap.
        kb = _StubKB([_StubChunk("ch1.s1", page_start=1)])
        tracker = CitationUsageTracker(kb)
        d = _build_deliberation_with_tracker(tracker)
        agent = MagicMock()
        agent.generate_response.side_effect = [
            # Draft 1 wins (more cites)
            ("[han:ch1.s1:p01] " * 5, 0.1, 10),
            # Draft 2 loses (fewer cites)
            ("[han:ch1.s1:p01] " * 2, 0.1, 10),
        ]
        d._generate_best_of_n_draft(agent, "prompt", n=2)
        # Only winner's 5 citations should be in the tracker
        assert tracker.chunk_count(kb.chunks[0]) == 5

    def test_two_drafts_generated(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        tracker = CitationUsageTracker(kb)
        d = _build_deliberation_with_tracker(tracker)
        agent = MagicMock()
        agent.generate_response.side_effect = [
            ("draft 1", 0.1, 5),
            ("draft 2", 0.1, 5),
        ]
        d._generate_best_of_n_draft(agent, "prompt", n=2)
        assert agent.generate_response.call_count == 2

    def test_tie_picks_first_draft(self):
        # When all drafts score equally, max() returns the first
        kb = _StubKB([_StubChunk("ch1.s1")])
        tracker = CitationUsageTracker(kb)
        d = _build_deliberation_with_tracker(tracker)
        agent = MagicMock()
        agent.generate_response.side_effect = [
            ("draft 1 [han:ch1.s1:p01]", 0.1, 5),
            ("draft 2 [han:ch1.s1:p01]", 0.1, 5),
        ]
        winner = d._generate_best_of_n_draft(agent, "prompt", n=2)
        assert winner == "draft 1 [han:ch1.s1:p01]"


class TestDecrementTrackerForText:
    def test_decrements_resolvable_tokens(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        tracker = CitationUsageTracker(kb)
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        # First scan increments
        tracker.scan_and_increment("[han:ch1.s1:p01] " * 3)
        assert tracker.chunk_count(kb.chunks[0]) == 3
        # Decrement helper undoes 3
        d._decrement_tracker_for_text(tracker, "[han:ch1.s1:p01] " * 3)
        assert tracker.chunk_count(kb.chunks[0]) == 0

    def test_decrement_clamps_at_zero(self):
        # Edge case: never decrement below 0
        kb = _StubKB([_StubChunk("ch1.s1")])
        tracker = CitationUsageTracker(kb)
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        tracker.scan_and_increment("[han:ch1.s1:p01]")
        assert tracker.chunk_count(kb.chunks[0]) == 1
        # Decrement 3 times — should stop at 0, not go negative
        d._decrement_tracker_for_text(tracker, "[han:ch1.s1:p01] " * 3)
        assert tracker.chunk_count(kb.chunks[0]) == 0

    def test_empty_text_no_op(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        tracker = CitationUsageTracker(kb)
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        # Must not crash
        d._decrement_tracker_for_text(tracker, "")
        d._decrement_tracker_for_text(tracker, None)
