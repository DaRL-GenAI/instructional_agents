"""ffmpeg / ffprobe helpers for lecture-video rendering.

The still-image, mux and concat recipes are ported from EduCAST / EduHarness
(``eduharness/stage2/media.py`` and ``eduharness/stage2/adapters/remotion.py``,
https://github.com/DaRL-GenAI/EduCAST).  Only ffmpeg and ffprobe are needed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

_TOOL_CACHE: dict[str, str | None] = {}


def _resolve_tool(name: str) -> str | None:
    """First working ``name`` binary: $INSTRUCTIONAL_AGENTS_<NAME>, then PATH."""
    if name in _TOOL_CACHE:
        return _TOOL_CACHE[name]
    candidates: list[str] = []
    override = os.environ.get(f"INSTRUCTIONAL_AGENTS_{name.upper()}", "").strip()
    if override:
        candidates.append(override)
    found = shutil.which(name)
    if found:
        candidates.append(found)
    for extra in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin"):
        candidate = Path(extra) / name
        if candidate.is_file():
            candidates.append(str(candidate))
    for candidate in candidates:
        try:
            ok = subprocess.run([candidate, "-version"], capture_output=True, timeout=20).returncode == 0
        except Exception:
            ok = False
        if ok:
            _TOOL_CACHE[name] = candidate
            return candidate
    _TOOL_CACHE[name] = None
    return None


def ffmpeg_bin() -> str:
    return _resolve_tool("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return _resolve_tool("ffprobe") or "ffprobe"


def ffmpeg_available() -> bool:
    return bool(_resolve_tool("ffmpeg") and _resolve_tool("ffprobe"))


def probe_duration(path: Path) -> float | None:
    try:
        value = subprocess.check_output(
            [ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return float(value)
    except Exception:
        return None


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-8:]
        raise RuntimeError(f"{Path(cmd[0]).name} failed ({proc.returncode}): " + " | ".join(tail))


def still_segment(image: Path, audio: Path | None, out: Path, *, width: int = 1920, height: int = 1080,
                  fps: int = 30, tail_seconds: float = 0.6, silent_seconds: float = 3.0) -> float:
    """A slide image held for the narration length (+ tail), encoded as H.264/AAC.

    Without audio the slide is shown for ``silent_seconds`` with a silent track so
    every segment has the same stream layout for lossless concatenation.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p"
    if audio is not None and Path(audio).is_file():
        adur = probe_duration(Path(audio)) or 0.0
        total = adur + tail_seconds
        cmd = [ffmpeg_bin(), "-y", "-loop", "1", "-framerate", str(fps), "-i", str(image), "-i", str(audio),
               "-filter_complex", f"[0:v]{scale}[v];[1:a]apad=pad_dur={tail_seconds:.3f}[a]",
               "-map", "[v]", "-map", "[a]",
               "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-crf", "20",
               "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
               "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    else:
        total = silent_seconds
        cmd = [ffmpeg_bin(), "-y", "-loop", "1", "-framerate", str(fps), "-i", str(image),
               "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
               "-filter_complex", f"[0:v]{scale}[v]", "-map", "[v]", "-map", "1:a",
               "-c:v", "libx264", "-tune", "stillimage", "-preset", "veryfast", "-crf", "20",
               "-c:a", "aac", "-b:a", "128k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(out)]
    _run(cmd)
    return probe_duration(out) or total


def concat_segments(segments: Iterable[Path], out: Path) -> float:
    """Losslessly concatenate identically encoded segments with the concat demuxer."""
    segments = [Path(s) for s in segments]
    if not segments:
        raise ValueError("no segments to concatenate")
    out.parent.mkdir(parents=True, exist_ok=True)
    listing = out.with_suffix(".concat.txt")
    listing.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in segments), encoding="utf-8")
    _run([ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(out)])
    listing.unlink(missing_ok=True)
    return probe_duration(out) or 0.0


def attach_subtitles(video: Path, srt: Path, out: Path, *, burn: bool = False, language: str = "eng") -> None:
    """Add captions as a soft mov_text track (default) or burn them into the frames."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if burn:
        srt_arg = str(srt).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
        _run([ffmpeg_bin(), "-y", "-i", str(video), "-vf", f"subtitles='{srt_arg}'",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "copy", "-movflags", "+faststart", str(out)])
    else:
        _run([ffmpeg_bin(), "-y", "-i", str(video), "-i", str(srt), "-c", "copy", "-c:s", "mov_text",
              "-metadata:s:s:0", f"language={language}", "-movflags", "+faststart", str(out)])


def silent_mp3(out: Path, seconds: float = 1.0) -> Path:
    """A silent MP3, used by tests and dry runs instead of a TTS call."""
    out.parent.mkdir(parents=True, exist_ok=True)
    _run([ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
          "-t", f"{seconds:.3f}", "-c:a", "libmp3lame", "-q:a", "9", str(out)])
    return out
