"""Textbook-grounded course generation.

Subsystem that loads a textbook (via the `src.textbook` ingesters), turns it
into retrievable chunks, retrieves evidence per topic, and injects that
evidence into slide / script / assessment prompts.

Opt-in via the `--use-textbook <path>` CLI flag. When the flag is absent
nothing in this package is touched and behavior is identical to a vanilla
run.

Imports are resolved lazily (PEP 562) so that ``import src.grounding`` --
and therefore ``import src.ADDIE`` -- never pulls in the optional grounding
dependencies (``rank-bm25``, ``markdown-it-py``, ``pymupdf``). They are only
needed once a textbook is actually loaded.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.grounding.contract import build_course_contract, sections_for_chapter
    from src.grounding.knowledge_base import Chunk, TextbookKnowledgeBase
    from src.grounding.retriever import (
        Embedder,
        HashEmbedder,
        HybridRetriever,
        OpenAIEmbedder,
        ScoredChunk,
    )

_EXPORTS = {
    "Chunk": "src.grounding.knowledge_base",
    "TextbookKnowledgeBase": "src.grounding.knowledge_base",
    "Embedder": "src.grounding.retriever",
    "HashEmbedder": "src.grounding.retriever",
    "HybridRetriever": "src.grounding.retriever",
    "OpenAIEmbedder": "src.grounding.retriever",
    "ScoredChunk": "src.grounding.retriever",
    "build_course_contract": "src.grounding.contract",
    "sections_for_chapter": "src.grounding.contract",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str):
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'src.grounding' has no attribute {name!r}")
    module = importlib.import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value  # cache for subsequent lookups
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
