"""Tests for the bound-section SOURCE STRUCTURE block.

The writer's evidence blocks end with a title list of the bound
sections so generated material is organized around the source's own
skeleton instead of structure invented from memory. Vanilla (no
retriever) and unbound chapters are no-ops.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


def _kb_with_sections(sections):
    sec_objs = [SimpleNamespace(section_id=sid, title=title)
                for sid, title in sections]
    chapter = SimpleNamespace(sections=sec_objs)
    return SimpleNamespace(textbook=SimpleNamespace(chapters=[chapter]))


def _chunk(cid, text, sid="ch1.s1"):
    c = MagicMock()
    c.text = text
    c.section_id = sid
    c.chunk_id = cid
    c.chapter_title = "Ch1"
    c.section_title = "Sec"
    c.kinds = {"prose"}
    c.page_start = 1
    c.page_range_label = lambda: "p1"
    r = MagicMock()
    r.chunk = c
    return r


def _delib(section_ids, sections, search_fn=None):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    retr = MagicMock()
    retr.kb = _kb_with_sections(sections)
    if search_fn is not None:
        retr.search.side_effect = search_fn
    d.retriever = retr
    d.section_ids = section_ids
    d._build_visual_content_rules = lambda *a, **k: ""
    return d


class TestBoundStructureBlock:
    def test_lists_only_bound_section_titles(self):
        d = _delib(
            ["ch1.s1", "ch1.s3"],
            [("ch1.s1", "2.1 Data Objects and Attribute Types"),
             ("ch1.s2", "2.2 Basic Statistical Descriptions"),
             ("ch1.s3", "2.3 Data Visualization")],
        )
        block = d._bound_structure_block()
        assert "SOURCE STRUCTURE" in block
        assert "- 2.1 Data Objects and Attribute Types" in block
        assert "- 2.3 Data Visualization" in block
        assert "2.2 Basic Statistical Descriptions" not in block

    def test_vanilla_no_retriever_is_empty(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        d.section_ids = ["ch1.s1"]
        assert d._bound_structure_block() == ""

    def test_unbound_is_empty(self):
        d = _delib([], [("ch1.s1", "2.1 Title")])
        assert d._bound_structure_block() == ""

    def test_no_matching_sections_is_empty(self):
        d = _delib(["ch9.s9"], [("ch1.s1", "2.1 Title")])
        assert d._bound_structure_block() == ""

    def test_malformed_kb_fails_open_empty(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        retr = MagicMock()
        retr.kb = SimpleNamespace(textbook=SimpleNamespace())
        d.retriever = retr
        d.section_ids = ["ch1.s1"]
        assert d._bound_structure_block() == ""


class TestStructureAppendedToEvidence:
    def test_grouped_block_ends_with_structure(self):
        def search(q, top_k=3, section_ids=None):
            return [_chunk("c1", "K-means partitions points into k clusters.")]

        d = _delib(["ch1.s1"], [("ch1.s1", "10.2 Partitioning Methods")],
                   search_fn=search)
        d._EVIDENCE_WORD_BUDGET = 400
        block, _ = d._build_grouped_evidence_block(
            [{"title": "K-Means", "description": "x"}])
        assert "EVIDENCE FOR SLIDE: K-Means" in block
        assert "SOURCE STRUCTURE" in block
        assert "- 10.2 Partitioning Methods" in block
        assert block.index("SOURCE STRUCTURE") > block.index("EVIDENCE FOR SLIDE")

    def test_grouped_block_vanilla_still_empty(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        d.section_ids = ["ch1.s1"]
        block, _ = d._build_grouped_evidence_block(
            [{"title": "K-Means", "description": "x"}])
        assert block == ""
