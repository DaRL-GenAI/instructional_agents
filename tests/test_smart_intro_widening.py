"""Tests for v6 Lever C — smart intro chapter widening.

Covers the two trigger paths (keyword + dominance) and confirms that
non-intro chapters with healthy bindings keep the Lever B default
sections_per_topic value.
"""

from __future__ import annotations

from src.grounding.contract import (
    SECTIONS_PER_TOPIC,
    SMART_INTRO_SECTIONS_PER_TOPIC,
    _is_dominant_binding,
    _is_generic_intro_chapter,
)


class TestGenericKeywordTrigger:
    def test_introduction_to_x(self):
        assert _is_generic_intro_chapter(
            "Week 1: Introduction to Data Mining",
            "Course overview and motivation",
        )

    def test_intro_to_short_form(self):
        assert _is_generic_intro_chapter("Intro to Statistics", "")

    def test_overview_of_x(self):
        assert _is_generic_intro_chapter("Overview of Methods", "")

    def test_basics_in_title(self):
        assert _is_generic_intro_chapter("Classification Basics", "")

    def test_fundamentals_in_title(self):
        assert _is_generic_intro_chapter("Fundamentals of ML", "")

    def test_project_work_chapter(self):
        # Final / project chapters tend to lack textbook anchor too
        assert _is_generic_intro_chapter("Project Work and Presentations", "")

    def test_review_chapter(self):
        assert _is_generic_intro_chapter("Review Session", "")

    def test_survey_chapter(self):
        assert _is_generic_intro_chapter("Survey of Approaches", "")

    def test_specific_topic_chapter_not_triggered(self):
        assert not _is_generic_intro_chapter("Decision Trees and Bayesian Methods", "")

    def test_clustering_methods_not_triggered(self):
        assert not _is_generic_intro_chapter("Clustering Methods", "")

    def test_case_insensitive(self):
        assert _is_generic_intro_chapter("INTRODUCTION TO X", "")
        assert _is_generic_intro_chapter("introduction to x", "")

    def test_description_match(self):
        # Title doesn't trigger, description does
        assert _is_generic_intro_chapter(
            "Week 5: Foundational Material",
            "Provides an introduction to advanced techniques",
        )


class TestDominantBindingTrigger:
    def test_dominant_binding_flagged(self):
        # top section dominates next by ratio
        ranked = [("ch3.s4", 0.10), ("ch1.s2", 0.02), ("ch6.s2", 0.01)]
        assert _is_dominant_binding(ranked)

    def test_balanced_binding_not_flagged(self):
        # top section is only slightly ahead of next
        ranked = [("ch3.s4", 0.06), ("ch1.s2", 0.05), ("ch6.s2", 0.04)]
        assert not _is_dominant_binding(ranked)

    def test_single_section_treated_as_dominant(self):
        # Only one section above coverage floor → dominant
        ranked = [("ch3.s4", 0.05), ("ch1.s2", 0.0)]
        assert _is_dominant_binding(ranked)

    def test_empty_or_singleton_not_dominant(self):
        assert not _is_dominant_binding([])
        assert not _is_dominant_binding([("ch1.s1", 0.05)])


class TestWideningConstants:
    def test_smart_intro_widens_beyond_lever_b_default(self):
        # The whole point: smart intro must be > the standard top-N
        assert SMART_INTRO_SECTIONS_PER_TOPIC > SECTIONS_PER_TOPIC

    def test_default_widened_value(self):
        # Lock in the v6 value
        assert SMART_INTRO_SECTIONS_PER_TOPIC == 10
