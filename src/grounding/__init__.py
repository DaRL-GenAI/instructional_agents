"""Textbook-grounded course generation.

Subsystem that loads a textbook (via the `src.textbook` ingesters), turns it
into retrievable chunks, retrieves evidence per topic, and injects that
evidence into slide / script / assessment prompts. After each chapter, an
advisory content-fidelity verifier judges the generated claims against the
retrieved evidence and logs a report.

Opt-in via the `--use-textbook <path>` CLI flag. When the flag is absent
nothing in this package is touched and behavior is identical to a vanilla
run.
"""

from src.grounding.content_verifier import ContentVerifier
from src.grounding.contract import build_course_contract, sections_for_chapter
from src.grounding.knowledge_base import Chunk, TextbookKnowledgeBase
from src.grounding.reranker import (
    CrossEncoderReranker,
    HashReranker,
    Reranker,
    apply_rerank,
)
from src.grounding.retriever import (
    Embedder,
    HashEmbedder,
    HybridRetriever,
    OpenAIEmbedder,
    ScoredChunk,
)

__all__ = [
    "Chunk",
    "ContentVerifier",
    "CrossEncoderReranker",
    "Embedder",
    "HashEmbedder",
    "HashReranker",
    "HybridRetriever",
    "OpenAIEmbedder",
    "Reranker",
    "ScoredChunk",
    "TextbookKnowledgeBase",
    "apply_rerank",
    "build_course_contract",
    "sections_for_chapter",
]
