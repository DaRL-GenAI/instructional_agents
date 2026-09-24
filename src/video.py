"""Narrated lecture videos from generated chapter materials.

For every ``exp/<name>/chapter_N`` directory this module turns the compiled
slides (``slides.pdf``; falls back to Pillow-drawn slides from ``slides.tex``)
and the lecture script (``script.md``) into

* ``video/lecture.mp4`` — one H.264/AAC video, one still per slide, narrated
  with OpenAI text-to-speech (soft ``mov_text`` captions, or burned in),
* ``video/lecture.vtt`` / ``video/lecture.srt`` — sidecar captions,
* ``video/timeline.json`` — every segment with slide page, narration text,
  audio hash and start/end seconds (the audit trail of the render),
* ``video/narration/<sha1>.mp3`` — cached narration clips.

The approach (TTS per scene, still image held for the narration, ffmpeg mux
and concat, proportional caption cues) is ported from EduCAST / EduHarness
(https://github.com/DaRL-GenAI/EduCAST) without its Remotion, Manim and
browser dependencies: only ffmpeg, Pillow and the OpenAI SDK are needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from src.video_captions import CaptionCue, build_caption_cues, render_srt, render_webvtt
from src.video_media import (attach_subtitles, concat_segments, ffmpeg_available, probe_duration, still_segment)

TTS_INSTRUCTIONS = (
    "Warm, clear teacher voice. Moderate pace, natural pauses at sentence ends, "
    "slight emphasis on key terms."
)
TTS_MAX_CHARS = 3800  # OpenAI speech input limit is 4096 characters

TTSFunc = Callable[[str, Path], Path]
"""Callable that writes MP3 narration for ``text`` to ``out_path`` and returns it."""


@dataclass
class VideoOptions:
    tts_model: str = "gpt-4o-mini-tts"
    voice: str = "alloy"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    dpi: int = 144
    tail_seconds: float = 0.6
    silent_seconds: float = 3.0
    burn_subtitles: bool = False
    caption_language: str = "eng"
    intro_narration: bool = True
    output_name: str = "lecture.mp4"


@dataclass
class Segment:
    index: int
    page: int                      # 1-based slide page in the deck
    title: str
    narration: str
    section: Optional[int] = None  # script section number the narration came from
    image: str = ""
    audio: str = ""
    audio_sha1: str = ""
    seconds: float = 0.0
    start: float = 0.0
    end: float = 0.0
    cues: list[dict] = field(default_factory=list)


# --------------------------------------------------------------------------- script parsing
_SECTION_RE = re.compile(r"^##\s+Section\s+(\d+)\s*:\s*(.*?)\s*$", re.M)
_GENERIC_H2_RE = re.compile(r"^##\s+(.*?)\s*$", re.M)
_FRAME_COUNT_RE = re.compile(r"^\*\((\d+)\s+frames?\)\*\s*$", re.M)


def parse_script_sections(script_md: str) -> list[dict]:
    """Split ``script.md`` (as written by SlidesDeliberation) into narration sections.

    Returns ``[{"section": int, "title": str, "frames": int, "text": str}]``.
    Falls back to generic ``##`` headings for hand-written scripts.
    """
    text = script_md.replace("\r\n", "\n")
    matches = list(_SECTION_RE.finditer(text))
    generic = False
    if not matches:
        matches = [m for m in _GENERIC_H2_RE.finditer(text)]
        generic = True
    sections: list[dict] = []
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        frames = 1
        fm = _FRAME_COUNT_RE.search(body)
        if fm:
            frames = max(1, int(fm.group(1)))
            body = body[:fm.start()] + body[fm.end():]
        number = i + 1 if generic else int(m.group(1))
        title = (m.group(1) if generic else m.group(2)).strip()
        sections.append({"section": number, "title": title, "frames": frames, "text": clean_for_speech(body)})
    return [s for s in sections if s["text"] or s["title"]]


_MD_FENCE_RE = re.compile(r"```.*?```", re.S)
_MD_INLINE_RE = re.compile(r"`([^`]*)`")
_MD_EMPH_RE = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")
_MD_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_MD_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_TEX_INLINE_RE = re.compile(r"\$([^$]{1,80})\$")


def clean_for_speech(text: str) -> str:
    """Strip Markdown / light LaTeX so the TTS voice does not read symbols aloud."""
    t = _MD_FENCE_RE.sub(" ", text)
    t = _MD_INLINE_RE.sub(r"\1", t)
    t = _MD_LINK_RE.sub(r"\1", t)
    t = _MD_HEADING_RE.sub("", t)
    t = _MD_BULLET_RE.sub("", t)
    t = _MD_EMPH_RE.sub(r"\2", t)
    t = _TEX_INLINE_RE.sub(r"\1", t)
    t = re.sub(r"^\s*-{3,}\s*$", " ", t, flags=re.M)
    t = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*\n\s*", "\n", t)
    return t.strip()


_SENT_RE = re.compile(r"[^.!?。！？]+[.!?。！？]*[\"'”’)]*", re.S)


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.findall(text.replace("\n", " ")) if p.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def split_narration(text: str, parts: int) -> list[str]:
    """Distribute a section's narration over ``parts`` consecutive frames by sentence."""
    parts = max(1, parts)
    if parts == 1:
        return [text.strip()]
    sentences = split_sentences(text)
    if len(sentences) <= parts:
        out = sentences + [""] * (parts - len(sentences))
        return out
    total_chars = sum(len(s) for s in sentences) or 1
    target = total_chars / parts
    buckets: list[list[str]] = [[] for _ in range(parts)]
    b = 0
    used = 0
    for i, s in enumerate(sentences):
        remaining_sents = len(sentences) - i
        remaining_buckets = parts - b
        if b < parts - 1 and buckets[b] and (used >= target * (b + 1) or remaining_sents <= remaining_buckets - 1):
            b += 1
        buckets[b].append(s)
        used += len(s)
    return [" ".join(x).strip() for x in buckets]


