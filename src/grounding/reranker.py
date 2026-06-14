"""Reranker — opt-in second-stage scoring for retrieved chunks.

Why a reranker:

The first-stage retriever (BM25 + dense cosine + Reciprocal Rank Fusion in
`src.grounding.retriever`) is *order-aware* but not *semantically aware* —
RRF combines two ranked lists without ever reading the (query, passage)
pair as a whole. A reranker reads each pair together and scores semantic
relevance directly, which RRF cannot.

Empirically this fixes the "first-stage retrieved the right region of
the textbook but missed the exact chunk" failure — the verifier's
``retrieval_bad`` slice. Targets the largest sub-100 % failure-mode
bucket after generation discipline tightened up.

The production reranker is:

* ``CrossEncoderReranker`` — uses a ms-marco MiniLM cross-encoder
  (default: ``Xenova/ms-marco-MiniLM-L-6-v2``, ~90 MB) loaded via
  ``fastembed`` (which runs the ONNX-exported model on onnxruntime).
  Numerically identical scores to the original
  ``cross-encoder/ms-marco-MiniLM-L-6-v2`` released by
  sentence-transformers — no torch dependency.

Plus ``HashReranker`` — a deterministic Jaccard-overlap stub used by
tests and offline dry runs so the plumbing can be exercised without
network or model downloads.

Design rules:

* **Opt-in.** The default ``HybridRetriever.search`` path stays
  reranker-free. A reranker only fires when explicitly passed in.
* **Lazy heavy imports.** Importing this module pulls in nothing heavy.
  The cross-encoder model is loaded on first ``.score()``. Lets callers
  exist without paying the cost.
* **Injectable interface.** ``Reranker`` is a `Protocol`; tests can pass
  a deterministic stub (``HashReranker``) without needing weights.
* **Graceful degradation.** Library / network errors fall back to the
  original RRF order — never lose the candidate set.
"""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Protocol, Sequence

# Default cross-encoder model — a small, well-tested MS-MARCO model.
# ~90 MB on disk, CPU-fast, fetched from HuggingFace on first use and
# cached locally. ``Xenova`` is the HuggingFace org that hosts the
# ONNX-exported version of the original
# ``cross-encoder/ms-marco-MiniLM-L-6-v2`` — same weights, same
# inference graph, ~$0 to swap. Loaded via ``fastembed``.
DEFAULT_CROSS_ENCODER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

# How many first-stage candidates to send to the reranker per query.
# Bigger = better recall before reranking, but slower. 20 is the sweet
# spot for typical textbook retrieval at our chunk count (≤ 5k).
DEFAULT_RERANK_FETCH_K = 20


class Reranker(Protocol):
    """Anything that scores (query, passage) pairs by relevance.

    Returns floats; higher = more relevant. Magnitude is opaque — only
    the ordering is meaningful — so callers must not compare scores
    across reranker instances.
    """

    model: str

    def score(self, query: str, passages: Sequence[str]) -> List[float]: ...


