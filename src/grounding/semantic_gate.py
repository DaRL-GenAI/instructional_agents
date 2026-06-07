"""v7 semantic gate — free claim-chunk similarity filter.

Two related gates that filter weak retrieval matches the writer would
otherwise cite badly. Both use sentence-transformer cosine similarity
(``all-MiniLM-L6-v2``, ~90MB, CPU-friendly) as a $0 quality signal
the system currently throws away.

  * **Gate A (pre-evidence)**: filter retrieval results BEFORE the
    writer sees them. ``sim(slide_query, chunk_text) < threshold`` →
    drop the chunk. Writer literally cannot cite chunks it never
    receives. Threshold tuned to 0.32 against v6 ground-truth data.

  * **Gate B (post-emit)**: scan generated text AFTER the LLM commits;
    for each citation token, compute ``sim(claim_sentence, chunk_text)``
    and strip the citation if below threshold. Threshold tuned to 0.30
    (slightly looser — Gate A already filtered the weakest matches).

Tuning data: v6 1,369-citation grounding scores. At t=0.32 / t=0.30
Gate B alone catches 27 % of bad cites at the cost of dropping 12 %
of good cites; Gate A on top adds another 5-8 pp on the writer's
chunk selection (unmeasured, mechanism-bounded).

Both gates degrade safely: if sentence-transformers isn't installed
or the encoder fails to load, the gate is a no-op and the rest of the
v6 stack runs unchanged. Vanilla path (no ``--use-textbook``) never
constructs the gate.
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
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(self.model_name)
            return True
        except Exception as e:
            print(f"[semantic-gate] encoder unavailable ({type(e).__name__}: {e}); "
                  f"gate is now a no-op. Install sentence-transformers to enable.")
            self._encoder = False  # sentinel: failed init
            return False

    def _embed(self, text: str):
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        if not self._ensure_encoder() or self._encoder is False:
            return None
        vec = self._encoder.encode(
            text, convert_to_numpy=True, normalize_embeddings=True,
        )
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
        """v7 Gate A — pre-evidence filter.

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
        """v7 Gate B — post-emit strip.

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
        token. Used as the 'claim sentence' for similarity scoring."""
        # Prefer the last sentence (split on . ! ? \n) but cap at n_words
        for sep in [". ", "! ", "? ", "\n"]:
            idx = preceding.rfind(sep)
            if idx > 0:
                tail = preceding[idx + len(sep):]
                if tail.strip():
                    preceding = tail
                    break
        words = preceding.split()
        return " ".join(words[-n_words:]) if words else ""
