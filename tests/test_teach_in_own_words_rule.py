"""Tests for the slide/assessment RULE 2 — teach in your own words.

The earlier "anchor-then-paraphrase" rule mandated a verbatim quote before
any paraphrase. That was a holdover from the removed post-hoc grounding
scorer: the citation token it required is stripped at save time, leaving a
"quote" — gloss pattern on every slide. RULE 2 now instructs the writer to
teach in its own words (the write-time verifier checks semantic support,
not verbatim wording). This locks in the new wording so an accidental
revert to quote-dumping is caught.
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


class TestTeachInOwnWordsRule:
    def test_rule_2_label_is_teach_in_own_words(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        assert "RULE 2 (TEACH IN YOUR OWN WORDS" in ev

    def test_old_quote_dump_template_absent(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        # The removed slot-fill template and its label must be gone.
        assert "ANCHOR-THEN-PARAPHRASE" not in ev
        assert "<<verbatim phrase from excerpt>>" not in ev
        assert "letter-for-letter" not in ev

    def test_anti_quote_dump_constraints_present(self):
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="slide")
        assert "HARD CONSTRAINTS" in ev
        assert "no quote-dumping" in ev
        # Quotes reserved for precise definitions/formulas, capped per slide.
        assert "at most" in ev and "ONE short quote per slide" in ev
        # Algorithms shown as numbered steps, not quoted descriptions.
        assert "numbered procedure" in ev

    def test_assessment_inherits_teach_in_own_words(self):
        # Assessments share the read-document rule-set with slides.
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="assessment")
        assert "RULE 2 (TEACH IN YOUR OWN WORDS" in ev
        assert "ANCHOR-THEN-PARAPHRASE" not in ev

    def test_script_keeps_paraphrase_naturally(self):
        # Script artifact keeps its softer "paraphrase naturally" rule.
        d = _build_deliberation()
        ev, _ = d._build_evidence_block("clustering", artifact="script")
        assert "PARAPHRASE NATURALLY" in ev
        assert "TEACH IN YOUR OWN WORDS" not in ev
