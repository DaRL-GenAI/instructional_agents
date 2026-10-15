"""--only-chapters: generate a chosen subset of chapters, skip the rest.

The runner takes an optional collection of 1-based chapter numbers; the
chapter loop skips everything else. None (default) generates all chapters —
pinned so the vanilla path is untouched.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.ADDIE import ADDIERunner


def _runner(only_chapters, chapters):
    r = ADDIERunner(MagicMock(), output_dir="/tmp/does-not-matter",
                    resume=False, only_chapters=only_chapters)
    r.chapters = chapters
    r.generated = []
    r._run_slides_generation_with_retry = (
        lambda chapter, idx, d: r.generated.append(idx + 1))
    r._save_chapters = lambda: None
    return r


def _drive(r, tmp_path):
    r.output_dir = str(tmp_path)
    r.run_chapter_deliberations()
    return r.generated


CHAPTERS = [{"title": f"Ch {i}"} for i in range(1, 5)]


class TestOnlyChapters:
    def test_default_generates_all(self, tmp_path):
        assert _drive(_runner(None, list(CHAPTERS)), tmp_path) == [1, 2, 3, 4]

    def test_subset_generates_only_those(self, tmp_path):
        assert _drive(_runner({2, 4}, list(CHAPTERS)), tmp_path) == [2, 4]

    def test_single_chapter(self, tmp_path):
        assert _drive(_runner([2], list(CHAPTERS)), tmp_path) == [2]

    def test_empty_collection_means_all(self, tmp_path):
        # falsy collections normalize to None (generate everything)
        assert _drive(_runner(set(), list(CHAPTERS)), tmp_path) == [1, 2, 3, 4]


class TestOutlineEscapeRepair:
    """Outline JSON with LaTeX-style invalid escapes is repaired, not
    replaced by the 3-slide fallback skeleton."""

    def test_invalid_latex_escape_recovers(self):
        from unittest.mock import MagicMock
        from src.slides import SlidesDeliberation
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.catalog_dict = {"slides_length": 30}
        d.retriever = None
        d.section_ids = []
        d.user_feedback = {"slides": "", "overall": ""}
        d.time_slides = 0
        d.token_slides = 0
        agent = MagicMock()
        bad = '[{"slide_id": 1, "title": "Chips", "description": "use \\colorbox{green}{Yes} chips"}]'
        agent.generate_response.return_value = (bad, 0.0, 0)
        d.agents = {"instructional_designer": agent}
        d.slides_outline = []
        d._generate_slides_outline({"title": "T", "description": "D"})
        assert len(d.slides_outline) == 1
        assert d.slides_outline[0]["title"] == "Chips"
