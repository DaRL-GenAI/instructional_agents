"""Tests for v6 Lever Z — guarantee visual chunk inclusion + mandatory
\\includegraphics directive.

v4 delivered 11 \\includegraphics across 14 chapters; v5 delivered 2
across 15 chapters. The deep-mine traced the regression to visual
chunks being crowded out of the retrieval top-k by prose chunks that
ranked higher. Lever Z forces at least one visual chunk into the
evidence block whenever one exists within the bound section_ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


@dataclass
class _StubChunk:
    section_id: str
    text: str
    page_start: int = 1
    page_end: int = 1
    textbook_id: str = "han"
    chapter_title: str = "Ch"
    section_title: str = "Sec"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [self.citation_token()]

    def page_range_label(self) -> str:
        return f"p{self.page_start}"


@dataclass
class _StubResult:
    chunk: _StubChunk


def _make_delib(prose_chunks, all_kb_chunks):
    retriever = MagicMock()
    retriever.search.return_value = [_StubResult(c) for c in prose_chunks]
    retriever.kb = MagicMock(chunks=all_kb_chunks)
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = retriever
    d.section_ids = None
    d.textbook_id = "han"
    d._evidence_top_k = 6
    d.citation_usage_tracker = None
    return d


class TestInjectVisualChunkIfAvailable:
    def test_already_has_visual_chunk_no_change(self):
        prose = [_StubChunk("ch1.s1", text="text with [IMAGE_PATH: /a.png] marker")]
        kb = list(prose)
        d = _make_delib(prose, kb)
        out = d._inject_visual_chunk_if_available(
            [_StubResult(c) for c in prose], None,
        )
        assert len(out) == 1
        # Visual already present; no replacement
        assert "[IMAGE_PATH:" in out[0].chunk.text

    def test_visual_injected_when_none_in_results(self):
        prose = [
            _StubChunk("ch1.s1", text="prose 1"),
            _StubChunk("ch1.s1", text="prose 2"),
            _StubChunk("ch1.s1", text="prose 3"),
        ]
        visual = _StubChunk("ch1.s1", text="caption [IMAGE_PATH: /fig1.png] more")
        kb = prose + [visual]
        d = _make_delib(prose, kb)
        out = d._inject_visual_chunk_if_available(
            [_StubResult(c) for c in prose], None,
        )
        # Visual chunk is hoisted to the FRONT so its IMAGE_PATH marker
        # survives the downstream block-builder's word budget. The lowest-
        # ranked prose chunk is dropped to keep the result count stable.
        assert "[IMAGE_PATH:" in out[0].chunk.text
        # Top two prose preserved (their original ranks 1, 2 stay in
        # positions 1, 2 — only the lowest-ranked got displaced)
        assert out[1].chunk.text == "prose 1"
        assert out[2].chunk.text == "prose 2"

    def test_visual_must_be_in_scope(self):
        prose = [_StubChunk("ch1.s1", text="prose")]
        visual_other_section = _StubChunk("ch99.s99", text="[IMAGE_PATH: /x.png]")
        kb = prose + [visual_other_section]
        d = _make_delib(prose, kb)
        # section_ids restricts to ch1.s1
        out = d._inject_visual_chunk_if_available(
            [_StubResult(c) for c in prose], ["ch1.s1"],
        )
        # Visual in ch99.s99 is OUT of scope → no injection
        assert all("[IMAGE_PATH:" not in r.chunk.text for r in out)

    def test_no_visual_in_kb_no_change(self):
        prose = [_StubChunk("ch1.s1", text="prose 1")]
        kb = list(prose)
        d = _make_delib(prose, kb)
        out = d._inject_visual_chunk_if_available(
            [_StubResult(c) for c in prose], None,
        )
        assert all("[IMAGE_PATH:" not in r.chunk.text for r in out)

    def test_prefers_same_section_as_top_result(self):
        prose = [
            _StubChunk("ch1.s1", text="prose ch1"),
            _StubChunk("ch2.s2", text="prose ch2"),
        ]
        # Two visuals available — one in ch1.s1 (same as top), one elsewhere
        visual_ch1 = _StubChunk("ch1.s1", text="ch1 [IMAGE_PATH: /a.png]")
        visual_ch2 = _StubChunk("ch2.s2", text="ch2 [IMAGE_PATH: /b.png]")
        kb = prose + [visual_ch2, visual_ch1]  # ch2 visual ordered first
        d = _make_delib(prose, kb)
        out = d._inject_visual_chunk_if_available(
            [_StubResult(c) for c in prose], None,
        )
        # Visual chunk is hoisted to the FRONT; should prefer ch1
        # (top-section match) even though ch2 came first in the KB scan.
        assert "/a.png" in out[0].chunk.text

    def test_vanilla_path_no_retriever_no_op(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        out = d._inject_visual_chunk_if_available([], None)
        assert out == []

    def test_empty_results_no_op(self):
        prose = []
        kb = []
        d = _make_delib(prose, kb)
        out = d._inject_visual_chunk_if_available([], None)
        assert out == []
