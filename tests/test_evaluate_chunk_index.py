"""Tests for the GroundingAgent's per-page chunk index.

A multi-page chunk should register one index entry per page in its
range so the LLM can cite any in-range page and have the verifier
resolve it correctly.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from evaluate import GroundingAgent
from src.grounding.knowledge_base import Chunk


def _chunk(page_start: int, page_end: int, section_id: str = "ch1.s1") -> Chunk:
    return Chunk(
        chunk_id=f"t:{section_id}:c00", text="content",
        textbook_id="t", chapter_id=section_id.split(".")[0],
        chapter_title="C",
        section_id=section_id, section_title="S",
        para_ids=[f"{section_id}.p01"],
        page_start=page_start, page_end=page_end,
    )


def _kb(chunks):
    return SimpleNamespace(chunks=chunks)


class TestChunkIndexRegistersAllInRangeTokens:
    def test_single_page_chunk_registers_one_token(self):
        agent = GroundingAgent(llm=MagicMock(), knowledge_base=_kb([_chunk(7, 7)]))
        assert "[t:ch1.s1:p07]" in agent._chunk_by_token
        assert len(agent._chunk_by_token) == 1

    def test_multi_page_chunk_registers_token_per_page(self):
        agent = GroundingAgent(llm=MagicMock(), knowledge_base=_kb([_chunk(3, 5)]))
        # Three pages → three index entries pointing at the same chunk
        assert "[t:ch1.s1:p03]" in agent._chunk_by_token
        assert "[t:ch1.s1:p04]" in agent._chunk_by_token
        assert "[t:ch1.s1:p05]" in agent._chunk_by_token
        # All three point at the same chunk object
        c = agent._chunk_by_token["[t:ch1.s1:p03]"]
        assert agent._chunk_by_token["[t:ch1.s1:p04]"] is c
        assert agent._chunk_by_token["[t:ch1.s1:p05]"] is c

    def test_first_chunk_wins_on_boundary_collision(self):
        # Two chunks that happen to share a page boundary in the same
        # section. First registered wins (rare but possible).
        c1 = _chunk(3, 5, section_id="ch1.s1")
        c2 = _chunk(5, 7, section_id="ch1.s1")
        agent = GroundingAgent(llm=MagicMock(), knowledge_base=_kb([c1, c2]))
        # p5 was first claimed by c1; should not have been overwritten
        assert agent._chunk_by_token["[t:ch1.s1:p05]"] is c1
        # c2's other pages (p6, p7) still registered to c2
        assert agent._chunk_by_token["[t:ch1.s1:p06]"] is c2
        assert agent._chunk_by_token["[t:ch1.s1:p07]"] is c2
