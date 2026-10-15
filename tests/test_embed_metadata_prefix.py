"""Tests for the opt-in embed-metadata-prefix (#6).

When ``embed_metadata_prefix`` is on, each chunk is embedded with a
``"<chapter> > <section>\\n"`` location prefix so the dense vector knows where
in the book it lives (helps the global bind step). Off by default — it changes
every embedding, so the cache key must differ to avoid colliding with the
non-prefixed index.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from src.grounding.retriever import HybridRetriever


class _RecEmbedder:
    model = "rec-model"

    def __init__(self):
        self.seen = None

    def embed(self, texts):
        self.seen = list(texts)
        return np.ones((len(texts), 4), dtype=float)


def _kb():
    c = MagicMock()
    c.text = "DBSCAN groups dense points."
    c.chapter_title = "Cluster Analysis"
    c.section_title = "Density-Based Methods"
    c.chunk_id = "ch10.s3:c01"
    c.section_id = "ch10.s3"
    kb = MagicMock()
    kb.chunks = [c]
    kb.textbook_id = "tb"
    return kb


class TestMetadataPrefix:
    def test_default_off_embeds_raw_text(self):
        emb = _RecEmbedder()
        HybridRetriever(_kb(), embedder=emb).ensure_indexed()
        assert emb.seen == ["DBSCAN groups dense points."]

    def test_prefix_on_prepends_location(self):
        emb = _RecEmbedder()
        HybridRetriever(
            _kb(), embedder=emb, embed_metadata_prefix=True
        ).ensure_indexed()
        assert emb.seen == [
            "Cluster Analysis > Density-Based Methods\n"
            "DBSCAN groups dense points."
        ]

    def test_cache_key_differs_between_modes(self):
        off = HybridRetriever(_kb(), embedder=_RecEmbedder())
        on = HybridRetriever(
            _kb(), embedder=_RecEmbedder(), embed_metadata_prefix=True
        )
        assert off._cache_key() != on._cache_key()
