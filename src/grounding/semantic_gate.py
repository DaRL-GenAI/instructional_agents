"""Semantic gates — free claim-chunk similarity filter.

Two related gates that filter weak retrieval matches the writer would
otherwise cite badly. Both use bi-encoder cosine similarity over the
``sentence-transformers/all-MiniLM-L6-v2`` model (~90 MB, CPU-friendly)
as a $0 quality signal that would otherwise be discarded. We load the
ONNX-exported version via ``fastembed`` so the runtime path stays
torch-free — onnxruntime + tokenizers only.

  * **Gate A (pre-evidence)**: filter retrieval results BEFORE the
    writer sees them. ``sim(slide_query, chunk_text) < threshold`` →
    drop the chunk. Writer literally cannot cite chunks it never
    receives. Threshold tuned to 0.32 against ground-truth grounding
    scores on a previously-measured baseline run.

  * **Gate B (post-emit)**: scan generated text AFTER the LLM commits;
    for each citation token, compute ``sim(claim_sentence, chunk_text)``
    and strip the citation if below threshold. Threshold tuned to 0.30
    (slightly looser — Gate A already filtered the weakest matches).

On the tuning baseline (~1,369 citations from the prior generation
pipeline), Gate B alone caught 27% of bad cites at the cost of dropping
12% of good cites; Gate A on top added another 5-8 percentage points
on the writer's chunk selection (mechanism-bounded estimate).

Both gates degrade safely: if fastembed isn't installed or the encoder
fails to load, the gate is a no-op and the rest of the pipeline runs
unchanged. Vanilla path (no ``--use-textbook``) never constructs the gate.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.grounding.knowledge_base import Chunk, TextbookKnowledgeBase


_CITATION_TOKEN_RE = re.compile(r"\[([^:\[\]]+):(ch\d+(?:\.s\d+)?):p(\d+)\]")


class SemanticGate:
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    DEFAULT_GATE_A_THRESHOLD = 0.32  # pre-evidence; tighter (writer sees
                                      # nothing weak)
    DEFAULT_GATE_B_THRESHOLD = 0.30  # post-emit; gentler (Gate A already
                                      # ran)

    def __init__(
        self,
        kb: Optional["TextbookKnowledgeBase"] = None,
        model_name: str = DEFAULT_MODEL,
        gate_a_threshold: float = DEFAULT_GATE_A_THRESHOLD,
        gate_b_threshold: float = DEFAULT_GATE_B_THRESHOLD,
    ):
        self.kb = kb
        self.model_name = model_name
        self.gate_a_threshold = gate_a_threshold
        self.gate_b_threshold = gate_b_threshold
        self._encoder = None  # lazy
        self._embedding_cache: dict[str, "object"] = {}
        # Build token → chunk text lookup for Gate B
        self._token_to_chunk_text: dict[str, str] = {}
        if kb is not None:
            for ch in getattr(kb, "chunks", []):
                txt = (ch.text or "")[:1500]  # truncate long chunks
                for tok in ch.citation_tokens_in_range():
                    self._token_to_chunk_text[tok] = txt

    def _ensure_encoder(self):
        if self._encoder is not None:
            return True
        try:
            # fastembed runs the ONNX-exported MiniLM bi-encoder via
            # onnxruntime — same model weights as the sentence-transformers
            # variant, no torch dep.
            from fastembed import TextEmbedding
            self._encoder = TextEmbedding(self.model_name)
            return True
        except Exception as e:
            print(f"[semantic-gate] encoder unavailable ({type(e).__name__}: {e}); "
                  f"gate is now a no-op. Install fastembed to enable.")
            self._encoder = False  # sentinel: failed init
            return False

    def _embed(self, text: str):
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        if not self._ensure_encoder() or self._encoder is False:
            return None
        # fastembed's TextEmbedding.embed returns an iterator of numpy
        # arrays; one element per input string. The vectors are not
        # L2-normalised, so we normalise here to keep `.similarity()`'s
        # dot-product == cosine identity intact.
        import numpy as np
        vec = next(iter(self._encoder.embed([text])))
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec = vec / norm
        self._embedding_cache[text] = vec
        return vec

    def similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity in [-1, 1]. Returns 1.0 if encoder
        unavailable so callers see "pass everything" rather than
        "drop everything" — fail-safe."""
        if not text_a or not text_b:
            return 1.0
        va = self._embed(text_a)
        vb = self._embed(text_b)
        if va is None or vb is None:
            return 1.0
        # Both are unit-normalized; cosine == dot product
        return float((va * vb).sum())

    def gate_a_filter_results(self, query: str, results, threshold: Optional[float] = None):
        """Gate A — pre-evidence filter.

        Given the slide/chapter query and the retriever's results,
        drop results whose chunk text scores below the threshold.
        Always keeps the top result (defensive: if EVERYTHING scores
        below, we'd rather show one weak chunk than zero).
        """
        if not results:
            return results
        t = threshold if threshold is not None else self.gate_a_threshold
        if not self._ensure_encoder():
            return results  # encoder unavailable → no-op
        scored = []
        for r in results:
            sim = self.similarity(query, r.chunk.text[:1500])
            scored.append((r, sim))
        survivors = [r for r, sim in scored if sim >= t]
        if not survivors:
            # Keep top-1 by similarity so we never return empty
            scored.sort(key=lambda rs: -rs[1])
            survivors = [scored[0][0]]
        return survivors

    def gate_b_strip_low_similarity(self, text: str, threshold: Optional[float] = None) -> str:
        """Gate B — post-emit strip.

        Scan generated text for citation tokens; for each token, compute
        similarity between the surrounding claim sentence (last ~25
        words ending at the token) and the chunk's text. If below the
        threshold, strip the citation token (keep the claim text
        otherwise intact, mirroring _strip_malformed_citation_tokens).
        """
        if not text or not self._token_to_chunk_text:
            return text
        if not self._ensure_encoder():
            return text  # encoder unavailable → no-op
        t = threshold if threshold is not None else self.gate_b_threshold

        out = []
        last = 0
        for m in _CITATION_TOKEN_RE.finditer(text):
            tok = m.group(0)
            chunk_text = self._token_to_chunk_text.get(tok)
            if chunk_text is None:
                # Unknown token — leave it for _strip_malformed to handle
                continue
            # Claim sentence: last ~25 words ending at the token
            preceding = text[max(0, m.start() - 300):m.start()]
            claim = self._extract_claim_window(preceding)
            sim = self.similarity(claim, chunk_text)
            if sim < t:
                # Strip the citation token; keep claim text
                out.append(text[last:m.start()])
                last = m.end()
                # Also collapse a preceding space if it was attached
                if out and out[-1].endswith(" "):
                    out[-1] = out[-1][:-1]
        out.append(text[last:])
        if last == 0:
            return text  # nothing stripped
        return "".join(out)

    @staticmethod
    def _extract_claim_window(preceding: str, n_words: int = 25) -> str:
        """Pull the last n_words from the text preceding a citation
        token. Used as the 'claim sentence' for similarity scoring.

        An earlier experiment (Tier 1.2) routed this through a regex
        sentence-end detector with abbreviation suppression; that
        change regressed precision on the math-heavy Han corpus
        (-3.84 pp on the 6-chapter subset, with only ~7% citation
        overlap between runs suggesting the divergence reaches far
        upstream). Until we understand the cross-textbook effect, the
        baseline ``rfind`` heuristic stays in place here. The
        sentence-end regex still lives in
        :mod:`src.grounding.claim_window` and is used by the chunker
        (`_split_chunk_if_oversized`) and the embedder size guard,
        which DO benefit from clean sentence boundaries regardless of
        textbook.
        """
        for sep in [". ", "! ", "? ", "\n"]:
            idx = preceding.rfind(sep)
            if idx > 0:
                tail = preceding[idx + len(sep):]
                if tail.strip():
                    preceding = tail
                    break
        words = preceding.split()
        return " ".join(words[-n_words:]) if words else ""
