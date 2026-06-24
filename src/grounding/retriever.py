"""Hybrid retrieval over a TextbookKnowledgeBase.

Combines lexical (BM25, via `rank-bm25`) and dense (embedding cosine)
retrieval, fused with Reciprocal Rank Fusion. The dense index is a plain
numpy matrix on disk — at our scale (≤ 5k chunks per textbook) cosine
similarity in numpy is sub-10ms per query and avoids spinning up a vector
DB. The embedder is an injectable interface so tests can run without
network or an API key.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Protocol, Sequence

import numpy as np
from rank_bm25 import BM25Okapi

from src.grounding.knowledge_base import Chunk, TextbookKnowledgeBase

# Reasonable defaults — chosen up front so callers don't have to think.
DEFAULT_TOP_K = 8           # final number of chunks returned per query
RRF_K = 60                  # Reciprocal Rank Fusion constant (Cormack et al. 2009)
DENSE_FETCH_K = 32          # candidates pulled from each index before fusion
SPARSE_FETCH_K = 32
COSINE_FLOOR = 0.20         # discard dense matches below this (clearly off-topic)
EMBED_BATCH = 64            # how many chunks to embed per API call
EMBED_MODEL = "text-embedding-3-large"
# Hard input ceiling enforced by OpenAI's embedding-3 models. Single
# inputs longer than this throw a 400 and reject the whole batch.
# `OpenAIEmbedder.embed()` splits any input larger than this on sentence
# boundaries, embeds the pieces, and mean-pools the results — a
# defense-in-depth layer behind the chunker's own size cap in
# `knowledge_base._split_chunk_if_oversized`.
EMBED_INPUT_CHAR_CEILING = 24000  # ≈6000 tokens, ~25% headroom under 8192
EMBED_DIM_BY_MODEL = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}
# Note on model choice: `text-embedding-3-large` produces 3072-dim vectors
# (vs `-small`'s 1536) and reportedly improves disambiguation between
# similar-but-not-quite-right chunks on MTEB-style benchmarks by ~5 pp.
# Cost is ~6.5× per token but absolute spend is tiny at our scale (a
# single textbook of ~400-500 chunks costs ~$0.03 to embed one-time;
# the result is cached in `.grounding_cache/` keyed on the model name,
# so existing `_small` caches don't collide with `_large` re-embeds).

# When a reranker is attached, fetch this many first-stage candidates
# BEFORE reranking, then keep the reranker's top-`top_k`. Larger = more
# recall for the reranker to choose from; bounded by the speed of the
# reranker.
DEFAULT_RERANK_FETCH_K = 20


# ---------------------------------------------------------------------------
# Embedder interface
# ---------------------------------------------------------------------------


class Embedder(Protocol):
    """Anything that maps a list of strings to a list of vectors."""

    model: str

    def embed(self, texts: Sequence[str]) -> np.ndarray: ...


class OpenAIEmbedder:
    """OpenAI embeddings, batched.

    The OpenAI client is constructed lazily — only when ``.embed()`` is
    actually called. This lets a cache-hit retriever exist (and answer
    queries) without ``OPENAI_API_KEY`` set, since the cache load path
    never touches the client.
    """

    def __init__(self, model: str = EMBED_MODEL, client=None) -> None:
        self.model = model
        self._client = client  # may be None; created on first .embed()

    def _ensure_client(self):
        if self._client is None:
            # Lazy import so importing this module doesn't require openai.
            from openai import OpenAI
            self._client = OpenAI()
        return self._client

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        client = self._ensure_client()
        vecs: List[np.ndarray] = []
        # Pass 1: per-text. For each input, either embed it whole (fits)
        # or split it on sentence boundaries, embed the pieces, and
        # mean-pool the resulting vectors into one slot. Mean-pooling
        # over sentence sub-embeddings is what bi-encoders do internally
        # for long passages, so semantically it's defensible — and it
        # keeps the output shape (one vector per input) unchanged for
        # downstream code that assumes that contract.
        normalised: List[List[str]] = []
        for t in texts:
            if len(t) <= EMBED_INPUT_CHAR_CEILING:
                normalised.append([t])
            else:
                from src.grounding.claim_window import split_into_sentences
                sentences = split_into_sentences(t)
                # Re-pack sentences into pieces ≤ ceiling. A single
                # sentence longer than ceiling (rare) falls back to a
                # hard slice.
                pieces: List[str] = []
                buf: List[str] = []
                buf_len = 0
                for s in sentences:
                    if len(s) > EMBED_INPUT_CHAR_CEILING:
                        if buf:
                            pieces.append(" ".join(buf))
                            buf, buf_len = [], 0
                        for start in range(0, len(s), EMBED_INPUT_CHAR_CEILING):
                            pieces.append(s[start : start + EMBED_INPUT_CHAR_CEILING])
                        continue
                    if buf and buf_len + len(s) + 1 > EMBED_INPUT_CHAR_CEILING:
                        pieces.append(" ".join(buf))
                        buf = [s]
                        buf_len = len(s)
                    else:
                        buf.append(s)
                        buf_len += len(s) + 1
                if buf:
                    pieces.append(" ".join(buf))
                normalised.append(pieces)

        # Pass 2: flatten the per-input piece-lists into one batch
        # stream, embed, then reduce each input's pieces back into one
        # vector by mean-pooling.
        flat: List[str] = []
        boundaries: List[int] = [0]
        for pieces in normalised:
            flat.extend(pieces)
            boundaries.append(len(flat))

        flat_vecs: List[List[float]] = []
        for start in range(0, len(flat), EMBED_BATCH):
            batch = list(flat[start : start + EMBED_BATCH])
            resp = client.embeddings.create(model=self.model, input=batch)
            flat_vecs.extend(item.embedding for item in resp.data)
        flat_arr = np.asarray(flat_vecs, dtype=np.float32)

        for a, b in zip(boundaries, boundaries[1:]):
            piece_vecs = flat_arr[a:b]
            if piece_vecs.shape[0] == 1:
                vecs.append(piece_vecs[0])
            else:
                # Mean-pool sub-embeddings for this input. L2-renormalise
                # so cosine downstream stays meaningful.
                avg = piece_vecs.mean(axis=0)
                n = float(np.linalg.norm(avg))
                vecs.append(avg / n if n > 0 else avg)
        return np.stack(vecs).astype(np.float32)


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder — for tests.

    Two texts with similar token sets land in similar directions. Not
    semantic by any stretch — but enough to verify the retrieval/RRF
    plumbing without burning an API key.
    """

    def __init__(self, dim: int = 64) -> None:
        self.model = f"hash-{dim}"
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in _tokenize(t):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                out[i, h % self.dim] += 1.0
        # L2-normalise so cosine == dot product.
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


