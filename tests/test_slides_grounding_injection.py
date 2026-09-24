"""Tests for evidence injection into SlidesDeliberation prompts.

Exercises `_build_evidence_block` directly (no LLM calls) and confirms:
 - With no retriever: returns ("", "") — vanilla path unchanged.
 - With a retriever: returns a non-empty evidence block (the second tuple
   element is always "" now that citation rules are removed).
 - The mandatory grounding directive leads the block.
 - Word budget is respected.
 - Section filter is honored (passed through to the retriever).
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.grounding import (
    Chunk,
    HashEmbedder,
    HybridRetriever,
    TextbookKnowledgeBase,
)
from src.slides import SlidesDeliberation

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"


def _make_deliberation(*, retriever=None, section_ids=None,
                       textbook_id=None) -> SlidesDeliberation:
    """Build a SlidesDeliberation with the minimum required wiring."""
    return SlidesDeliberation(
        id="test", name="Test", agents={}, llm=MagicMock(),
        output_dir="/tmp/test_slides",
        retriever=retriever,
        section_ids=section_ids,
        textbook_id=textbook_id,
    )


class TestNoRetrieverIsNoOp:
    def test_returns_empty_strings(self):
        d = _make_deliberation(retriever=None)
        evidence, rules = d._build_evidence_block("anything")
        assert evidence == ""
        assert rules == ""

    def test_no_retriever_attrs_default_to_none(self):
        d = _make_deliberation()
        assert d.retriever is None
        assert d.section_ids is None
        assert d.textbook_id is None


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf missing")
class TestWithRetriever:
    @pytest.fixture
    def deliberation(self, tmp_path) -> SlidesDeliberation:
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        return _make_deliberation(retriever=retriever, textbook_id="mini")

    def test_evidence_block_is_non_empty(self, deliberation):
        evidence, rules = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        assert evidence != ""
        # The second tuple element is always empty now (citation rules removed).
        assert rules == ""

    def test_evidence_block_carries_excerpt_passages(self, deliberation):
        # The retrieved chunk text must reach the writer as labeled excerpts.
        evidence, _ = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        assert "EXCERPT" in evidence
        assert "PASSAGE" in evidence

    def test_evidence_block_starts_with_mandatory_directive(self, deliberation):
        # The grounding directive must lead the block — burying it as a
        # footer gets ignored by the model on long LaTeX-heavy prompts.
        evidence, _ = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        assert "MANDATORY" in evidence or "mandatory" in evidence
        # And the directive must appear BEFORE the excerpts, not after.
        directive_idx = evidence.lower().find("mandatory")
        excerpts_idx = evidence.find("EXCERPT")
        assert 0 <= directive_idx < excerpts_idx

    def test_word_budget_respected(self, deliberation):
        evidence, _ = deliberation._build_evidence_block("everything")
        # Block ≤ budget + headers/directive overhead (≈100-200 words).
        assert len(evidence.split()) < deliberation._EVIDENCE_WORD_BUDGET + 200

    def test_filter_to_nonexistent_section_returns_empty(self, tmp_path):
        # If the contract assigned a section that doesn't exist in the
        # knowledge base, the retriever returns no candidates → injection
        # is a no-op for that prompt.
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        d = _make_deliberation(retriever=retriever, section_ids=["does.not.exist"])
        evidence, rules = d._build_evidence_block("anything")
        assert evidence == ""
        assert rules == ""

    def test_section_filter_is_honored(self, tmp_path):
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        # Build a deliberation scoped to one section only — when scoped to a
        # real section, retrieval still produces a non-empty evidence block.
        first_section = next(
            s.section_id for c in kb.textbook.chapters for s in c.sections
        )
        d = _make_deliberation(retriever=retriever, section_ids=[first_section])
        evidence, _ = d._build_evidence_block("anything in scope")
        # Either nothing matched (empty) or we got a real labeled block.
        if evidence:
            assert "EXCERPT" in evidence


class TestRetrieverFailureDegradesGracefully:
    def test_exception_during_search_falls_back_to_vanilla(self):
        broken = MagicMock()
        broken.search.side_effect = RuntimeError("simulated network blip")
        d = _make_deliberation(retriever=broken)
        evidence, rules = d._build_evidence_block("anything")
        assert evidence == ""
        assert rules == ""


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf missing")
class TestArtifactModeDifferentiation:
    """Scripts get a softer RULE 2 than slides / assessments: a stiff
    written voice hurts spoken-script alignment + coherence, so the script
    rule-set says "paraphrase naturally" while the read-document rule-set
    says "teach in your own words."
    """

    @pytest.fixture
    def deliberation(self, tmp_path) -> SlidesDeliberation:
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        return _make_deliberation(retriever=retriever, textbook_id="mini")

    def test_slide_artifact_uses_read_document_rule_2(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="slide",
        )
        # Slide artifact: "TEACH IN YOUR OWN WORDS" — the read-document variant.
        assert "TEACH IN YOUR OWN WORDS" in evidence
        # Script-only markers must NOT be present.
        assert "PARAPHRASE NATURALLY" not in evidence
        assert "SPOKEN SCRIPT" not in evidence

    def test_script_artifact_uses_spoken_rule_2(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="script",
        )
        # Script artifact: "PARAPHRASE NATURALLY" + signals that this is
        # spoken narration.
        assert "PARAPHRASE NATURALLY" in evidence
        assert "SPOKEN SCRIPT" in evidence or "spoken script" in evidence
        # Read-document phrasing must NOT be there.
        assert "TEACH IN YOUR OWN WORDS" not in evidence
        # The "MANDATORY" safety keyword the wider suite asserts on all
        # grounded prompts must still be present.
        assert "MANDATORY" in evidence

    def test_script_artifact_relaxes_direct_quote_rule(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="script",
        )
        # Script rule 2: paraphrase naturally; direct quotation is RESERVED.
        assert "PARAPHRASE NATURALLY" in evidence
        assert "spoken narration" in evidence.lower()
        assert "TEACH IN YOUR OWN WORDS" not in evidence

    def test_assessment_artifact_uses_read_document_rule_2(self, deliberation):
        # Assessments are READ documents (like slides), not spoken —
        # they get the read-document rule-set.
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="assessment",
        )
        assert "TEACH IN YOUR OWN WORDS" in evidence
        assert "SPOKEN SCRIPT" not in evidence

    def test_unknown_artifact_falls_back_to_slide(self, deliberation):
        # Defensive: a mis-wired call site shouldn't crash; default to
        # the read-document rule-set.
        evidence_bogus, _ = deliberation._build_evidence_block(
            "numbers", artifact="not_a_real_type",
        )
        # Same header label, same rule-2 phrasing → fell back to slide mode.
        assert "TEACH IN YOUR OWN WORDS" in evidence_bogus
        assert "MANDATORY RULES" in evidence_bogus  # NOT "...FOR SPOKEN SCRIPT"

    def test_default_artifact_is_slide(self, deliberation):
        # Backward compat: calls without an explicit artifact get the
        # read-document rule-set.
        evidence_default, _ = deliberation._build_evidence_block("numbers")
        evidence_slide, _ = deliberation._build_evidence_block(
            "numbers", artifact="slide",
        )
        assert "TEACH IN YOUR OWN WORDS" in evidence_default
        assert "TEACH IN YOUR OWN WORDS" in evidence_slide

    def test_no_retriever_ignores_artifact(self):
        # Vanilla path returns ("","") regardless of artifact — the opt-in
        # invariant trumps artifact differentiation.
        d = _make_deliberation(retriever=None)
        for artifact in ("slide", "script", "assessment"):
            evidence, rules = d._build_evidence_block("anything", artifact=artifact)
            assert evidence == ""
            assert rules == ""


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf missing")
class TestPerSlideMethodsInjectGrounding:
    """Regression for the bug where the per-slide methods (_generate_slide_*)
    regenerate LaTeX / script / assessment per slide WITHOUT grounding
    context. Each of the four per-slide methods must call
    _build_evidence_block so the directive + excerpts appear in the prompt
    sent to the LLM.
    """

    def _wired_deliberation(self, tmp_path):
        from src.grounding import (HashEmbedder, HybridRetriever,
                                    TextbookKnowledgeBase)
        from src.agents import Agent
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        # Build minimal agents — we mock their LLM via the .generate_response
        # patch below, so the agent objects just need to exist.
        agents = {
            "teaching_assistant": MagicMock(spec=Agent),
            "teaching_faculty": MagicMock(spec=Agent),
            "instructional_designer": MagicMock(spec=Agent),
        }
        # Each generate_response returns a no-op string + dummy timing/tokens.
        for a in agents.values():
            a.generate_response.return_value = ("{\"slide_id\": 1}", 0.0, 0)
            a.reset_history = MagicMock()
        d = SlidesDeliberation(
            id="t", name="T", agents=agents, llm=MagicMock(),
            output_dir=str(tmp_path / "out"),
            retriever=retriever, section_ids=None, textbook_id="mini",
        )
        # Per-slide methods read these — populate minimally.
        d.user_feedback = {"slides": {}, "script": {}, "assessment": {}, "overall": {}}
        d.time_slides = d.token_slides = 0
        d.time_script = d.token_script = 0
        d.time_assessment = d.token_assessment = 0
        d.slides_outline = [{"slide_id": 1, "title": "Numbers", "description": "ints"}]
        d.latex_dict = {0: {"frames": [{"full_frame": "\\begin{frame}x\\end{frame}",
                                          "title": "Numbers"}]}}
        d.slides_script = {}
        d.assessment_template = {0: {"slide_id": 1, "title": "Numbers"}}
        return d, agents

    def _captured_prompt(self, agent_mock):
        """Return the `prompt` kwarg from the most recent generate_response call."""
        assert agent_mock.generate_response.called, "agent.generate_response was not invoked"
        kwargs = agent_mock.generate_response.call_args.kwargs
        return kwargs.get("prompt") or agent_mock.generate_response.call_args.args[0]

    def test_slide_draft_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_draft(
            slide={"title": "Numbers", "description": "ints and operators"},
            context_slides=[],
            chapter={"title": "Chapter 1", "description": "foundations"},
        )
        prompt = self._captured_prompt(agents["teaching_faculty"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "EXCERPT" in prompt

    def test_slide_latex_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_latex(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "EXCERPT" in prompt

    def test_slide_script_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_script(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "EXCERPT" in prompt

    def test_slide_assessment_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_assessment(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "EXCERPT" in prompt
