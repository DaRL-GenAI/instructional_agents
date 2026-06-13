"""LLM write-time citation verifier.

After the writer commits the final artifacts (slides.tex, script.md,
assessment.md), every citation token is verified with a single
gpt-4o-mini YES/NO call: "Does this excerpt directly support this
claim?" If NO, the citation is stripped (claim text kept).

Design constraints:
  * Different from the eval-time verifier (different prompt, binary
    screen vs. 1-5 rubric scoring). Not circular — eval-time uses a
    different rubric to score the cleaned output.
  * Cheap: ~$0.0001 per call on gpt-4o-mini (250 in / 10 out tokens
    typical). For ~1,300 cites in a typical run, total ~$0.13/run.
  * Defensive: any API error keeps the citation (fail-open). We'd
    rather measure the writer's bad cite than silently drop everything
    on a network blip.
  * Runs LAST in the strip chain (after malformed-strip, after Gate B
    semantic strip). By then we're only verifying citations that:
      (a) are syntactically well-formed
      (b) resolve to a real chunk
      (c) passed sentence-transformer similarity check
    so we only spend $ on borderline cases where the LLM verdict
    matters.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.agents import LLM
    from src.grounding.knowledge_base import TextbookKnowledgeBase


_CITATION_TOKEN_RE = re.compile(r"\[([^:\[\]]+):(ch\d+(?:\.s\d+)?):p(\d+)\]")


_VERIFIER_SYSTEM = (
    "You are a citation-fitness checker. For each (CLAIM, EXCERPT) pair, "
    "decide if the EXCERPT directly supports the CLAIM. Reply with ONLY "
    "one word: YES or NO. Use YES only when the excerpt contains the "
    "specific information the claim makes. Topical adjacency is NOT "
    "support. Tangential mention is NOT support. Use NO for "
    "wrong-section-named cases."
)

_VERIFIER_USER_TEMPLATE = (
    "CLAIM: {claim}\n\n"
    "EXCERPT (from textbook section {section}, page {page}): {excerpt}\n\n"
    "Does the EXCERPT directly support the CLAIM? Reply YES or NO only."
)


class WriteTimeVerifier:
    """LLM-side claim-chunk verifier. Strips citations the gpt-4o-mini
    judge says NO on."""

    def __init__(
        self,
        kb: Optional["TextbookKnowledgeBase"] = None,
        llm: Optional["LLM"] = None,
        model: str = "gpt-4o-mini",
    ):
        self.kb = kb
        self.llm = llm
        self.model = model
        # Token → chunk metadata (text + section + page) for verifier prompt
        self._chunk_meta_by_token: dict[str, dict] = {}
        if kb is not None:
            for ch in getattr(kb, "chunks", []):
                meta = {
                    "text": (ch.text or "")[:1500],
                    "section": ch.section_id,
                    "page_label": (
                        f"p{ch.page_start}-p{ch.page_end}"
                        if ch.page_end > ch.page_start
                        else f"p{ch.page_start}"
                    ),
                }
                for tok in ch.citation_tokens_in_range():
                    self._chunk_meta_by_token[tok] = meta
        self._cache: dict[tuple, bool] = {}
        # Runtime counters for cost diagnostics
        self.calls_made = 0
        self.calls_yes = 0
        self.calls_no = 0
        self.calls_error = 0

    def _verify_one(self, claim: str, token: str) -> bool:
        """Ask the LLM: does this excerpt support this claim? True=YES.
        Fail-open: any error returns True so we don't strip on a blip."""
        meta = self._chunk_meta_by_token.get(token)
        if meta is None:
            return True  # unknown chunk — let malformed strip handle
        # Trim claim to ~30 words for cost control
        claim_short = " ".join(claim.split()[-30:])
        cache_key = (claim_short, token)
        if cache_key in self._cache:
            return self._cache[cache_key]
        if self.llm is None:
            return True
        user_prompt = _VERIFIER_USER_TEMPLATE.format(
            claim=claim_short,
            section=meta["section"],
            page=meta["page_label"],
            excerpt=meta["text"][:800],  # trim chunk for cost
        )
        # LLM.generate_response in src/agents.py takes messages: List[Dict]
        messages = [
            {"role": "system", "content": _VERIFIER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
        try:
            response, _elapsed, _tokens = self.llm.generate_response(
                messages, False,
            )
            self.calls_made += 1
            answer = (response or "").strip().upper()
            if answer.startswith("YES"):
                self._cache[cache_key] = True
                self.calls_yes += 1
                return True
            if answer.startswith("NO"):
                self._cache[cache_key] = False
                self.calls_no += 1
                return False
            # Ambiguous → fail-open
            self._cache[cache_key] = True
            return True
        except Exception as e:
            self.calls_error += 1
            print(f"[write-verifier] LLM call failed for {token}: {e} — keeping cite (fail-open)")
            return True

    def strip_unsupported(self, text: str) -> str:
        """Walk citation tokens in text; ask LLM per token; strip on NO."""
        if not text or self.llm is None or not self._chunk_meta_by_token:
            return text
        out = []
        last = 0
        for m in _CITATION_TOKEN_RE.finditer(text):
            tok = m.group(0)
            preceding = text[max(0, m.start() - 300):m.start()]
            claim = self._extract_claim_window(preceding)
            if not claim.strip():
                continue
            supported = self._verify_one(claim, tok)
            if supported:
                continue  # leave token in place
            # Strip the token
            out.append(text[last:m.start()])
            last = m.end()
            if out and out[-1].endswith(" "):
                out[-1] = out[-1][:-1]
        out.append(text[last:])
        if last == 0:
            return text
        return "".join(out)

    @staticmethod
    def _extract_claim_window(preceding: str, n_words: int = 30) -> str:
        """Last n_words of the text preceding a citation.

        Earlier experiment (Tier 1.2) routed this through a regex
        sentence-end detector. That change correlated with a
        precision regression on the math-heavy Han corpus, so the
        baseline ``rfind`` heuristic stays in place here pending a
        cleaner isolation experiment. The sentence-end regex still
        lives in :mod:`src.grounding.claim_window` and is used by the
        chunker (`_split_chunk_if_oversized`) and the embedder size
        guard — both benefit from clean sentence boundaries
        regardless of textbook.
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

    def report(self) -> str:
        return (
            f"WriteTimeVerifier: {self.calls_made} LLM calls "
            f"(YES={self.calls_yes}, NO={self.calls_no}, "
            f"errors={self.calls_error}) — stripped {self.calls_no} citations"
        )
