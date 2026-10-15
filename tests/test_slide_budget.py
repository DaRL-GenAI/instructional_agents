"""Tests for content-scaled slide budget.

The per-chapter slide count was a flat catalog value (slides_length // 3) shared
by every chapter, so a content-rich chapter (clustering, ~12 bound sections) got
the same budget as a thin one (Intro, ~3) — the "flat ~50 slides regardless of
content" gap found across the whole course. The budget now scales with how many
textbook sections are bound, clamped so per-chapter cost stays bounded. Grounded
path only; vanilla keeps the configured count.
"""

from __future__ import annotations

from src.slides import (
    _scaled_slide_budget,
    _BUDGET_REFERENCE_SECTIONS,
    _BUDGET_MIN_SCALE,
    _BUDGET_MAX_SCALE,
)


class TestScaledSlideBudget:
    def test_reference_chapter_keeps_base(self):
        # a chapter binding ~reference sections keeps ~the configured budget
        assert _scaled_slide_budget(50, _BUDGET_REFERENCE_SECTIONS) == 50

    def test_rich_chapter_scales_up_then_clamps(self):
        assert _scaled_slide_budget(50, 12) > 50                       # richer -> more
        assert _scaled_slide_budget(50, 40) == round(_BUDGET_MAX_SCALE * 50)  # clamped

    def test_thin_chapter_scales_down_then_clamps(self):
        assert _scaled_slide_budget(50, 4) < 50                        # thinner -> fewer
        assert _scaled_slide_budget(50, 1) == round(_BUDGET_MIN_SCALE * 50)   # clamped

    def test_zero_sections_falls_back_to_base(self):
        assert _scaled_slide_budget(50, 0) == 50

    def test_non_decreasing_in_section_count(self):
        vals = [_scaled_slide_budget(50, n) for n in range(1, 25)]
        assert vals == sorted(vals)

    def test_stays_within_clamp_band(self):
        for n in range(0, 30):
            v = _scaled_slide_budget(50, n)
            assert round(_BUDGET_MIN_SCALE * 50) <= v <= round(_BUDGET_MAX_SCALE * 50) or v == 50
