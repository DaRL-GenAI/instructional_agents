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

Two concrete rerankers are provided:

* ``LLMReranker`` (default) — asks an OpenAI chat model to rate each
  (query, passage) pair on 1–5. No disk / no model download — works
  wherever the OpenAI client works. Costs ~$0.0001 per scoring call on
  gpt-4o-mini.
* ``CrossEncoderReranker`` — uses a ms-marco MiniLM cross-encoder
  (default: ``Xenova/ms-marco-MiniLM-L-6-v2``, ~90 MB) loaded via
  ``fastembed`` (which runs the ONNX-exported model on onnxruntime).
  Faster per-call once loaded; numerically identical scores to the
  original ``cross-encoder/ms-marco-MiniLM-L-6-v2`` released by
  sentence-transformers — no torch dependency.

Plus ``HashReranker`` — a deterministic Jaccard-overlap stub used by
tests and offline dry runs so the plumbing can be exercised without
network or model downloads.

Design rules:

* **Opt-in.** The default ``HybridRetriever.search`` path stays
  reranker-free. A reranker only fires when explicitly passed in.
* **Lazy heavy imports.** Importing this module pulls in nothing heavy.
  The OpenAI client / sentence-transformers model are loaded on first
  ``.score()``. Lets callers exist without paying the cost.
* **Injectable interface.** ``Reranker`` is a `Protocol`; tests can pass
  a deterministic stub (``HashReranker``) without needing weights or
  the API.
* **Graceful degradation.** Library / network errors fall back to the
  original RRF order — never lose the candidate set.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import List, Optional, Protocol, Sequence

# Default cross-encoder model — a small, well-tested MS-MARCO model.
# ~90 MB on disk, CPU-fast, fetched from HuggingFace on first use and
# cached locally. Only used by `CrossEncoderReranker`; `LLMReranker`
# is the default for production. ``Xenova`` is the HuggingFace org
# that hosts the ONNX-exported version of the original
# ``cross-encoder/ms-marco-MiniLM-L-6-v2`` — same weights, same
# inference graph, ~$0 to swap. Loaded via ``fastembed``.
DEFAULT_CROSS_ENCODER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"

# Default LLM chat model for `LLMReranker`. Picked to match the cheap
# tier the rest of the project uses; can be overridden per instance.
DEFAULT_LLM_RERANKER_MODEL = "gpt-4o-mini"

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


class LLMReranker:
    """LLM-based reranker — asks an OpenAI chat model to score each
    (query, passage) pair on 1–5 relevance.

    Why this is the production default:
      * No model weights / no disk / no torch dependency. Works in any
        environment that has an OpenAI client.
      * Argument for natural-language reasoning > a small distilled
        cross-encoder on textbook-style prose, especially for queries
        that are HyDE-expanded paragraphs.
      * Single-tier deployment surface — the rest of the project
        already uses the OpenAI API; one less moving part.

    Cost note:
      * One LLM call PER (query, passage) pair. With top_k=20 candidates
        per query and ~12 grounded retrievals per chapter, that's ~240
        scoring calls per chapter. At gpt-4o-mini's blended ~$0.0003 / 1k
        tokens for ~150 tokens / call, that is ~$0.01 per chapter —
        small relative to the ~$0.05 / chapter generation cost.
      * The model + temperature can be overridden per instance.
    """

    # Each scoring call is structured (short JSON in / short integer out)
    # so it stays tight in token count. Three retries on a transient
    # parse / network failure; on persistent failure we return 3 (the
    # neutral midpoint) for that passage so apply_rerank's overall
    # ordering still works.
    _MAX_RETRIES = 3
    _NEUTRAL_SCORE = 3.0

    def __init__(
        self,
        model: str = DEFAULT_LLM_RERANKER_MODEL,
        client=None,
        temperature: float = 0.0,
        seed: Optional[int] = 42,
    ) -> None:
        self.model = model
        self._client = client
        self.temperature = temperature
        self.seed = seed

    def _ensure_client(self):
        if self._client is None:
            # Lazy import + lazy construction — lets the module be imported
            # without an OpenAI key in env (e.g. by the test suite using
            # the hash stub).
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._client

    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        if not passages:
            return []
        out: List[float] = []
        for passage in passages:
            out.append(self._score_one(query, passage))
        return out

    def _score_one(self, query: str, passage: str) -> float:
        """Score a single (query, passage) pair. Returns float 1.0–5.0."""
        client = self._ensure_client()
        # Truncate very long passages — the reranker only needs to read
        # enough to judge relevance, not the full chunk. Keeps token cost
        # tight.
        passage_excerpt = passage[:1500]
        prompt = (
            "Rate how relevant the textbook PASSAGE is to the QUERY on a "
            "1.0-5.0 scale:\n"
            "  5.0 = directly answers / defines the query topic\n"
            "  4.0 = closely related, same concept area\n"
            "  3.0 = adjacent topic, mentions the query topic in passing\n"
            "  2.0 = different topic but same broad field\n"
            "  1.0 = unrelated\n\n"
            f"QUERY: {query}\n\n"
            f"PASSAGE: {passage_excerpt}\n\n"
            "Respond with STRICT JSON only: "
            '{"SCORE": <float 1.0-5.0>}'
        )
        messages = [
            {"role": "system",
             "content": "You score passage relevance to queries. Output only the JSON object."},
            {"role": "user", "content": prompt},
        ]
        for _ in range(self._MAX_RETRIES):
            try:
                kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                }
                if self.seed is not None:
                    kwargs["seed"] = self.seed
                resp = client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                m = re.search(r'\{[^{}]*"SCORE"[^{}]*\}', text, re.DOTALL)
                if not m:
                    continue
                obj = json.loads(m.group(0))
                score = float(obj.get("SCORE", self._NEUTRAL_SCORE))
                if 1.0 <= score <= 5.0:
                    return score
            except Exception:
                continue
        # Persistent failure — return neutral so this passage doesn't
        # dominate or sink the ranking.
        return self._NEUTRAL_SCORE


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
