"""Textbook IR caching.

Saves the parsed Textbook intermediate representation (chapters, sections,
paragraphs) to disk as JSON after a successful ingestion. Subsequent
ingestions of the same source path load from cache instead of re-parsing
the PDF.

Why this exists: PDF parsing (and the optional equation-VLM pass) is
slow relative to the rest of a run, and re-runs / ``--resume`` should see
byte-identical chapter / section / paragraph / chunk IDs. The IR cache
pins the parsed representation to disk on first ingestion.

Entries are keyed by ``textbook_id`` plus a fingerprint of the SOURCE
CONTENT (see ``knowledge_base._source_fingerprint``), so swapping the
file behind the same name automatically re-ingests. Deleting the cache
file also forces a fresh ingestion.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.textbook.schema import Textbook


_DEFAULT_CACHE_SUBDIR = "ir"


def cache_path(cache_dir: Path, textbook_id: str,
               fingerprint: Optional[str] = None) -> Path:
    """Return the canonical cache file path for a textbook IR.

    Lives under ``<cache_dir>/ir/<textbook_id>[_<fingerprint>].json`` so
    the IR cache is sibling to the embeddings cache and doesn't collide
    with the figure-PNG cache. ``fingerprint`` is the source-content hash;
    when given it becomes part of the file name so a changed source never
    hits a stale entry.
    """
    stem = f"{textbook_id}_{fingerprint}" if fingerprint else textbook_id
    return Path(cache_dir) / _DEFAULT_CACHE_SUBDIR / f"{stem}.json"


def load_ir(cache_dir: Path, textbook_id: str,
            fingerprint: Optional[str] = None) -> Optional[Textbook]:
    """Load a cached Textbook IR if one exists.

    Returns ``None`` when:
      * the cache file is absent,
      * the file is unreadable (permissions, corruption),
      * the JSON fails to validate against the current Textbook schema
        (e.g. after a schema migration).

    A return of ``None`` is the caller's signal to fall through to a
    fresh ingestion.
    """
    p = cache_path(cache_dir, textbook_id, fingerprint)
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        print(f"[ir-cache] read failed for {p}: {type(e).__name__}: {e}")
        return None
    try:
        return Textbook.model_validate_json(raw)
    except Exception as e:
        print(
            f"[ir-cache] schema validation failed for {p}: "
            f"{type(e).__name__}: {e}. Will re-ingest from source."
        )
        return None


def save_ir(cache_dir: Path, textbook_id: str, textbook: Textbook,
            fingerprint: Optional[str] = None) -> Path:
    """Write a Textbook IR to disk in canonical JSON form.

    Creates parent directories as needed. Overwrites any existing
    cache file for the same key. Returns the path written.
    """
    p = cache_path(cache_dir, textbook_id, fingerprint)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textbook.model_dump_json(indent=2), encoding="utf-8")
    return p
