"""Regression tests for issues found in code review: outline JSON escapes,
contents-page and caption headings in PDF ingest, sharded verification
edge cases, chapter selection under --resume, and empty-frame detection."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import src.ADDIE as addie_mod
import src.grounding.content_verifier as cv
from src.ADDIE import ADDIERunner
from src.slides import _drop_empty_frames, _parse_outline_json
from src.textbook.ingest_pdf import HeadingState, _normalize_pdf_markdown_headings


def _headings(md: str):
    return [line for line in md.splitlines() if line.startswith("#")]


# ---------------------------------------------------------------- outline JSON
class TestOutlineLatexEscapes:
    @pytest.mark.parametrize("raw, want", [
        (r'[{"t": "\frac{a}{b}"}]', "\\frac{a}{b}"),
        (r'[{"t": "\beta and \colorbox"}]', "\\beta and \\colorbox"),
        (r'[{"t": "\underline{x}"}]', "\\underline{x}"),
        (r'[{"t": "\\alpha ok, \colorbox bad"}]', "\\alpha ok, \\colorbox bad"),
        (r'[{"t": "\nabla f and \textbf{x} and \rho"}]', "\\nabla f and \\textbf{x} and \\rho"),
        (r'[{"t": "\colorbox{green}{Yes}"}]', "\\colorbox{green}{Yes}"),
    ])
    def test_latex_commands_survive(self, raw, want):
        assert _parse_outline_json(raw)[0]["t"] == want

    def test_real_json_escapes_still_decode(self):
        raw = r'[{"t": "a \"quoted\" word\nNext line \u00e9 \\ end"}]'
        assert _parse_outline_json(raw)[0]["t"] == 'a "quoted" word\nNext line é \\ end'

    def test_no_control_characters(self):
        got = _parse_outline_json(r'[{"t": "\frac \beta \bar \fbox"}]')[0]["t"]
        assert "\x08" not in got and "\x0c" not in got


# ---------------------------------------------------------------- PDF ingest
class TestContentsPageAndCaptions:
    def test_contents_page_does_not_take_chapter_numbers(self):
        st = HeadingState()
        pages = [
            "## Contents\n\n## Chapter 1 Introduction\n\n## Chapter 2 Data\n",
            "## Chapter 1 Introduction\n\nBody text of chapter one.",
            "## Chapter 2 Data\n\nBody text of chapter two.",
        ]
        out = [_headings(_normalize_pdf_markdown_headings(p, state=st, page_start=True)[0])
               for p in pages]
        assert "# Chapter 1 Introduction" not in out[0]
        assert out[1] == ["# Chapter 1 Introduction"]
        assert out[2] == ["# Chapter 2 Data"]

    def test_running_header_after_real_opening_is_demoted(self):
        st = HeadingState()
        body = ("This chapter introduces the main ideas of the subject in plain prose. " * 6)
        first = _normalize_pdf_markdown_headings(
            "## Chapter 1 Introduction\n\n" + body, state=st, page_start=True)[0]
        later = _normalize_pdf_markdown_headings(
            "## Chapter 1 Introduction\n\n" + body, state=st, page_start=True)[0]
        assert _headings(first) == ["# Chapter 1 Introduction"]
        assert _headings(later) == ["### Chapter 1 Introduction"]

    @pytest.mark.parametrize("label", ["Figure 2", "Table 2", "Example 2", "Fig. 2", "Exercise 2"])
    def test_page_top_caption_is_not_a_chapter(self, label):
        st = HeadingState()
        _normalize_pdf_markdown_headings("## Chapter 1 Intro\n\ntext", state=st, page_start=True)
        prose = ("This paragraph explains the figure in detail and continues as normal prose. ") * 5
        out = _headings(_normalize_pdf_markdown_headings(
            f"## {label}\n\n" + prose, state=st, page_start=True)[0])
        assert not any(h.startswith("# ") for h in out)

    def test_page_top_title_number_opening_still_promoted(self):
        st = HeadingState()
        _normalize_pdf_markdown_headings("## Chapter 1 Intro\n\ntext", state=st, page_start=True)
        prose = ("Cluster analysis groups objects so that similar ones share a group. ") * 5
        out = _headings(_normalize_pdf_markdown_headings(
            "## Cluster Analysis 2\n\n" + prose, state=st, page_start=True)[0])
        assert out == ["# Chapter 2 Cluster Analysis"]


# ---------------------------------------------------------------- verifier
_ART = {"slides": "\\begin{frame}\\frametitle{T}\nK-Means partitions the data into k clusters of points.\n\\end{frame}"}


class _LegacyJudge:
    def generate_response(self, messages, _stream):
        return json.dumps({"unsupported": [{"index": 1, "claim": "x", "reason": "r"}]}), 0, 0


class _ProtocolJudge:
    def generate_response(self, messages, _stream):
        return json.dumps({"claims": [{"index": 1, "verdict": "unsupported", "reason": "r"}]}), 0, 0


class TestShardedVerification:
    def test_legacy_judge_with_shards_returns_a_report(self, monkeypatch):
        monkeypatch.setattr(cv, "_EVIDENCE_SHARD_CHARS", 100)
        rep = cv.ContentVerifier(llm=_LegacyJudge()).verify_chapter(
            "ch1", "t", _ART, ["s1"],
            full_source_text=("para about clustering. " * 3 + "\n\n") * 6)
        assert "error" not in rep
        assert rep["judge_protocol"] == "legacy_fallback"
        assert rep["flagged_claims"][0]["flag_kind"] == "legacy_unsupported"
        assert rep["evidence_shards"] >= 2

    def test_oversized_paragraph_is_split_not_recursed(self, monkeypatch):
        monkeypatch.setattr(cv, "_EVIDENCE_SHARD_CHARS", 100)
        rep = cv.ContentVerifier(llm=_ProtocolJudge()).verify_chapter(
            "ch1", "t", _ART, ["s1"], full_source_text="x" * 500)
        assert "error" not in rep
        assert rep["evidence_shards"] == 5

    def test_shard_pieces_respect_the_limit(self):
        shards = cv._shard_evidence("word " * 300, 100)
        assert all(len(s) <= 100 for s in shards)
        assert " ".join(s.strip() for s in shards).split() == ["word"] * 300

    def test_sharding_failure_is_fail_open(self, monkeypatch):
        monkeypatch.setattr(cv, "_EVIDENCE_SHARD_CHARS", 100)
        v = cv.ContentVerifier(llm=_ProtocolJudge())
        monkeypatch.setattr(v, "_verify_sharded", MagicMock(side_effect=RuntimeError("boom")))
        rep = v.verify_chapter("ch1", "t", _ART, ["s1"], full_source_text="y " * 200)
        assert rep["summary"] == "verification failed (fail-open)"
        assert "boom" in rep["error"]


# ---------------------------------------------------------------- chapter selection
class TestOnlyChaptersWithResume:
    def test_selected_finished_chapter_is_regenerated(self, tmp_path):
        ch2 = tmp_path / "chapter_2"
        ch2.mkdir()
        for name in ("slides.tex", "script.md", "assessment.md"):
            (ch2 / name).write_text("old content")
        runner = ADDIERunner(MagicMock(), output_dir=str(tmp_path), resume=True, only_chapters={2})
        runner.chapters = [{"title": f"Ch {i}"} for i in range(1, 5)]
        done = []
        runner._run_slides_generation_with_retry = lambda ch, idx, d: done.append(idx + 1)
        with patch.object(addie_mod, "LaTeXCompiler"):
            runner.run_chapter_deliberations()
        assert done == [2]

    def test_resume_without_selection_still_skips_finished(self, tmp_path):
        ch1 = tmp_path / "chapter_1"
        ch1.mkdir()
        for name in ("slides.tex", "script.md", "assessment.md"):
            (ch1 / name).write_text("old content")
        runner = ADDIERunner(MagicMock(), output_dir=str(tmp_path), resume=True)
        runner.chapters = [{"title": "Ch 1"}, {"title": "Ch 2"}]
        done = []
        runner._run_slides_generation_with_retry = lambda ch, idx, d: done.append(idx + 1)
        with patch.object(addie_mod, "LaTeXCompiler"):
            runner.run_chapter_deliberations()
        assert done == [2]


# ---------------------------------------------------------------- empty frames
class TestEmptyFrameDetection:
    def test_brace_group_body_is_content(self):
        deck = "\\begin{frame}\\frametitle{Q}\n{\\Large Any questions?}\n\\end{frame}"
        assert _drop_empty_frames(deck) == deck

    def test_inline_title_only_frame_is_still_dropped(self):
        deck = "\\begin{frame}{Diagram: the pipeline}\n\\end{frame}"
        assert _drop_empty_frames(deck).strip() == ""

    def test_inline_title_with_body_is_kept(self):
        deck = "\\begin{frame}[fragile]{Title}\nReal body text here.\n\\end{frame}"
        assert _drop_empty_frames(deck) == deck
