"""Tests for deterministic navigation-frame insertion.

The outline-prompt request for Learning Objectives / Key Takeaways slides was
unreliable (the model ignored it). These are now inserted deterministically from
the deck's own topic titles: an objectives agenda after the opener and a
takeaways recap at the end.
"""

from __future__ import annotations

from src.slides import _insert_navigation_frames


def _deck(*titles):
    body = "\\begin{document}\n"
    for t in titles:
        body += f"\\begin{{frame}}\n\\frametitle{{{t}}}\nbody text\n\\end{{frame}}\n"
    body += "\\end{document}\n"
    return body


class TestNavigationFrames:
    def test_inserts_objectives_and_takeaways(self):
        out = _insert_navigation_frames(_deck("Intro", "K-Means", "DBSCAN", "Evaluation"))
        assert "\\frametitle{Learning Objectives}" in out
        assert "\\frametitle{Key Takeaways}" in out
        assert out.count("\\begin{frame}") == 4 + 2          # two nav frames added

    def test_objectives_early_takeaways_at_end(self):
        out = _insert_navigation_frames(_deck("Intro", "K-Means", "DBSCAN"))
        assert out.index("Learning Objectives") < out.index("K-Means")
        assert out.index("DBSCAN") < out.index("Key Takeaways") < out.index("\\end{document}")

    def test_topics_come_from_content_not_opener(self):
        out = _insert_navigation_frames(_deck("Intro Slide", "K-Means", "DBSCAN"))
        obj_start = out.index("Learning Objectives")
        obj = out[obj_start:out.index("\\end{frame}", obj_start)]
        assert "K-Means" in obj and "DBSCAN" in obj
        assert "Intro Slide" not in obj                       # opener excluded

    def test_noop_without_frames(self):
        assert _insert_navigation_frames("just prose") == "just prose"
        assert _insert_navigation_frames("") == ""
