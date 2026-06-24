"""Tests for the AUDIENCE & APPROPRIATENESS outline-prompt block.

The block instructs the writer to commit to a learner level, define jargon on
first use, and anchor abstract ideas with concrete examples — targeting the
`appropriateness` rubric metric. It is grounded-path only (assembled inside the
`retriever is not None and section_ids` guard), so the vanilla outline prompt
must never contain it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


class _RecordingAgent:
    """Captures the prompt handed to the instructional_designer agent."""

    def __init__(self):
        self.prompt = None

    def reset_history(self):
        pass

    def generate_response(self, prompt, stream=False, save_to_history=False):
        self.prompt = prompt
        return ('[{"slide_id": 1, "title": "X", "description": "Y"}]', 0.0, 0)


def _delib(*, retriever=None, section_ids=None):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    agent = _RecordingAgent()
    d.agents = {"instructional_designer": agent}
    d.catalog_dict = {"slides_length": 30}
    d.retriever = retriever
    d.section_ids = section_ids
    d.user_feedback = {}
    d.time_slides = 0
    d.token_slides = 0
    d.slides_outline = []
    return d, agent


class TestAudienceBlock:
    def test_present_on_grounded_path(self):
        retr = MagicMock()
        retr.kb.chunks = []  # empty bound → only the unconditional blocks
        d, agent = _delib(retriever=retr, section_ids=["ch1.s1"])
        d._generate_slides_outline({"title": "T", "description": "D"})
        assert agent.prompt is not None
        assert "AUDIENCE & APPROPRIATENESS" in agent.prompt
        assert "Define each technical term" in agent.prompt
        assert "concrete example" in agent.prompt

    def test_absent_on_vanilla_path(self):
        # No retriever → no textbook_hints → the block must not appear, so the
        # vanilla outline prompt stays byte-identical to upstream.
        d, agent = _delib(retriever=None, section_ids=None)
        d._generate_slides_outline({"title": "T", "description": "D"})
        assert agent.prompt is not None
        assert "AUDIENCE & APPROPRIATENESS" not in agent.prompt
