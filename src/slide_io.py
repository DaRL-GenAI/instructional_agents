"""Shared file and response helpers for slide-generation modules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND_TRAILER = b"\x00\x00\x00\x00IEND\xaeB`\x82"


def atomic_write(path: Path, content: str) -> None:
    """Replace a UTF-8 text file without leaving a failed temporary write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from plain or fenced model output."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def valid_png_bytes(raw: bytes) -> bool:
    """Reject truncated PNGs while validating their structural boundary chunks."""
    if (
        len(raw) < 36
        or not raw.startswith(PNG_SIGNATURE)
        or raw[12:16] != b"IHDR"
        or not raw.endswith(PNG_IEND_TRAILER)
    ):
        return False
    width = int.from_bytes(raw[16:20], "big")
    height = int.from_bytes(raw[20:24], "big")
    return width > 0 and height > 0


def valid_png_file(path: Path) -> bool:
    try:
        return path.is_file() and valid_png_bytes(path.read_bytes())
    except OSError:
        return False