def chunk_for_tts(text: str, limit: int = TTS_MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    out, cur = [], ""
    for s in split_sentences(text):
        if len(cur) + len(s) + 1 > limit and cur:
            out.append(cur.strip())
            cur = ""
        cur += " " + s
    if cur.strip():
        out.append(cur.strip())
    return out


# --------------------------------------------------------------------------- slide images
def render_pdf_pages(pdf: Path, out_dir: Path, *, dpi: int = 144) -> list[Path]:
    """Rasterize every page of ``pdf`` to PNG with PyMuPDF, or pdftoppm as a fallback."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("page_*.png"):
        old.unlink()
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None
    pages: list[Path] = []
    if fitz is not None:
        with fitz.open(str(pdf)) as doc:
            zoom = dpi / 72.0
            for i, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                out = out_dir / f"page_{i:03d}.png"
                pix.save(str(out))
                pages.append(out)
        return pages
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(out_dir / "raw")],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = sorted(out_dir.glob("raw-*.png"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
        for i, p in enumerate(raw, start=1):
            out = out_dir / f"page_{i:03d}.png"
            p.replace(out)
            pages.append(out)
        return pages
    raise RuntimeError("Rendering slides.pdf needs PyMuPDF (pip install pymupdf) or pdftoppm (poppler-utils).")


_FRAME_RE = re.compile(r"\\begin\{frame\}(.*?)\\end\{frame\}", re.S)
_FRAMETITLE_RE = re.compile(r"\\frametitle\{((?:[^{}]|\{[^{}]*\})*)\}")
_ITEM_RE = re.compile(r"\\item\s+(.*?)(?=\\item|\\end\{|\\begin\{|$)", re.S)


def _detex(s: str) -> str:
    s = re.sub(r"\\(?:textbf|textit|emph|texttt|underline|textcolor\[HTML\]\{[0-9A-Fa-f]+\}|textcolor\{[^}]*\})\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", " ", s)
    s = s.replace("{", "").replace("}", "").replace("~", " ").replace("\\&", "&").replace("\\%", "%").replace("\\_", "_").replace("\\$", "$")
    s = re.sub(r"%.*", "", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_frames_from_tex(tex: str) -> list[dict]:
    """Rough (title, bullets) per Beamer frame, used only for the Pillow fallback deck."""
    frames = []
    for m in _FRAME_RE.finditer(tex):
        body = m.group(1)
        if "\\titlepage" in body:
            continue
        tm = _FRAMETITLE_RE.search(body)
        title = _detex(tm.group(1)) if tm else ""
        if not tm:
            head = re.match(r"\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}", body)
            if head:
                title = _detex(head.group(1))
        body_wo_code = re.sub(r"\\begin\{(lstlisting|verbatim|minted)\}.*?\\end\{\1\}", " ", body, flags=re.S)
        bullets = [_detex(b) for b in _ITEM_RE.findall(body_wo_code)]
        bullets = [b for b in bullets if b][:8]
        frames.append({"title": title or "Slide", "bullets": bullets})
    return frames


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for c in candidates:
        if Path(c).is_file():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textlength(t, font=font) > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_fallback_slide(out: Path, *, title: str, bullets: list[str], header: str = "", footer: str = "",
                        index: int = 1, total: int = 1, width: int = 1920, height: int = 1080, title_slide: bool = False) -> Path:
    """Draw a clean slide with Pillow when no compiled PDF is available."""
    from PIL import Image, ImageDraw
    bg, ink, text_c, muted, accent = (255, 254, 250), (40, 59, 49), (41, 54, 47), (121, 126, 113), (188, 88, 52)
    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width, 12], fill=accent)
    margin = int(width * 0.05)
    small = _font(int(height * 0.026))
    d.text((margin, int(height * 0.045)), header[:120], font=small, fill=muted)
    if title_slide:
        tf = _font(int(height * 0.075), bold=True)
        lines = _wrap(d, title, tf, width - 2 * margin)
        y = int(height * 0.36)
        for l in lines[:3]:
            d.text((margin, y), l, font=tf, fill=ink)
            y += int(height * 0.095)
        d.rectangle([margin, y + 10, margin + 160, y + 18], fill=accent)
        if bullets:
            sf = _font(int(height * 0.036))
            d.text((margin, y + 50), bullets[0][:120], font=sf, fill=muted)
    else:
        tf = _font(int(height * 0.06), bold=True)
        y = int(height * 0.11)
        for l in _wrap(d, title, tf, width - 2 * margin)[:2]:
            d.text((margin, y), l, font=tf, fill=ink)
            y += int(height * 0.075)
        d.rectangle([margin, y + 6, margin + 120, y + 12], fill=accent)
        y += int(height * 0.05)
        size = int(height * (0.04 if len(bullets) <= 5 else 0.033))
        bf = _font(size)
        for b in bullets:
            lines = _wrap(d, b, bf, width - 2 * margin - 60)
            d.ellipse([margin + 6, y + size * 0.38, margin + 6 + size * 0.36, y + size * 0.74], fill=accent)
            for l in lines:
                if y > height - int(height * 0.12):
                    break
                d.text((margin + 50, y), l, font=bf, fill=text_c)
                y += int(size * 1.35)
            y += int(size * 0.5)
    d.text((margin, height - int(height * 0.07)), footer[:80], font=small, fill=muted)
    pos = f"{index} / {total}"
    d.text((width - margin - d.textlength(pos, font=small), height - int(height * 0.07)), pos, font=small, fill=muted)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


# --------------------------------------------------------------------------- TTS
def openai_tts(model: str = "gpt-4o-mini-tts", voice: str = "alloy", *, instructions: str = TTS_INSTRUCTIONS, client=None) -> TTSFunc:
    """Return a TTS callable backed by the OpenAI speech API (same recipe as EduHarness)."""
    def _tts(text: str, out_path: Path) -> Path:
        nonlocal client
        if client is None:
            from openai import OpenAI
            client = OpenAI()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pieces = chunk_for_tts(text)
        piece_paths: list[Path] = []
        for i, piece in enumerate(pieces):
            target = out_path if len(pieces) == 1 else out_path.with_name(f"{out_path.stem}.part{i}.mp3")
            kwargs = {"model": model, "voice": voice, "input": piece, "response_format": "mp3"}
            if model.startswith("gpt-4o") or "tts" in model and "gpt" in model:
                kwargs["instructions"] = instructions
            last_err: Exception | None = None
            for attempt in range(4):
                try:
                    with client.audio.speech.with_streaming_response.create(**kwargs) as resp:
                        resp.stream_to_file(str(target))
                    last_err = None
                    break
                except Exception as exc:  # retry transient failures only
                    last_err = exc
                    msg = str(exc).lower()
                    transient = any(t in type(exc).__name__ for t in ("Timeout", "Connection", "RateLimit", "InternalServer", "APIStatus")) or any(c in msg for c in ("429", "502", "503", "504"))
                    if not transient or attempt == 3:
                        raise
                    time.sleep(2.0 * (attempt + 1))
            if last_err:
                raise last_err
            piece_paths.append(target)
        if len(piece_paths) > 1:
            from src.video_media import ffmpeg_bin
            listing = out_path.with_suffix(".concat.txt")
            listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in piece_paths), encoding="utf-8")
            subprocess.run([ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(out_path)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            listing.unlink(missing_ok=True)
            for p in piece_paths:
                p.unlink(missing_ok=True)
        return out_path
    return _tts


# --------------------------------------------------------------------------- builder
class LectureVideoBuilder:
    """Render one chapter directory into a narrated lecture video."""

    def __init__(self, chapter_dir: str | Path, options: VideoOptions | None = None, *, tts: TTSFunc | None = None,
                 course_name: str = "", chapter_title: str = "", log: Callable[[str], None] = print):
        self.chapter_dir = Path(chapter_dir)
        self.options = options or VideoOptions()
        self.tts = tts
        self.course_name = course_name
        self.chapter_title = chapter_title or self._guess_title()
        self.log = log
        self.video_dir = self.chapter_dir / "video"
        self.frames_dir = self.video_dir / "frames"
        self.narration_dir = self.video_dir / "narration"
        self.segments_dir = self.video_dir / "segments"

    # ---- inputs
    def _guess_title(self) -> str:
        script = self.chapter_dir / "script.md"
        if script.is_file():
            first = script.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
            if first and first[0].startswith("#"):
                return re.sub(r"^#+\s*(Slides Script:\s*)?", "", first[0]).strip()
        return self.chapter_dir.name.replace("_", " ").title()

    def slide_images(self) -> tuple[list[Path], str]:
        """PNG per slide. Prefers slides.pdf; otherwise draws slides from slides.tex."""
        pdf = self.chapter_dir / "slides.pdf"
        if pdf.is_file() and pdf.stat().st_size > 0:
            return render_pdf_pages(pdf, self.frames_dir, dpi=self.options.dpi), "pdf"
        tex = self.chapter_dir / "slides.tex"
        frames = extract_frames_from_tex(tex.read_text(encoding="utf-8", errors="replace")) if tex.is_file() else []
        if not frames:
            frames = [{"title": s["title"], "bullets": []} for s in parse_script_sections(self._script_text())]
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        for old in self.frames_dir.glob("page_*.png"):
            old.unlink()
        total = len(frames) + 1
        pages = [draw_fallback_slide(self.frames_dir / "page_001.png", title=self.chapter_title, bullets=[self.course_name] if self.course_name else [],
                                     header=self.course_name, footer="Instructional Agents", index=1, total=total,
                                     width=self.options.width, height=self.options.height, title_slide=True)]
        for i, f in enumerate(frames, start=2):
            pages.append(draw_fallback_slide(self.frames_dir / f"page_{i:03d}.png", title=f["title"], bullets=f["bullets"],
                                             header=self.course_name, footer=self.chapter_title, index=i, total=total,
                                             width=self.options.width, height=self.options.height))
        return pages, "tex"

    def _script_text(self) -> str:
        script = self.chapter_dir / "script.md"
        if not script.is_file():
            raise FileNotFoundError(f"{script} not found; generate the chapter first")
        return script.read_text(encoding="utf-8", errors="replace")

    # ---- planning
    def plan(self, pages: list[Path] | None = None) -> list[Segment]:
        """Map script sections onto slide pages. Pure function of the inputs (no API calls)."""
        sections = parse_script_sections(self._script_text())
        if pages is None:
            pages, _ = self.slide_images()
        n_pages = len(pages)
        total_frames = sum(s["frames"] for s in sections)
        has_title_page = n_pages >= total_frames + 1 or (n_pages > 0 and total_frames == 0)
        segments: list[Segment] = []
        page_cursor = 1
        if has_title_page:
            intro = ""
            if self.options.intro_narration:
                intro = f"Welcome to {self.chapter_title}."
                if self.course_name:
                    intro = f"Welcome to {self.chapter_title}, part of {self.course_name}."
                if sections:
                    first = split_sentences(sections[0]["text"])[:1]
                    if first:
                        intro += " " + first[0]
            segments.append(Segment(index=0, page=1, title=self.chapter_title, narration=intro, section=None))
            page_cursor = 2
        for s in sections:
            frames_left = n_pages - page_cursor + 1
            if frames_left <= 0:
                # No slide left for this section: append its narration to the last segment.
                if segments:
                    segments[-1].narration = (segments[-1].narration + " " + s["text"]).strip()
                continue
            k = min(s["frames"], frames_left)
            parts = split_narration(s["text"], k)
            for j, part in enumerate(parts):
                segments.append(Segment(index=len(segments), page=page_cursor, title=s["title"] if k == 1 else f"{s['title']} ({j + 1}/{k})", narration=part, section=s["section"]))
                page_cursor += 1
        # Leftover slides (e.g. an appendix) are shown silently.
        while page_cursor <= n_pages:
            segments.append(Segment(index=len(segments), page=page_cursor, title=f"Slide {page_cursor}", narration="", section=None))
            page_cursor += 1
        for seg in segments:
            seg.image = str(pages[seg.page - 1])
        return segments

    # ---- rendering
    def build(self) -> dict:
        if not ffmpeg_available():
            raise RuntimeError("ffmpeg/ffprobe not found. Install ffmpeg (apt-get install ffmpeg / brew install ffmpeg).")
        started = time.time()
        pages, source = self.slide_images()
        segments = self.plan(pages)
        self.log(f"[video] {self.chapter_dir.name}: {len(pages)} slides ({source}), {len(segments)} segments")
        tts = self.tts or openai_tts(self.options.tts_model, self.options.voice)
        cache_hits = 0
        for seg in segments:
            if not seg.narration.strip():
                continue
            key = hashlib.sha1(f"{self.options.tts_model}|{self.options.voice}|{seg.narration}".encode("utf-8")).hexdigest()
            seg.audio_sha1 = key
            audio = self.narration_dir / f"{key}.mp3"
            if audio.is_file() and audio.stat().st_size > 0:
                cache_hits += 1
            else:
                self.log(f"[video]   narration {seg.index + 1}/{len(segments)}: {len(seg.narration)} chars → TTS")
                tts(seg.narration, audio)
            seg.audio = str(audio)
            seg.seconds = probe_duration(audio) or 0.0
        if cache_hits:
            self.log(f"[video]   {cache_hits} narration clip(s) reused from cache")
        # still-image segments
        self.segments_dir.mkdir(parents=True, exist_ok=True)
        for old in self.segments_dir.glob("seg_*.mp4"):
            old.unlink()
        seg_paths: list[Path] = []
        cursor = 0.0
        all_cues: list[CaptionCue] = []
        for seg in segments:
            out = self.segments_dir / f"seg_{seg.index:03d}.mp4"
            dur = still_segment(Path(seg.image), Path(seg.audio) if seg.audio else None, out,
                                width=self.options.width, height=self.options.height, fps=self.options.fps,
                                tail_seconds=self.options.tail_seconds, silent_seconds=self.options.silent_seconds)
            seg.start = round(cursor, 3)
            seg.end = round(cursor + dur, 3)
            if seg.narration.strip():
                cues = [c.shifted(cursor) for c in build_caption_cues(seg.narration, seg.seconds or dur)]
                seg.cues = [c.as_dict() for c in cues]
                all_cues.extend(cues)
            cursor += dur
            seg_paths.append(out)
        raw = self.video_dir / "lecture.nosubs.mp4"
        total = concat_segments(seg_paths, raw)
        srt = self.video_dir / "lecture.srt"
        vtt = self.video_dir / "lecture.vtt"
        srt.write_text(render_srt(all_cues), encoding="utf-8")
        vtt.write_text(render_webvtt(all_cues), encoding="utf-8")
        final = self.video_dir / self.options.output_name
        try:
            attach_subtitles(raw, srt, final, burn=self.options.burn_subtitles, language=self.options.caption_language)
            raw.unlink(missing_ok=True)
        except Exception as exc:  # captions are optional: keep the plain video
            self.log(f"[video]   caption track failed ({exc}); keeping video without embedded captions")
            raw.replace(final)
        shutil.rmtree(self.segments_dir, ignore_errors=True)
        summary = {
            "chapter_dir": str(self.chapter_dir),
            "chapter_title": self.chapter_title,
            "course_name": self.course_name,
            "video": str(final),
            "captions_vtt": str(vtt),
            "captions_srt": str(srt),
            "slides_source": source,
            "slides": len(pages),
            "segments": [asdict(s) for s in segments],
            "duration_seconds": round(total, 3),
            "tts_model": self.options.tts_model,
            "voice": self.options.voice,
            "narration_chars": sum(len(s.narration) for s in segments),
            "tts_calls": sum(1 for s in segments if s.narration.strip()) - cache_hits,
            "render_seconds": round(time.time() - started, 1),
            "burned_subtitles": self.options.burn_subtitles,
        }
        (self.video_dir / "timeline.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log(f"[video] wrote {final} ({total:.1f}s)")
        return summary


def _chapter_dirs(exp_dir: Path) -> list[Path]:
    dirs = [d for d in exp_dir.glob("chapter_*") if d.is_dir() and (d / "script.md").is_file()]
    return sorted(dirs, key=lambda d: int(re.sub(r"\D", "", d.name) or 0))


def _chapter_titles(exp_dir: Path) -> dict[int, str]:
    f = exp_dir / "processed_chapters.json"
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {i + 1: c.get("title", "") for i, c in enumerate(data) if isinstance(c, dict)}
    except Exception:
        return {}


def render_chapter_video(chapter_dir: str | Path, *, options: VideoOptions | None = None, tts: TTSFunc | None = None,
                         course_name: str = "", chapter_title: str = "", log=print) -> dict:
    return LectureVideoBuilder(chapter_dir, options, tts=tts, course_name=course_name, chapter_title=chapter_title, log=log).build()


def render_course_videos(exp_dir: str | Path, *, options: VideoOptions | None = None, tts: TTSFunc | None = None,
                         course_name: str = "", chapters: list[int] | None = None, log=print) -> list[dict]:
    """Render every ``chapter_N`` of an experiment directory. Returns the per-chapter summaries."""
    exp_dir = Path(exp_dir)
    titles = _chapter_titles(exp_dir)
    results: list[dict] = []
    for d in _chapter_dirs(exp_dir):
        idx = int(re.sub(r"\D", "", d.name) or 0)
        if chapters and idx not in chapters:
            continue
        try:
            results.append(render_chapter_video(d, options=options, tts=tts, course_name=course_name, chapter_title=titles.get(idx, ""), log=log))
        except Exception as exc:
            log(f"[video] {d.name}: FAILED — {exc}")
            results.append({"chapter_dir": str(d), "error": str(exc)})
    index = exp_dir / "videos.json"
    index.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results
