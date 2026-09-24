"""Offline tests for the lecture-video renderer (no API calls; ffmpeg only where available)."""
import json
import shutil
from pathlib import Path

import pytest

from src import video as V
from src.video_captions import build_caption_cues, render_srt, render_webvtt
from src.video_media import ffmpeg_available, silent_mp3

SCRIPT = """# Slides Script: Chapter 1: Agents

## Section 1: Introduction

Welcome everyone. Today we look at **agents**. An agent perceives, reasons and acts.

---

## Section 2: Tools
*(2 frames)*

Tools extend what a model can do. First we call a search tool. Then we parse the result. Finally we act on it.

---

## Section 3: Summary

That is all for today.

---
"""

TEX = r"""\documentclass{beamer}
\begin{document}
\frame{\titlepage}
\begin{frame}[fragile]{Introduction}
\begin{itemize}\item Agents perceive \& act \item \textbf{Tools} help\end{itemize}
\end{frame}
\begin{frame}[fragile]
\frametitle{Tools - Part 1}
\begin{itemize}\item Search\end{itemize}
\end{frame}
\begin{frame}[fragile]
\frametitle{Tools - Part 2}
\begin{lstlisting}
x = 1
\end{lstlisting}
\end{frame}
\begin{frame}{Summary}
\begin{itemize}\item Done\end{itemize}
\end{frame}
\end{document}
"""


def test_parse_script_sections_and_frames():
    sections = V.parse_script_sections(SCRIPT)
    assert [s["section"] for s in sections] == [1, 2, 3]
    assert [s["frames"] for s in sections] == [1, 2, 1]
    assert "**" not in sections[0]["text"] and "agents" in sections[0]["text"]
    assert "(2 frames)" not in sections[1]["text"]


def test_parse_generic_headings():
    sections = V.parse_script_sections("# Title\n\n## Intro\nHello there.\n\n## Next\nBye.")
    assert [s["title"] for s in sections] == ["Intro", "Next"]


def test_split_narration_distributes_sentences():
    parts = V.split_narration("One. Two. Three. Four. Five.", 2)
    assert len(parts) == 2 and all(parts)
    assert " ".join(parts).split() == "One. Two. Three. Four. Five.".split()
    assert V.split_narration("Only one.", 3) == ["Only one.", "", ""]


def test_clean_for_speech():
    t = V.clean_for_speech("- **Bold** item with `code` and $x^2$\n\n```py\nprint(1)\n```\n---\nEnd.")
    assert "**" not in t and "`" not in t and "print" not in t and "$" not in t and "---" not in t
    assert "Bold item" in t


def test_extract_frames_from_tex():
    frames = V.extract_frames_from_tex(TEX)
    assert [f["title"] for f in frames] == ["Introduction", "Tools - Part 1", "Tools - Part 2", "Summary"]
    assert frames[0]["bullets"] == ["Agents perceive & act", "Tools help"]
    assert frames[2]["bullets"] == []  # code listings are not read as bullets


def test_plan_maps_sections_to_pages(tmp_path):
    (tmp_path / "script.md").write_text(SCRIPT)
    (tmp_path / "slides.tex").write_text(TEX)
    b = V.LectureVideoBuilder(tmp_path, course_name="Agents 101", chapter_title="Chapter 1: Agents")
    pages, source = b.slide_images()
    assert source == "tex" and len(pages) == 5  # title + 4 frames
    segs = b.plan(pages)
    assert [s.page for s in segs] == [1, 2, 3, 4, 5]
    assert segs[0].section is None and segs[0].narration.startswith("Welcome to Chapter 1: Agents")
    assert [s.section for s in segs[1:]] == [1, 2, 2, 3]
    assert segs[2].narration and segs[3].narration  # the 2-frame section is split
    assert all(Path(s.image).is_file() for s in segs)


def test_plan_without_title_page_and_with_leftover_slides(tmp_path):
    (tmp_path / "script.md").write_text(SCRIPT)
    b = V.LectureVideoBuilder(tmp_path, chapter_title="X")
    pages = [tmp_path / f"p{i}.png" for i in range(1, 8)]
    for p in pages:
        p.write_bytes(b"")
    segs = b.plan(pages)
    assert len(segs) == 7 and segs[0].page == 1 and segs[-1].narration == ""  # 4 narrated + title + 2 silent
    segs2 = V.LectureVideoBuilder(tmp_path, chapter_title="X").plan(pages[:4])
    assert [s.section for s in segs2] == [1, 2, 2, 3]  # exactly one page per frame: no title page


def test_caption_offsets_and_formats():
    cues = [c.shifted(10.0) for c in build_caption_cues("Hello world. Second sentence here.", 4.0)]
    assert cues[0].start == 10.0 and abs(cues[-1].end - 14.0) < 1e-6
    vtt = render_webvtt(cues)
    srt = render_srt(cues)
    assert vtt.startswith("WEBVTT") and "00:00:10.000 -->" in vtt
    assert srt.startswith("1\n00:00:10,000 -->")


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_end_to_end_with_fake_tts(tmp_path):
    (tmp_path / "script.md").write_text(SCRIPT)
    (tmp_path / "slides.tex").write_text(TEX)
    calls = []

    def fake_tts(text, out):
        calls.append(text)
        return silent_mp3(Path(out), 0.8)

    opts = V.VideoOptions(width=640, height=360, fps=10, tail_seconds=0.2, silent_seconds=0.5)
    summary = V.render_chapter_video(tmp_path, options=opts, tts=fake_tts, course_name="Agents 101", chapter_title="Chapter 1: Agents", log=lambda *_: None)
    video = Path(summary["video"])
    assert video.is_file() and video.stat().st_size > 1000
    assert 4.0 < summary["duration_seconds"] < 7.0  # 5 segments × (0.8 s + 0.2 s tail)
    assert len(calls) == 5 and summary["tts_calls"] == 5
    assert Path(summary["captions_vtt"]).read_text().startswith("WEBVTT")
    timeline = json.loads((tmp_path / "video" / "timeline.json").read_text())
    assert [s["page"] for s in timeline["segments"]] == [1, 2, 3, 4, 5]
    assert timeline["segments"][1]["start"] > 0
    # second run reuses the narration cache
    calls.clear()
    summary2 = V.render_chapter_video(tmp_path, options=opts, tts=fake_tts, course_name="Agents 101", chapter_title="Chapter 1: Agents", log=lambda *_: None)
    assert calls == [] and summary2["tts_calls"] == 0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_render_course_videos_index(tmp_path):
    for i in (1, 2):
        d = tmp_path / f"chapter_{i}"
        d.mkdir()
        (d / "script.md").write_text("## Section 1: Only\nShort text.\n")
    (tmp_path / "processed_chapters.json").write_text(json.dumps([{"title": "One"}, {"title": "Two"}]))
    opts = V.VideoOptions(width=320, height=180, fps=5, tail_seconds=0.1, silent_seconds=0.3, intro_narration=False)
    results = V.render_course_videos(tmp_path, options=opts, tts=lambda t, o: silent_mp3(Path(o), 0.4), log=lambda *_: None)
    assert [r["chapter_title"] for r in results] == ["One", "Two"]
    assert (tmp_path / "videos.json").is_file()
