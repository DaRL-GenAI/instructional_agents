"""Tests for per-chapter top_k tuning.

Dense chapters (many candidate chunks in the bound sections) get a
wider retrieval window so the LLM sees more options; thin chapters
narrow down to avoid pulling tangential content into evidence.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


def _make_deliberation(*, retriever=None, section_ids=None) -> SlidesDeliberation:
    """Build a SlidesDeliberation skeleton sufficient for the top_k
    computation, bypassing the heavy initializer."""
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = retriever
    d.section_ids = section_ids
    d.textbook_id = None
    return d


def _kb(chunks_per_section):
    """Build a KB with given count per section_id."""
    chunks = []
    for sid, n in chunks_per_section.items():
        for _ in range(n):
            chunks.append(SimpleNamespace(section_id=sid))
    return SimpleNamespace(chunks=chunks)


class TestComputeTopKForChapter:
    def test_no_retriever_returns_default(self):
        d = _make_deliberation(retriever=None, section_ids=None)
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K

    def test_no_section_ids_returns_default(self):
        retriever = SimpleNamespace(kb=_kb({"ch1.s1": 50}))
        d = _make_deliberation(retriever=retriever, section_ids=None)
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K

    def test_thin_chapter_clamped_to_min(self):
        retriever = SimpleNamespace(kb=_kb({"ch1.s1": 5}))  # well below floor
        d = _make_deliberation(retriever=retriever, section_ids={"ch1.s1"})
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K_MIN

    def test_medium_density_scales(self):
        # 60 chunks → round(60 / 12) = 5; but our floor is 5 so the
        # scaling kicks in at slightly higher density. Pick 80 chunks
        # → round(80 / 12) = 7 (in the scaled middle).
        retriever = SimpleNamespace(kb=_kb({"ch1.s1": 80}))
        d = _make_deliberation(retriever=retriever, section_ids={"ch1.s1"})
        result = d._compute_top_k_for_chapter()
        assert SlidesDeliberation._EVIDENCE_TOP_K_MIN < result < SlidesDeliberation._EVIDENCE_TOP_K_MAX

    def test_dense_chapter_clamped_to_max(self):
        retriever = SimpleNamespace(kb=_kb({"ch1.s1": 500}))
        d = _make_deliberation(retriever=retriever, section_ids={"ch1.s1"})
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K_MAX

    def test_counts_across_multiple_sections(self):
        retriever = SimpleNamespace(
            kb=_kb({"ch1.s1": 40, "ch1.s2": 60, "ch1.s3": 20})
        )
        # All three sections bound → 120 total chunks → round(120/12)=10
        d = _make_deliberation(
            retriever=retriever,
            section_ids={"ch1.s1", "ch1.s2", "ch1.s3"},
        )
        assert d._compute_top_k_for_chapter() == 10

    def test_unrelated_sections_dont_inflate_count(self):
        # Bound to ch1.s1 only; chunks in ch1.s2 should not contribute
        retriever = SimpleNamespace(
            kb=_kb({"ch1.s1": 50, "ch1.s2": 200})
        )
        d = _make_deliberation(retriever=retriever, section_ids={"ch1.s1"})
        # 50 chunks → round(50/12) = 4 → clamped to MIN (5)
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K_MIN

    def test_zero_bound_chunks_returns_default(self):
        # section_ids set but no chunks match → fall back to default
        retriever = SimpleNamespace(kb=_kb({"other.s1": 50}))
        d = _make_deliberation(retriever=retriever, section_ids={"ch1.s1"})
        assert d._compute_top_k_for_chapter() == SlidesDeliberation._EVIDENCE_TOP_K
