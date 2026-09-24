"""Offline end-to-end smoke test for textbook grounding.

Ingests the Markdown fixture, builds the hybrid retriever with the
deterministic ``HashEmbedder`` (no network, no API key), binds fake
syllabus chapters to textbook sections via the course contract, and checks
that a ``SlidesDeliberation`` wired with the retriever produces evidence
blocks -- while a vanilla one leaves its prompts untouched.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.grounding import (
    HashEmbedder,
    HybridRetriever,
    TextbookKnowledgeBase,
    build_course_contract,
    sections_for_chapter,
)
from src.slides import SlidesDeliberation

FIXTURE_MD = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mini_textbook.md"


@pytest.fixture(scope="module")
def kb():
    return TextbookKnowledgeBase.from_path(FIXTURE_MD, textbook_id="mini", title="Mini")


@pytest.fixture
def retriever(kb, tmp_path):
    return HybridRetriever(kb, embedder=HashEmbedder(dim=64), cache_dir=tmp_path)


def test_markdown_ingestion_builds_chunks(kb):
    assert kb.textbook.source_format == "markdown"
    assert [c.title for c in kb.textbook.chapters] == ["Chapter 1: Foundations", "Chapter 2: Control Flow"]
    assert len(kb.chunks) >= 3
    toc = kb.toc()
    assert "Chapter 1: Foundations" in toc and "Operators" in toc


def test_retrieval_is_offline_and_topical(retriever, tmp_path):
    hits = retriever.search("plus operator adds numbers", top_k=3)
    assert hits, "expected at least one hit"
    assert "plus operator" in hits[0].chunk.text.lower()
    # Embedding cache written next to the run, not in the repo.
    assert list(tmp_path.glob("*.npz"))
    assert not (Path(__file__).resolve().parents[1] / ".grounding_cache").exists()


def test_contract_binds_chapters_to_sections(kb, retriever):
    chapters = [
        {"title": "Week 1: Numbers and operators", "description": "integers, floats, the plus operator"},
        {"title": "Week 2: Conditionals", "description": "if statements branch on conditions"},
    ]
    contract = build_course_contract(
        course_id="smoke", chapters=chapters, kb=kb, retriever=retriever, llm=None,
    )
    assert len(contract.topic_to_textbook) == 2
    bound = sections_for_chapter(contract, 1)
    # The conditionals chapter must resolve to a chapter-2 section (or be
    # left unbound = whole-book retrieval) -- never to a chapter-1 section only.
    assert bound is None or any(s.startswith("ch2") for s in bound)


def _deliberation(retriever=None, section_ids=None):
    d = SlidesDeliberation(
        id="t", name="T", agents={}, llm=MagicMock(), output_dir="/nonexistent",
        retriever=retriever, section_ids=section_ids, textbook_id="mini" if retriever else None,
    )
    d.slides_outline = [{"slide_id": 1, "title": "Operators", "description": "the plus operator"}]
    return d


def test_grounded_deliberation_emits_evidence(retriever):
    d = _deliberation(retriever)
    flat, rules = d._build_evidence_block("plus operator adds numbers")
    assert rules == ""
    assert "MANDATORY RULES" in flat and "EXCERPT 1 of" in flat
    assert "plus operator" in flat.lower()
    assert len(flat.split()) < d._EVIDENCE_WORD_BUDGET + 400
    grouped, _ = d._build_grouped_evidence_block(d.slides_outline)
    assert "EVIDENCE FOR SLIDE: Operators" in grouped
    per_slide, _ = d._build_per_slide_evidence("plus operator", artifact="script")
    assert "SPOKEN SCRIPT" in per_slide
    # The prepend helper only changes a prompt when there is evidence.
    assert d._with_evidence(flat, "PROMPT").endswith("\nPROMPT")


def test_vanilla_deliberation_is_a_no_op():
    d = _deliberation()
    assert d.retriever is None and d.section_ids is None and d.textbook_id is None
    assert d._build_evidence_block("anything") == ("", "")
    assert d._build_grouped_evidence_block(d.slides_outline) == ("", "")
    assert d._build_per_slide_evidence("anything") == ("", "")
    prompt = "vanilla prompt"
    assert d._with_evidence("", prompt) is prompt
