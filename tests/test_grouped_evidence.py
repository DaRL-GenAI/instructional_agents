"""Tests for the grouped (per-outline-slide) evidence block.

Instead of one chapter-wide dump, the writer's initial-LaTeX evidence is
retrieved per slide-topic and grouped under per-slide labels, deduped globally
so no chunk repeats. Vanilla (no retriever) and empty-outline are no-ops.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


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


def _delib(search_fn):
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    retr = MagicMock()
    retr.search.side_effect = search_fn
    d.retriever = retr
    d.section_ids = ["ch1.s1"]
    d._EVIDENCE_WORD_BUDGET = 400
    d._build_visual_content_rules = lambda *a, **k: ""
    return d


class TestGroupedEvidence:
    def test_groups_by_slide_with_labels(self):
        def search(q, top_k=3, section_ids=None):
            if "K-Means" in q:
                return [_chunk("c1", "K-means partitions points into k clusters.")]
            if "DBSCAN" in q:
                return [_chunk("c2", "DBSCAN finds dense regions of arbitrary shape.")]
            return []
        d = _delib(search)
        block, _ = d._build_grouped_evidence_block(
            [{"title": "K-Means", "description": "x"},
             {"title": "DBSCAN", "description": "y"}]
        )
        assert "EVIDENCE FOR SLIDE: K-Means" in block
        assert "EVIDENCE FOR SLIDE: DBSCAN" in block
        assert "k-means partitions" in block.lower()
        assert "dense regions" in block.lower()
        assert "MANDATORY RULES" in block  # shared rule header

    def test_dedupes_chunk_across_slides(self):
        shared = _chunk("shared", "Shared evidence chunk about clustering basics.")
        d = _delib(lambda q, top_k=3, section_ids=None: [shared])
        block, _ = d._build_grouped_evidence_block(
            [{"title": "A", "description": "x"}, {"title": "B", "description": "y"}]
        )
        assert block.count("Shared evidence chunk") == 1

    def test_vanilla_no_retriever_is_empty(self):
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = None
        assert d._build_grouped_evidence_block([{"title": "X"}]) == ("", "")

    def test_empty_or_missing_outline_is_empty(self):
        d = _delib(lambda *a, **k: [])
        assert d._build_grouped_evidence_block(None) == ("", "")
        assert d._build_grouped_evidence_block([]) == ("", "")
