"""Deterministic narration chunking and approximate caption timing.

Ported from EduCAST / EduHarness (``eduharness/stage3/captions.py``,
https://github.com/DaRL-GenAI/EduCAST).  The TTS provider returns audio but
no word timestamps, so cues are timed proportionally to estimated speaking
time.  Pure standard library.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import unicodedata


DEFAULT_MAX_UNITS = 84
"""Roughly two 42-character Latin lines or two 21-character CJK lines."""

_STRONG_STOPS = frozenset(".!?;。！？；")
_SOFT_STOPS = frozenset(",:、，：")
_CLOSERS = frozenset("\"')]}’”〉》】）")
_SPACE = re.compile(r"\s+")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*")


@dataclass(frozen=True, slots=True)
class CaptionCue:
    start: float
    end: float
    text: str

    def as_dict(self) -> dict[str, float | str]:
        return asdict(self)

    def shifted(self, offset: float) -> "CaptionCue":
        return CaptionCue(start=round(self.start + offset, 6), end=round(self.end + offset, 6), text=self.text)


def caption_chunks(text: str, *, max_units: int = DEFAULT_MAX_UNITS) -> list[str]:
    """Split narration into readable cues while preserving punctuation."""
    if max_units < 12:
        raise ValueError("max_units must be at least 12")
    normalized = _SPACE.sub(" ", str(text or "")).strip()
    if not normalized:
        return []

    pieces: list[str] = []
    for sentence in _sentence_parts(normalized):
        pieces.extend(_fit_to_width(sentence, max_units))

    packed: list[str] = []
    for piece in pieces:
        if packed:
            joined = _join_text(packed[-1], piece)
            if _display_units(joined) <= max_units:
                packed[-1] = joined
                continue
        packed.append(piece)
    return packed


def build_caption_cues(text: str, duration: float | None, *, max_units: int = DEFAULT_MAX_UNITS) -> list[CaptionCue]:
    """Create contiguous cues spanning ``duration`` seconds (approximate, not forced alignment)."""
    chunks = caption_chunks(text, max_units=max_units)
    if not chunks:
        return []
    total = float(duration or 0.0)
    if total <= 0:
        total = estimate_duration(text)
    total = max(0.25, total)

    weights = [_reading_seconds(chunk) for chunk in chunks]
    weight_total = sum(weights) or float(len(chunks))
    equal_pool = min(total * 0.35, 0.55 * len(chunks))
    weighted_pool = total - equal_pool
    shares = [equal_pool / len(chunks) + weighted_pool * weight / weight_total for weight in weights]

    cues: list[CaptionCue] = []
    cursor = 0.0
    for index, (chunk, share) in enumerate(zip(chunks, shares)):
        end = total if index == len(chunks) - 1 else cursor + share
        cues.append(CaptionCue(start=round(cursor, 6), end=round(end, 6), text=chunk))
        cursor = end
    return cues


def estimate_duration(text: str) -> float:
    """Estimate a natural narration duration when no audio probe is available."""
    return round(max(1.5, _reading_seconds(_SPACE.sub(" ", str(text or "")).strip()) + 0.35), 3)


def render_webvtt(cues: list[CaptionCue]) -> str:
    blocks = ["WEBVTT", ""]
    for index, cue in enumerate(cues, 1):
        text = _SPACE.sub(" ", cue.text).strip().replace("-->", "->")
        if not text:
            continue
        blocks.extend([str(index), f"{_vtt_timestamp(cue.start)} --> {_vtt_timestamp(cue.end)}", text, ""])
    return "\n".join(blocks)


def render_srt(cues: list[CaptionCue]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, 1):
        text = _SPACE.sub(" ", cue.text).strip().replace("-->", "->")
        if not text:
            continue
        blocks.extend([str(index), f"{_srt_timestamp(cue.start)} --> {_srt_timestamp(cue.end)}", text, ""])
    return "\n".join(blocks)


def write_webvtt(path: Path, cues: list[CaptionCue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_webvtt(cues), encoding="utf-8")


def write_srt(path: Path, cues: list[CaptionCue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_srt(cues), encoding="utf-8")


def _sentence_parts(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        char = text[i]
        boundary = char in _STRONG_STOPS
        if char == "." and i > 0 and i + 1 < len(text):
            boundary = not (text[i - 1].isdigit() and text[i + 1].isdigit())
        if boundary:
            end = i + 1
            while end < len(text) and text[end] in _CLOSERS:
                end += 1
            piece = text[start:end].strip()
            if piece:
                parts.append(piece)
            start = end
            i = end
            while start < len(text) and text[start].isspace():
                start += 1
                i += 1
            continue
        i += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _fit_to_width(text: str, max_units: int) -> list[str]:
    remaining = text.strip()
    chunks: list[str] = []
    while remaining and _display_units(remaining) > max_units:
        used = 0
        hard_end = 0
        preferred_end = 0
        for index, char in enumerate(remaining):
            width = _char_units(char)
            if used + width > max_units:
                break
            used += width
            hard_end = index + 1
            if char.isspace() or char in _SOFT_STOPS:
                preferred_end = index + 1
        threshold = max_units * 0.55
        cut = preferred_end if _display_units(remaining[:preferred_end]) >= threshold else hard_end
        cut = max(1, cut)
        chunk = remaining[:cut].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _join_text(left: str, right: str) -> str:
    spacer = " " if left[-1:].isascii() and right[:1].isascii() else ""
    return left + spacer + right


def _display_units(text: str) -> int:
    return sum(_char_units(char) for char in text)


def _char_units(char: str) -> int:
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _reading_seconds(text: str) -> float:
    latin_words = len(_LATIN_WORD.findall(text))
    cjk_glyphs = sum(
        1 for char in text
        if not char.isspace() and ord(char) > 127
        and unicodedata.category(char)[0] in {"L", "N"}
        and unicodedata.east_asian_width(char) in {"W", "F"}
    )
    comma_pauses = sum(text.count(char) for char in _SOFT_STOPS)
    stop_pauses = sum(text.count(char) for char in _STRONG_STOPS)
    return max(0.2, latin_words / 2.75 + cjk_glyphs / 4.2 + comma_pauses * 0.12 + stop_pauses * 0.24)


def _split_ms(seconds: float) -> tuple[int, int, int, int]:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1_000)
    return hours, minutes, secs, millis


def _vtt_timestamp(seconds: float) -> str:
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _srt_timestamp(seconds: float) -> str:
    h, m, s, ms = _split_ms(seconds)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