class CrossEncoderReranker:
    """Cross-encoder reranker over a ms-marco MiniLM ONNX model.

    The model is loaded lazily on first ``.score()`` call so importing
    this module doesn't pull in onnxruntime. The lazy import also lets
    callers exist (and pass the instance around) without ever paying
    the load cost if reranking is never invoked.

    Implementation note: previously backed by ``sentence-transformers``
    + PyTorch. Now uses ``fastembed.rerank.cross_encoder.TextCrossEncoder``
    which runs the same model (``Xenova/ms-marco-MiniLM-L-6-v2``, the
    ONNX export of ``cross-encoder/ms-marco-MiniLM-L-6-v2``) via
    onnxruntime. Scores are numerically identical to the old path
    (verified on the test fixture); install footprint dropped from
    ~400 MB (torch) to ~75 MB (onnxruntime).

    Not the default for production — `LLMReranker` is, because it
    avoids the model-download requirement entirely. Provided here for
    environments where local inference is preferable to API calls.
    """

    def __init__(self, model: str = DEFAULT_CROSS_ENCODER_MODEL, device: str = "cpu") -> None:
        self.model = model
        # ``device`` retained for backward compatibility with the older
        # sentence-transformers interface; fastembed runs CPU inference
        # by default via onnxruntime and doesn't expose a device knob.
        self.device = device
        self._encoder = None  # type: ignore[assignment]

    def _ensure_loaded(self):
        if self._encoder is None:
            # Lazy import. ``fastembed`` itself is light (~5 MB), but
            # onnxruntime weighs in around 50 MB and we don't want to
            # pay that on plain ``import src.grounding``.
            from fastembed.rerank.cross_encoder import TextCrossEncoder
            self._encoder = TextCrossEncoder(self.model)
        return self._encoder

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        if not passages:
            return []
        enc = self._ensure_loaded()
        # fastembed's TextCrossEncoder.rerank returns an iterator of
        # floats — one per passage. We materialise to a list so callers
        # get a stable container.
        scores = list(enc.rerank(query, list(passages)))
        return [float(s) for s in scores]


# ---------------------------------------------------------------------------
# A deterministic stub for tests + offline environments
# ---------------------------------------------------------------------------


_WORD = re.compile(r"[A-Za-z0-9]+")


def _bow(text: str) -> set:
    """Bag-of-words feature set; lowercased word tokens, no stopwords stripped."""
    return {m.group(0).lower() for m in _WORD.finditer(text)}


class HashReranker:
    """Deterministic stub — Jaccard overlap between query and passage tokens.

    Not a serious reranker. Used by tests and offline-environment dry runs
    so the plumbing can be exercised without downloading the real model
    or hitting any network. Two passages with more overlapping vocabulary
    with the query land higher.
    """

    def __init__(self) -> None:
        self.model = "hash-jaccard"

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        q = _bow(query)
        if not q:
            return [0.0] * len(passages)
        out: List[float] = []
        for p in passages:
            pb = _bow(p)
            if not pb:
                out.append(0.0)
                continue
            union = q | pb
            inter = q & pb
            out.append(len(inter) / len(union))
        # Tiny tie-break by a content hash so identical-Jaccard passages
        # still have a deterministic order — keeps tests stable.
        for i, p in enumerate(passages):
            h = int(hashlib.md5(p.encode("utf-8")).hexdigest(), 16) % 1000
            out[i] += h / 1_000_000.0  # ≤ 1e-3 nudge; tiny vs the Jaccard score
        return out


# ---------------------------------------------------------------------------
# Pure utility — rerank a candidate set
# ---------------------------------------------------------------------------


def apply_rerank(
    query: str,
    candidates: List,
    reranker: Reranker,
    *,
    top_k: int,
    text_getter=lambda c: c.chunk.text,
):
    """Rerank `candidates` by `reranker.score(query, ...)` and return top-k.

    `candidates` is any list (typically the `ScoredChunk` list returned by
    `HybridRetriever`). `text_getter` extracts the passage text from a
    candidate; defaults to `c.chunk.text` to fit `ScoredChunk` without
    requiring imports.

    On any exception inside the reranker (model load failure, network
    issue downloading weights, OOM on a big batch), we fall back to the
    original order — the caller is no worse off than not reranking.
    """
    if not candidates:
        return []
    passages = [text_getter(c) for c in candidates]
    try:
        scores = reranker.score(query, passages)
    except Exception as e:
        print(f"[reranker] failed ({e}); keeping original order")
        return candidates[:top_k]
    if len(scores) != len(candidates):
        print(
            f"[reranker] score count mismatch "
            f"({len(scores)} vs {len(candidates)}); keeping original order"
        )
        return candidates[:top_k]
    # Stable sort on (-score, original_index) — preserves the first-stage
    # order as a tiebreaker.
    indexed = list(enumerate(candidates))
    indexed.sort(key=lambda pair: (-scores[pair[0]], pair[0]))
    return [c for _, c in indexed[:top_k]]
