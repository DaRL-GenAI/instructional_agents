"""Tests for v6 Lever I — anchor-then-paraphrase prompt rewrite.

The slide/assessment Rule 2 now mandates a verbatim quote BEFORE
paraphrasing any factual claim. This locks in the new wording so an
accidental revert is caught.
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
    textbook_id: str = "han"
    chapter_title: str = "Ch"
    section_title: str = "Sec"
    text: str = "K-means clustering partitions n observations into k clusters"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [self.citation_token()]

    def page_range_label(self) -> str:
        return f"p{self.page_start}"


@dataclass
class _StubResult:
    chunk: _StubChunk


def _build_deliberation():
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    retriever = MagicMock()
    retriever.search.return_value = [_StubResult(_StubChunk("ch1.s1"))]
    retriever.kb = MagicMock(chunks=[_StubChunk("ch1.s1")])
    d.retriever = retriever
    d.section_ids = None
    d.textbook_id = "han"
    d._evidence_top_k = 6
    d.citation_usage_tracker = None
    return d


class TestAnchorThenParaphraseRule:
    def test_rule_2_label_renamed(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        assert "RULE 2 (ANCHOR-THEN-PARAPHRASE" in ev

    def test_v7_slot_fill_template_present(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        # v7: slot-fill template with literal <<...>> placeholders
        assert "<<verbatim phrase from excerpt>>" in ev
        assert "<<your one-sentence elaboration" in ev

    def test_v7_hard_constraints_present(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        assert "HARD CONSTRAINTS" in ev
        assert "letter-for-letter" in ev
        assert "NO NEW FACTS" in ev

    def test_v7_definition_mandate(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        # v7: verbatim quote MANDATORY for definitions
        assert "MANDATORY" in ev

    def test_assessment_inherits_strict_rule_2(self):
        # Assessments share the strict rule-set with slides
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="assessment")
        assert "ANCHOR-THEN-PARAPHRASE" in ev
        assert "<<verbatim phrase from excerpt>>" in ev

    def test_script_does_not_use_anchor_then_paraphrase(self):
        # Script artifact keeps its softer "paraphrase naturally" rule
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="script")
        assert "ANCHOR-THEN-PARAPHRASE" not in ev
        assert "PARAPHRASE NATURALLY" in ev
