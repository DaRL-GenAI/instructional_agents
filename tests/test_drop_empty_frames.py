"""Tests for _drop_empty_frames — removes blank figure-dedicated slides.

The writer sometimes emits a figure-only frame ("Diagram: ...",
"Illustration of ...") that never receives a figure, leaving a frame with
just a frametitle and no body — it ships as a blank slide. This pass drops
such frames; it keeps any frame with a figure or visible text, and is a
no-op when nothing is empty.
"""

from __future__ import annotations

from src.slides import _drop_empty_frames


def _frame(title, body=""):
    return (
        f"\\begin{{frame}}[fragile]\n\\frametitle{{{title}}}\n{body}\\end{{frame}}\n"
    )


class TestDropEmptyFrames:
    def test_drops_frame_with_no_body(self):
        deck = _frame("Real slide", "Some real content here.\n") + _frame(
            "Diagram: Hierarchy of Ordinal Attributes", ""
        )
        out = _drop_empty_frames(deck)
        assert "Real slide" in out
        assert "Diagram: Hierarchy of Ordinal Attributes" not in out

    def test_keeps_frame_with_text(self):
        deck = _frame(
            "Topic", "\\begin{itemize}\n\\item A real bullet point.\n\\end{itemize}\n"
        )
        out = _drop_empty_frames(deck)
        assert "Topic" in out
        assert "real bullet point" in out

    def test_keeps_frame_with_figure(self):
        deck = _frame(
            "Figure slide", "\\includegraphics[width=0.6\\linewidth]{/x/fig.png}\n"
        )
        out = _drop_empty_frames(deck)
        assert "Figure slide" in out
        assert "includegraphics" in out

    def test_drops_empty_itemize_frame(self):
        deck = _frame("Keep", "Body text.\n") + _frame(
            "Empty list", "\\begin{itemize}\n\\end{itemize}\n"
        )
        out = _drop_empty_frames(deck)
        assert "Keep" in out
        assert "Empty list" not in out

    def test_keeps_frame_with_only_bold_text(self):
        # \textbf{...}'s argument is real content, not a stripped command.
        deck = _frame("Bold", "\\textbf{This is the whole point.}\n")
        out = _drop_empty_frames(deck)
        assert "Bold" in out

    def test_noop_without_frames(self):
        assert _drop_empty_frames("just text") == "just text"
        assert _drop_empty_frames("") == ""

    def test_noop_when_all_frames_have_content(self):
        # Byte-for-byte unchanged when there is nothing to drop.
        deck = _frame("A", "Alpha content.\n") + _frame("B", "Beta content.\n")
        assert _drop_empty_frames(deck) == deck
