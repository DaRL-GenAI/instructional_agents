"""Tests for evidence injection into SlidesDeliberation prompts.

Exercises `_build_evidence_block` directly (no LLM calls) and confirms:
 - With no retriever: returns ("", "") — vanilla path unchanged.
 - With a retriever: returns a non-empty evidence block + citation rules.
 - Each retrieved chunk's citation token appears in the block.
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
        assert rules != ""

    def test_evidence_carries_citation_tokens(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        # Tokens look like `[mini:ch1.s1:p01]`.
        assert "[mini:" in evidence

    def test_evidence_block_starts_with_mandatory_directive(self, deliberation):
        # Citation instruction must lead the block — burying it as a footer
        # gets ignored by the model on long LaTeX-heavy prompts. See
        # the 2026-05-26 grounded-run citation-density debug for context.
        evidence, _ = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        assert "MANDATORY" in evidence or "mandatory" in evidence
        assert "MUST" in evidence
        # And the directive must appear BEFORE the first excerpt's token, not after.
        directive_idx = evidence.lower().find("mandatory")
        first_token_idx = evidence.find("[mini:")
        assert 0 <= directive_idx < first_token_idx

    def test_evidence_block_contains_concrete_example(self, deliberation):
        # The example sentence — with a real token from this textbook —
        # gives the model a literal pattern to imitate. Improves
        # citation density vs. a generic "cite using a token" instruction.
        evidence, _ = deliberation._build_evidence_block(
            "numbers and arithmetic operators"
        )
        assert "Example" in evidence or "example" in evidence
        # Example sentence must contain a real [mini:...] token.
        # Search the substring that follows the word "Example".
        example_region = evidence.split("Example", 1)[-1]
        assert "[mini:" in example_region

    def test_citation_rules_mention_inline_citation(self, deliberation):
        _, rules = deliberation._build_evidence_block("numbers")
        assert "cite" in rules.lower() or "citation" in rules.lower()
        assert "[mini:" in rules  # the example token reference

    def test_word_budget_respected(self, deliberation):
        evidence, _ = deliberation._build_evidence_block("everything")
        # Block ≤ budget + headers/directive/example overhead (≈100-200 words).
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
        # Build a deliberation scoped to one section only.
        first_section = next(
            s.section_id for c in kb.textbook.chapters for s in c.sections
        )
        d = _make_deliberation(retriever=retriever, section_ids=[first_section])
        evidence, _ = d._build_evidence_block("anything in scope")
        if evidence:
            # If anything came back, every citation token must point at the
            # allowed section.
            assert all(
                first_section in line
                for line in evidence.splitlines()
                if line.startswith("[mini:")
            )


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
    """Phase fix (2026-05-27): scripts get a softer rule-set than slides /
    assessments. The strict "cite every claim + direct-quote definitions"
    rules hurt script alignment + coherence by -0.66 vs vanilla in the
    Re-eval #1 numbers; differentiating fixes that without weakening
    slide-side citation discipline.
    """

    @pytest.fixture
    def deliberation(self, tmp_path) -> SlidesDeliberation:
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        return _make_deliberation(retriever=retriever, textbook_id="mini")

    def test_slide_artifact_uses_strict_rule_1(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="slide",
        )
        # Slide artifact: "CITE EVERY SOURCED CLAIM" — the strict variant.
        assert "CITE EVERY SOURCED CLAIM" in evidence
        # Script-only marker must NOT be present.
        assert "CITE EACH CONCEPT, NOT EACH SENTENCE" not in evidence
        assert "SPOKEN SCRIPT" not in evidence

    def test_script_artifact_uses_softer_rule_1(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="script",
        )
        # Script artifact: "CITE EACH CONCEPT, NOT EACH SENTENCE" + signals
        # that this is spoken narration.
        assert "CITE EACH CONCEPT, NOT EACH SENTENCE" in evidence
        assert "SPOKEN SCRIPT" in evidence or "spoken script" in evidence
        # Strict-slide phrasing must NOT be there.
        assert "CITE EVERY SOURCED CLAIM" not in evidence
        # And the "MANDATORY" safety keyword the wider test suite asserts on
        # all grounded prompts must still be present.
        assert "MANDATORY" in evidence

    def test_script_artifact_relaxes_direct_quote_rule(self, deliberation):
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="script",
        )
        # Script rule 2: paraphrase naturally; direct quotation is RESERVED.
        assert "PARAPHRASE NATURALLY" in evidence
        assert "spoken narration" in evidence.lower()
        # Strict-slide rule-2 ("ANCHOR TO SOURCE WORDING") must NOT be in
        # the script's directive block (different framing entirely).
        assert "ANCHOR TO SOURCE WORDING" not in evidence

    def test_assessment_artifact_uses_strict_rules(self, deliberation):
        # Assessments are READ documents (like slides), not spoken —
        # they get the strict rule-set.
        evidence, _ = deliberation._build_evidence_block(
            "numbers", artifact="assessment",
        )
        assert "CITE EVERY SOURCED CLAIM" in evidence
        assert "ANCHOR TO SOURCE WORDING" in evidence
        assert "SPOKEN SCRIPT" not in evidence

    def test_unknown_artifact_falls_back_to_slide(self, deliberation):
        # Defensive: a mis-wired call site shouldn't crash; default to
        # the strict rule-set (over-citing > under-citing).
        evidence_bogus, _ = deliberation._build_evidence_block(
            "numbers", artifact="not_a_real_type",
        )
        evidence_slide, _ = deliberation._build_evidence_block(
            "numbers", artifact="slide",
        )
        # Same header label, same rule-1 phrasing → fell back to slide mode.
        assert "CITE EVERY SOURCED CLAIM" in evidence_bogus
        assert "MANDATORY RULES" in evidence_bogus  # NOT "MANDATORY RULES FOR SPOKEN SCRIPT"

    def test_default_artifact_is_slide(self, deliberation):
        # Backward compat: calls without an explicit artifact get the
        # strict slide rule-set (matches the pre-2026-05-27 behavior).
        evidence_default, _ = deliberation._build_evidence_block("numbers")
        evidence_slide, _ = deliberation._build_evidence_block(
            "numbers", artifact="slide",
        )
        # Both share the strict rule-1 phrasing.
        assert "CITE EVERY SOURCED CLAIM" in evidence_default
        assert "CITE EVERY SOURCED CLAIM" in evidence_slide

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
    overwrite the template-stage citations because they regenerate LaTeX /
    script / assessment per slide WITHOUT grounding context. Each of the
    four per-slide methods must call _build_evidence_block so the directive
    + excerpts appear in the prompt sent to the LLM.
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
        assert "[mini:" in prompt

    def test_slide_latex_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_latex(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "[mini:" in prompt

    def test_slide_script_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_script(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "[mini:" in prompt

    def test_slide_assessment_prompt_contains_grounding(self, tmp_path):
        d, agents = self._wired_deliberation(tmp_path)
        d._generate_slide_assessment(
            slide_idx=0,
            slide={"title": "Numbers", "description": "ints and operators"},
            slide_draft="Numbers are basic.",
        )
        prompt = self._captured_prompt(agents["teaching_assistant"])
        assert "MANDATORY" in prompt.upper() or "GROUNDING REQUIREMENT" in prompt
        assert "[mini:" in prompt
