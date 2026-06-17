"""Tests for deck-level figure dedup.

The figure matcher can pick the same image for several slides, so a single
diagram ended up on 3 slides with 3 different invented captions. Dedup keeps
each image's first placement and strips later \\includegraphics blocks (image +
caption together, so no orphan caption is left behind).
"""

from __future__ import annotations

from src.slides import _dedupe_repeated_figures


class TestDedupeRepeatedFigures:
    def test_keeps_first_strips_later_with_caption(self):
        tex = (
            "\\begin{frame}\\frametitle{A}\n"
            "\\includegraphics[width=0.5\\textwidth]{/x/fig1.png}\n"
            "\\caption{first caption}\n"
            "\\end{frame}\n"
            "\\begin{frame}\\frametitle{B}\n"
            "\\includegraphics[width=0.5\\textwidth]{/x/fig1.png}\n"
            "\\caption{second invented caption}\n"
            "\\end{frame}\n"
        )
        out = _dedupe_repeated_figures(tex)
        assert out.count("includegraphics") == 1          # only the first kept
        assert "first caption" in out                      # its caption kept
        assert "second invented caption" not in out        # duplicate caption gone (no orphan)

    def test_keeps_distinct_figures(self):
        tex = (
            "\\includegraphics{/x/a.png}\n\\caption{a}\n"
            "\\includegraphics{/x/b.png}\n\\caption{b}\n"
        )
        out = _dedupe_repeated_figures(tex)
        assert out.count("includegraphics") == 2           # both distinct figures kept

    def test_dedupes_by_basename_not_full_path(self):
        # same image referenced two different ways -> still deduped
        tex = (
            "\\includegraphics{/a/fig.png}\n"
            "\\includegraphics{/b/fig.png}\n"
        )
        assert _dedupe_repeated_figures(tex).count("includegraphics") == 1

    def test_noop_without_figures(self):
        assert _dedupe_repeated_figures("just prose, no figures") == "just prose, no figures"
        assert _dedupe_repeated_figures("") == ""
