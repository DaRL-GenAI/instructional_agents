"""Citation diversity cap (v6 Lever A).

Tracks per-chunk citation counts across a single course-generation run.
When a chunk's emitted-citation count reaches ``cap``, retrieval results
referencing that chunk are filtered out of subsequent evidence blocks,
forcing the writer onto fresh chunks. This redistributes citation load
across the bound sections and lifts page coverage without changing the
writer's prompt shape.

Construction is opt-in: ``ADDIERunner`` only constructs a tracker when
grounding is enabled. The tracker is passed by reference into every
``SlidesDeliberation`` so all chapters share one global per-chunk counter.

A chunk is identified by its canonical ``citation_token()``. Multi-page
chunks emit several valid in-range tokens (``citation_tokens_in_range()``);
the tracker maps each of those back to the same chunk so the count
across all page-specific tokens is summed.

Counts are incremented at write-time: each LLM output is scanned for
``[textbook_id:section_id:p<page>]`` tokens, every resolvable token
bumps the corresponding chunk's count.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.grounding.knowledge_base import Chunk, TextbookKnowledgeBase


_CITATION_TOKEN_RE = re.compile(r"\[([^:\[\]]+):(ch\d+(?:\.s\d+)?):p(\d+)\]")


class CitationUsageTracker:
    DEFAULT_CAP = 15

    def __init__(self, kb: Optional["TextbookKnowledgeBase"] = None, cap: int = DEFAULT_CAP):
        self.cap = cap
        self._counts: dict[str, int] = defaultdict(int)
        # Map every in-range token back to the chunk's canonical key so
        # all variants (p15, p16, p17 of a 15-17 chunk) increment the
        # same counter.
        self._token_to_chunk_key: dict[str, str] = {}
        if kb is not None:
            for ch in getattr(kb, "chunks", []):
                key = ch.citation_token()
                for tok in ch.citation_tokens_in_range():
                    self._token_to_chunk_key[tok] = key

    def chunk_count(self, chunk: "Chunk") -> int:
        return self._counts[chunk.citation_token()]

    def is_over_cap(self, chunk: "Chunk") -> bool:
        return self.chunk_count(chunk) >= self.cap

    def scan_and_increment(self, text: Optional[str]) -> int:
        """Find every well-formed citation token in ``text`` and bump
        the corresponding chunk's counter. Returns the number of
        increments applied (== resolvable tokens found).
        """
        if not text:
            return 0
        increments = 0
        for m in _CITATION_TOKEN_RE.finditer(text):
            tok = m.group(0)
            key = self._token_to_chunk_key.get(tok)
            if key is not None:
                self._counts[key] += 1
                increments += 1
        return increments

    def reset(self) -> None:
        """Wipe all counts. Used by tests."""
        self._counts.clear()
