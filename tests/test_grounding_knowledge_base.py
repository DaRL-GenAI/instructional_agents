"""Tests for the textbook knowledge base.

Exercises the chunking layer end-to-end on the labeled mini PDF fixture
and a hand-built synthetic Textbook. No LLM calls; no real-world PDFs
required.
"""

from pathlib import Path

import pytest

from src.grounding import Chunk, TextbookKnowledgeBase
from src.grounding.knowledge_base import (
    OVERLAP_TOKENS,
    TARGET_TOKENS,
    _derive_id,
    _derive_title,
    _paragraph_chunks,
    _word_count,
)
from src.textbook.schema import Chapter, PageSpan, Paragraph, Section

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"


def _para(idx: int, words: int, page: int = 1, kind: str = "prose") -> Paragraph:
    return Paragraph(
        para_id=f"ch1.s1.p{idx:02d}",
        text=" ".join(["word"] * words),
        page=page,
        kind=kind,
    )


def _section(paras: list[Paragraph]) -> Section:
    pages = [p.page for p in paras] or [1]
    return Section(
        section_id="ch1.s1",
        title="A Section",
        pages=PageSpan(start=min(pages), end=max(pages)),
        paragraphs=paras,
        concepts=[],
    )


def _chapter(section: Section) -> Chapter:
    return Chapter(
        chapter_id="ch1",
        number=1,
        title="Chapter 1",
        pages=section.pages,
        sections=[section],
        learning_objectives=[],
    )


class TestChunkerHelpers:
    """Unit tests on the synthetic builder."""

    def test_word_count_is_split_based(self):
        assert _word_count("one two three") == 3
        assert _word_count("") == 0

    def test_small_section_collapses_to_one_chunk(self):
        # Total ~120 words << TARGET_TOKENS — one chunk emitted.
        sec = _section([_para(0, 60), _para(1, 60)])
        chs = list(_paragraph_chunks(sec, _chapter(sec), "tb"))
        assert len(chs) == 1
        assert chs[0].para_ids == ["ch1.s1.p00", "ch1.s1.p01"]

    def test_packs_up_to_target_then_breaks(self):
        # Four paragraphs of ~200 words each → 800 words → should split.
        sec = _section([_para(i, 200) for i in range(4)])
        chs = list(_paragraph_chunks(sec, _chapter(sec), "tb"))
        assert len(chs) >= 2
        # Each chunk respects the target (allowing the first paragraph to
        # exceed it, since we always pack at least one).
        for ch in chs[:-1]:
            assert ch.token_count() <= TARGET_TOKENS + 200  # +1 paragraph slack

    def test_overlap_between_adjacent_chunks(self):
        # Build a section where each chunk should carry the trailing
        # paragraph from the previous one (overlap).
        sec = _section([_para(i, 200) for i in range(4)])
        chs = list(_paragraph_chunks(sec, _chapter(sec), "tb"))
        assert len(chs) >= 2
        first_tail = set(chs[0].para_ids[-1:])
        second_head = set(chs[1].para_ids[:1])
        assert first_tail & second_head, "expected at least 1 paragraph of overlap"

    def test_short_section_still_emits_a_chunk(self):
        # Even a one-sentence section yields a chunk — filtering by chunk
        # size is a retrieval concern, not a chunking one.
        sec = _section([_para(0, 8)])
        chs = list(_paragraph_chunks(sec, _chapter(sec), "tb"))
        assert len(chs) == 1
        assert chs[0].token_count() == 8

    def test_pages_track_min_and_max(self):
        sec = _section([_para(0, 60, page=4), _para(1, 60, page=7)])
        chs = list(_paragraph_chunks(sec, _chapter(sec), "tb"))
        assert chs[0].page_start == 4
        assert chs[0].page_end == 7


class TestCitationToken:
    """The citation marker must be stable, compact, and informative."""

    def test_format(self):
        ch = Chunk(
            chunk_id="han:ch1.s2:c00",
            text="x",
            textbook_id="han",
            chapter_id="ch1",
            chapter_title="t",
            section_id="ch1.s2",
            section_title="t",
            para_ids=["ch1.s2.p00"],
            page_start=42,
            page_end=43,
        )
        assert ch.citation_token() == "[han:ch1.s2:p42]"


class TestDeriveIds:
    def test_id_from_pdf_file(self):
        assert _derive_id(Path("Han_Data_Mining_3e.pdf")) == "han_data_mining_3e"

    def test_id_from_directory(self):
        assert _derive_id(Path("/tmp/agentic_design_patterns")) == "agentic_design_patterns"

    def test_title_is_humanised(self):
        assert _derive_title(Path("Han_Data_Mining_3e.pdf")) == "Han Data Mining 3E"


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf fixture missing")
class TestKnowledgeBaseFromFixture:
    """Layer 1 — load the labeled fixture through the KB front door."""

    def _kb(self) -> TextbookKnowledgeBase:
        return TextbookKnowledgeBase.from_path(
            FIXTURE, textbook_id="mini", title="Mini"
        )

    def test_chapters_loaded(self):
        kb = self._kb()
        assert len(kb.textbook.chapters) == 2

    def test_some_chunks_produced(self):
        kb = self._kb()
        assert len(kb) >= 1  # tiny fixture → at least one chunk
        assert all(isinstance(c, Chunk) for c in kb.chunks)

    def test_every_chunk_has_real_pages(self):
        kb = self._kb()
        for c in kb.chunks:
            assert c.page_start >= 1
            assert c.page_end >= c.page_start

    def test_chunk_ids_unique(self):
        kb = self._kb()
        ids = [c.chunk_id for c in kb.chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_carry_textbook_id(self):
        kb = self._kb()
        assert all(c.chunk_id.startswith("mini:") for c in kb.chunks)


class TestUnsupportedPaths:
    def test_missing_path_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            TextbookKnowledgeBase.from_path(tmp_path / "does_not_exist.pdf")

    def test_unsupported_extension_raises(self, tmp_path: Path):
        weird = tmp_path / "thing.docx"
        weird.write_text("nope")
        with pytest.raises(ValueError, match="unsupported"):
            TextbookKnowledgeBase.from_path(weird)

    def test_empty_directory_raises(self, tmp_path: Path):
        with pytest.raises(ValueError, match="no .pdf or .md files"):
            TextbookKnowledgeBase.from_path(tmp_path)

    def test_mixed_directory_raises(self, tmp_path: Path):
        (tmp_path / "a.pdf").write_bytes(b"x")
        (tmp_path / "b.md").write_text("x")
        with pytest.raises(ValueError, match="mixed sources"):
            TextbookKnowledgeBase.from_path(tmp_path)