# ---------------------------------------------------------------------------
# Tokenization (shared by BM25 and the hash embedder)
# ---------------------------------------------------------------------------


_WORD = re.compile(r"[A-Za-z0-9]+")
# Light stopword list. Cheap; helps BM25 a lot on textbook prose.
_STOP = frozenset(
    "a an and are as at be by for from has have he in is it its of on or that "
    "the to was were will with which who whom this these those i you we they "
    "their our its but not no nor so if then than when where why how do does "
    "did done can could may might must shall should would about into through".split()
)


def _tokenize(text: str) -> List[str]:
    return [t for t in (m.group(0).lower() for m in _WORD.finditer(text)) if t not in _STOP]


# ---------------------------------------------------------------------------
# Scored result
# ---------------------------------------------------------------------------


@dataclass
class ScoredChunk:
    """A retrieval hit: the chunk plus its fused score and per-index ranks."""

    chunk: Chunk
    rrf_score: float
    bm25_rank: Optional[int]      # 0-indexed; None if not in the BM25 top-N
    dense_rank: Optional[int]     # 0-indexed; None if filtered or absent
    bm25_score: Optional[float]
    cosine: Optional[float]

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id


# ---------------------------------------------------------------------------
# The retriever
# ---------------------------------------------------------------------------


class HybridRetriever:
    """BM25 + dense cosine + RRF fusion over a TextbookKnowledgeBase."""

    def __init__(
        self,
        kb: TextbookKnowledgeBase,
        embedder: Optional[Embedder] = None,
        cache_dir: Optional[Path] = None,
        reranker: Optional["Reranker"] = None,  # type: ignore[name-defined]
        embed_metadata_prefix: bool = False,
    ) -> None:
        if not kb.chunks:
            raise ValueError("knowledge base has no chunks — nothing to retrieve")
        self.kb = kb
        self.embedder: Embedder = embedder if embedder is not None else OpenAIEmbedder()
        # When True, each chunk is embedded with a "<chapter> > <section>\n"
        # location prefix so the dense vector knows WHERE in the book it lives —
        # helps the global chapter→section bind step disambiguate a term that
        # recurs across domains. OPT-IN (default off): it changes every
        # embedding, so it invalidates the embedding cache and needs an A/B
        # recall check before flipping on. The cache key folds in this flag so
        # prefixed and non-prefixed indexes never collide.
        self._embed_metadata_prefix = embed_metadata_prefix

        # Optional second-stage cross-encoder reranker. When set, search()
        # pulls a larger first-stage candidate set (DEFAULT_RERANK_FETCH_K)
        # from RRF, then reorders by (query, passage) semantic relevance
        # and returns top-k of the reranked list. When None: existing
        # behavior — RRF top-k is returned directly. See
        # `src.grounding.reranker` for the protocol.
        self.reranker = reranker

        # BM25 over the chunk texts — cheap, build eagerly.
        self._tokenised: List[List[str]] = [_tokenize(c.text) for c in kb.chunks]
        self._bm25 = BM25Okapi(self._tokenised)

        # Dense index: a (n_chunks, dim) numpy matrix. Optionally cached on
        # disk so reruns skip the embedding API call.
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._embeddings: Optional[np.ndarray] = None  # built on first call

    # ----- public API -----------------------------------------------------

    def ensure_indexed(self) -> None:
        """Build (or load from cache) the dense embeddings.

        Called lazily on the first `.search()`, but exposed so callers can
        warm the index up front (and surface API costs early in a run).
        """
        if self._embeddings is not None:
            return
        cached = self._load_cache()
        if cached is not None:
            self._embeddings = cached
            return
        t0 = time.perf_counter()
        if self._embed_metadata_prefix:
            texts = [self._chunk_embed_text(c) for c in self.kb.chunks]
        else:
            texts = [c.text for c in self.kb.chunks]
        self._embeddings = self.embedder.embed(texts)
        self._normalise_rows(self._embeddings)
        elapsed = time.perf_counter() - t0
        print(
            f"[retriever] embedded {len(texts)} chunks in {elapsed:.1f}s "
            f"({self.embedder.model})"
        )
        self._save_cache(self._embeddings)

    def search(
        self,
        query: str,
        *,
        top_k: int = DEFAULT_TOP_K,
        section_ids: Optional[Iterable[str]] = None,
    ) -> List[ScoredChunk]:
        """Return up to `top_k` chunks for `query`, fused across BM25 + dense.

        Optional `section_ids` restricts retrieval to the given sections —
        the contract-aware path (each topic in a CourseContract maps to a
        small set of sections; we only retrieve from those).
        """
        self.ensure_indexed()

        allowed: Optional[set[int]] = None
        if section_ids is not None:
            wanted = set(section_ids)
            allowed = {
                i for i, c in enumerate(self.kb.chunks) if c.section_id in wanted
            }
            if not allowed:
                return []

        bm25_ranked = self._bm25_ranking(query, allowed)
        dense_ranked = self._dense_ranking(query, allowed)

        # When a reranker is attached we pull a larger first-stage set
        # (so the reranker has more candidates to choose from), then
        # reorder + truncate to `top_k` below. When no reranker: fuse
        # directly to top_k as before.
        first_stage_k = DEFAULT_RERANK_FETCH_K if self.reranker is not None else top_k
        fused = self._rrf(bm25_ranked, dense_ranked, top_k=first_stage_k)

        # Build ScoredChunk objects; carry per-index ranks/scores for
        # debugging and downstream attribution.
        bm25_by_id = {cid: (rank, score) for rank, (cid, score) in enumerate(bm25_ranked)}
        dense_by_id = {cid: (rank, score) for rank, (cid, score) in enumerate(dense_ranked)}

        out: List[ScoredChunk] = []
        for cid, rrf_score in fused:
            chunk = self._chunk_lookup[cid]
            br = bm25_by_id.get(cid)
            dr = dense_by_id.get(cid)
            out.append(
                ScoredChunk(
                    chunk=chunk,
                    rrf_score=rrf_score,
                    bm25_rank=br[0] if br else None,
                    dense_rank=dr[0] if dr else None,
                    bm25_score=br[1] if br else None,
                    cosine=dr[1] if dr else None,
                )
            )

        # Second stage: cross-encoder reranking. The reranker reads
        # (query, passage) as a pair and gives a semantic-relevance score
        # that RRF's order-agnostic fusion can't produce. On any failure
        # we keep the first-stage order — caller is never worse off.
        if self.reranker is not None and out:
            from src.grounding.reranker import apply_rerank
            out = apply_rerank(query, out, self.reranker, top_k=top_k)

        return out

    # ----- internals ------------------------------------------------------

    @property
    def _chunk_lookup(self) -> dict[str, Chunk]:
        if not hasattr(self, "_chunk_lookup_cache"):
            self._chunk_lookup_cache = {c.chunk_id: c for c in self.kb.chunks}
        return self._chunk_lookup_cache

    def _bm25_ranking(
        self, query: str, allowed: Optional[set[int]]
    ) -> List[tuple[str, float]]:
        scores = self._bm25.get_scores(_tokenize(query))
        idxs = np.argsort(-scores)
        out: List[tuple[str, float]] = []
        for i in idxs:
            if allowed is not None and int(i) not in allowed:
                continue
            s = float(scores[i])
            if s <= 0.0:
                break  # ranked list is descending; rest are zero
            out.append((self.kb.chunks[int(i)].chunk_id, s))
            if len(out) >= SPARSE_FETCH_K:
                break
        return out

    def _dense_ranking(
        self, query: str, allowed: Optional[set[int]]
    ) -> List[tuple[str, float]]:
        if self._embeddings is None:  # pragma: no cover — ensure_indexed ran
            return []
        q_vec = self.embedder.embed([query])[0]
        # L2-normalise the query; index is already normalised → dot == cosine.
        n = float(np.linalg.norm(q_vec))
        if n > 0:
            q_vec = q_vec / n
        sims = self._embeddings @ q_vec  # shape (n_chunks,)
        idxs = np.argsort(-sims)
        out: List[tuple[str, float]] = []
        for i in idxs:
            if allowed is not None and int(i) not in allowed:
                continue
            cos = float(sims[i])
            if cos < COSINE_FLOOR:
                break  # ranked list is descending; rest are below floor
            out.append((self.kb.chunks[int(i)].chunk_id, cos))
            if len(out) >= DENSE_FETCH_K:
                break
        return out

    @staticmethod
    def _rrf(
        bm25_ranked: List[tuple[str, float]],
        dense_ranked: List[tuple[str, float]],
        *,
        top_k: int,
    ) -> List[tuple[str, float]]:
        """Reciprocal Rank Fusion. RRF score = sum(1 / (k + rank))."""
        scores: dict[str, float] = {}
        for rank, (cid, _) in enumerate(bm25_ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        for rank, (cid, _) in enumerate(dense_ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return ranked[:top_k]

    def _chunk_embed_text(self, c) -> str:
        """Chunk text prefixed with its structural location for embedding —
        ``"<chapter> > <section>\\n<text>"`` — so the dense vector knows WHERE
        in the book the passage lives. Used only when
        ``embed_metadata_prefix`` is on."""
        ch = (getattr(c, "chapter_title", "") or "").strip()
        sec = (getattr(c, "section_title", "") or "").strip()
        loc = " > ".join(s for s in (ch, sec) if s)
        return f"{loc}\n{c.text}" if loc else (c.text or "")

    @staticmethod
    def _normalise_rows(m: np.ndarray) -> None:
        """L2-normalise in place. Zero rows stay zero."""
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        m /= norms

    # ----- disk cache for embeddings -------------------------------------

    def _cache_key(self) -> str:
        """Tied to textbook content + embedder model + chunk count."""
        h = hashlib.md5()
        h.update(self.kb.textbook_id.encode())
        h.update(self.embedder.model.encode())
        h.update(b"meta-prefix" if self._embed_metadata_prefix else b"raw")
        h.update(str(len(self.kb.chunks)).encode())
        # Hash the chunk ids so a re-ingest with a different chunking
        # config invalidates the cache automatically.
        for c in self.kb.chunks:
            h.update(c.chunk_id.encode())
        return h.hexdigest()[:16]

    def _cache_path(self) -> Optional[Path]:
        if self._cache_dir is None:
            return None
        return self._cache_dir / f"{self.kb.textbook_id}_{self._cache_key()}.npz"

    def _load_cache(self) -> Optional[np.ndarray]:
        p = self._cache_path()
        if p is None or not p.exists():
            return None
        try:
            data = np.load(p)
            arr = data["embeddings"]
            if arr.shape[0] != len(self.kb.chunks):
                return None  # stale cache
            print(f"[retriever] loaded {arr.shape[0]} cached embeddings from {p.name}")
            return arr.astype(np.float32, copy=False)
        except Exception as e:  # corrupted cache file
            print(f"[retriever] cache load failed ({e}); re-embedding")
            return None

    def _save_cache(self, embeddings: np.ndarray) -> None:
        p = self._cache_path()
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez(p, embeddings=embeddings)
        # A sidecar JSON for human inspection of what's in the cache.
        meta = {
            "textbook_id": self.kb.textbook_id,
            "embedder_model": self.embedder.model,
            "n_chunks": len(self.kb.chunks),
            "shape": list(embeddings.shape),
        }
        p.with_suffix(".json").write_text(json.dumps(meta, indent=2))
