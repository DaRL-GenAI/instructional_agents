"""Tests for scale-invariant contract binding.

The fused RRF score is normalized by the max attainable (n_queries / K) so the
abstain floors don't drift with the per-chapter query count (a transfer hazard).
Coverage widening then binds the full on-topic plateau (sections within the
relative-score floor of the top) up to MAX_SECTIONS_PER_TOPIC, instead of a
fixed cap that truncated broad chapters to a third of themselves.
"""

from __future__ import annotations

from src.grounding.contract import (
    _normalized_top,
    _count_sections_above_floor,
    _is_filler_section,
    _section_chapter_num,
    _chapter_coherence_filter,
    NORM_COVERAGE_FLOOR,
    MAX_SECTIONS_PER_TOPIC,
    QUERY_FUSION_RRF_K,
    SECTIONS_PER_TOPIC,
)


class TestFillerSection:
    def test_detects_boilerplate_with_numbers_and_markup(self):
        assert _is_filler_section("10.7 **[Summary]**")
        assert _is_filler_section("10.9 **[Bibliographic Notes]**")
        assert _is_filler_section("10.8 **[Exercises]**")
        assert _is_filler_section("References")
        assert _is_filler_section("Index")

    def test_keeps_real_method_sections(self):
        assert not _is_filler_section("10.1 **[Cluster Analysis]**")
        assert not _is_filler_section("10.2 Partitioning Methods")
        assert not _is_filler_section("10.4 Density-Based Methods")
        assert not _is_filler_section("DBSCAN")


class TestNormalizedTop:
    def test_rank0_by_all_queries_is_one(self):
        # n queries each ranking the section #1: raw = n/K, normalized = 1.0
        for n in (1, 3, 6, 10):
            assert abs(_normalized_top(n / QUERY_FUSION_RRF_K, n) - 1.0) < 1e-9

    def test_floor_preserves_legacy_threshold_at_six_queries(self):
        # the legacy raw coverage floor (0.012) maps exactly to the normalized
        # floor at the reference query count, so default-config behavior is kept
        assert abs(_normalized_top(0.012, 6) - NORM_COVERAGE_FLOOR) < 1e-6

    def test_single_hit_normalizes_to_inverse_query_count(self):
        # one rank-0 hit = 1/K raw; normalized = its share of the max = 1/n
        assert abs(_normalized_top(1.0 / QUERY_FUSION_RRF_K, 4) - 0.25) < 1e-9
        assert abs(_normalized_top(1.0 / QUERY_FUSION_RRF_K, 10) - 0.10) < 1e-9

    def test_zero_query_guard(self):
        # never divides by zero
        assert _normalized_top(0.05, 0) == _normalized_top(0.05, 1)


class TestCountSectionsAboveFloor:
    def test_counts_the_on_topic_plateau(self):
        ranked = [("a", 1.0), ("b", 0.5), ("c", 0.2), ("d", 0.05)]  # floor = 0.1
        assert _count_sections_above_floor(ranked, 0.10) == 3       # d (0.05) below

    def test_broad_flat_distribution_counts_all(self):
        ranked = [("s%d" % i, 1.0 - 0.01 * i) for i in range(14)]   # all within 13%
        n = _count_sections_above_floor(ranked, 0.10)
        assert n == 14                                              # a comprehensive chapter
        # such a chapter would widen up to the cap, well beyond the default
        assert min(MAX_SECTIONS_PER_TOPIC, n) > SECTIONS_PER_TOPIC

    def test_empty(self):
        assert _count_sections_above_floor([], 0.10) == 0


class TestCoverageCap:
    def test_cap_exceeds_default(self):
        # the raised cap must allow a broad chapter to bind beyond the default
        assert MAX_SECTIONS_PER_TOPIC > SECTIONS_PER_TOPIC


class TestChapterCoherence:
    def test_parses_chapter_number_from_title(self):
        assert _section_chapter_num("10.3 **[Hierarchical Methods]**") == 10
        assert _section_chapter_num("3.4 **[Data Reduction]**") == 3
        assert _section_chapter_num("DBSCAN") is None
        assert _section_chapter_num("Chapter 8") is None  # not the N.M form

    def test_drops_distant_chapters_keeps_dominant_plusminus_one(self):
        title = {
            "a": "10.1 Cluster Analysis", "b": "10.2 Partitioning",
            "c": "10.3 Hierarchical", "d": "11.2 High-Dim Clustering",
            "e": "3.4 Data Reduction", "f": "2.4 Similarity",
        }
        ranked = [("a", 1.0), ("b", 0.8), ("c", 0.7), ("d", 0.5), ("e", 0.4), ("f", 0.3)]
        kept = {sid for sid, _ in _chapter_coherence_filter(ranked, title)}
        assert {"a", "b", "c", "d"} <= kept            # ch10 + adjacent ch11 kept
        assert "e" not in kept and "f" not in kept     # ch3, ch2 dropped (far)

    def test_noop_when_unnumbered(self):
        title = {"a": "DBSCAN", "b": "K-Means", "c": "OPTICS"}
        ranked = [("a", 1.0), ("b", 0.8), ("c", 0.6)]
        assert _chapter_coherence_filter(ranked, title) == ranked


class TestMedian:
    """The book-relative abstain floors key off the median top_norm."""

    def test_median(self):
        from src.grounding.contract import _median
        assert _median([]) == 0.0
        assert _median([0.5]) == 0.5
        assert _median([0.2, 0.4, 0.6]) == 0.4
        assert _median([0.2, 0.4, 0.6, 0.8]) == 0.5

    def test_relative_floors_match_legacy_at_typical_median(self):
        # On the eval books median top_norm ~0.5 → relative floors ≈ the legacy
        # fixed floors, so behavior is preserved there.
        from src.grounding.contract import (
            REL_COVERAGE_FRACTION, REL_META_FRACTION,
            NORM_COVERAGE_FLOOR_MIN, NORM_META_ABSTAIN_MIN,
        )
        ref = 0.5
        cov = max(NORM_COVERAGE_FLOOR_MIN, REL_COVERAGE_FRACTION * ref)
        meta = max(NORM_META_ABSTAIN_MIN, REL_META_FRACTION * ref)
        assert abs(cov - 0.125) < 1e-9   # ≈ legacy 0.12
        assert abs(meta - 0.25) < 1e-9   # == legacy 0.25
