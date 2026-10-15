"""Textbook IR caching.

Saves the parsed Textbook intermediate representation (chapters, sections,
paragraphs) to disk as JSON after a successful ingestion. Subsequent
ingestions of the same source path load from cache instead of re-parsing
the PDF.

Why this exists: when hybrid extraction routes some pages through a
VLM, the parsed IR depends on what the VLM returns. The VLM is not
strictly deterministic across runs (OpenAI seed is best-effort, and
even at temperature=0 small variations occur). Without caching, the
chunks built at generation time would NOT match the chunks built at
verification time — citation tokens emitted during generation would
fail to resolve during eval, even though both runs used the same code
and inputs.

The IR cache pins the parsed representation to disk on first
ingestion. Every later call against the same source returns the
identical IR — generation, evaluation, and subsequent re-runs all
agree on chapter / section / paragraph / chunk IDs.

Cache invalidation is manual: delete the cache file to force fresh
re-ingestion. We do not auto-invalidate on PDF modification time
because the typical workflow ingests once and runs many times.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.textbook.schema import Textbook


_DEFAULT_CACHE_SUBDIR = "ir"


def cache_path(cache_dir: Path, textbook_id: str) -> Path:
    """Return the canonical cache file path for a textbook IR.

    Lives under ``<cache_dir>/ir/<textbook_id>.json`` so the IR cache
    is sibling to the existing embeddings cache and doesn't collide
    with the figure-PNG cache.
    """
    return Path(cache_dir) / _DEFAULT_CACHE_SUBDIR / f"{textbook_id}.json"


def load_ir(cache_dir: Path, textbook_id: str) -> Optional[Textbook]:
    """Load a cached Textbook IR if one exists.

    Returns ``None`` when:
      * the cache file is absent,
      * the file is unreadable (permissions, corruption),
      * the JSON fails to validate against the current Textbook schema
        (e.g. after a schema migration).

    A return of ``None`` is the caller's signal to fall through to a
    fresh ingestion.
    """
    p = cache_path(cache_dir, textbook_id)
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


def save_ir(cache_dir: Path, textbook_id: str, textbook: Textbook) -> Path:
    """Write a Textbook IR to disk in canonical JSON form.

    Creates parent directories as needed. Overwrites any existing
    cache file for the same textbook_id. Returns the path written.
    """
    p = cache_path(cache_dir, textbook_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textbook.model_dump_json(indent=2), encoding="utf-8")
    return p
