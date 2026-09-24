"""Tests for the heading-collapse diagnostic (external-review Risk 2).

When a PDF lacks the headings the segmenter recognizes, every chapter collapses
to a single section and grounding silently drops to chapter granularity. The
detector surfaces that (a warning) instead of letting it pass as an invisible
quality drop. It does NOT change behavior — the pipeline still works (the
chunker sentence-splits within the coarse section; the slide writer's global
evidence dedup already prevents the cross-slide redundancy the review feared).
"""

from __future__ import annotations

from src.grounding.knowledge_base import _heading_collapse_warning


class _Ch:
    def __init__(self, n_sections):
        self.sections = list(range(n_sections))  # only len() matters here


class _TB:
    def __init__(self, *section_counts):
        self.chapters = [_Ch(n) for n in section_counts]


class TestHeadingCollapseWarning:
    def test_fires_when_all_chapters_have_one_section(self):
        tb = _TB(1, 1, 1, 1, 1)               # 5 chapters, all flat
        w = _heading_collapse_warning(tb)
        assert w is not None and "5/5 chapters" in w

    def test_silent_on_a_well_structured_book(self):
        tb = _TB(4, 6, 3, 5, 7)               # real sub-sections everywhere
        assert _heading_collapse_warning(tb) is None

    def test_silent_when_too_few_chapters_to_judge(self):
        # 2 chapters is too small a sample to call it a collapse.
        assert _heading_collapse_warning(_TB(1, 1)) is None

    def test_fires_at_eighty_percent_flat(self):
        tb = _TB(1, 1, 1, 1, 3)               # 4/5 flat → still a collapse
        w = _heading_collapse_warning(tb)
        assert w is not None and "4/5 chapters" in w

    def test_silent_below_threshold(self):
        tb = _TB(1, 1, 3, 4, 5)               # only 2/5 flat → structured enough
        assert _heading_collapse_warning(tb) is None

    def test_no_chapters_is_silent(self):
        assert _heading_collapse_warning(_TB()) is None
