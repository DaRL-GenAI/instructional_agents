"""Sentence-bounded claim window extraction.

Shared by ``semantic_gate.SemanticGate`` (Gate B) and
``write_time_verifier.WriteTimeVerifier``. Both need to extract the
"claim sentence" that immediately precedes a citation token so the
LLM judge (or sentence-transformer cosine) can score the token in
context.

The earlier implementation walked backward looking for ``". "`` /
``"! "`` / ``"? "`` / ``"\\n"`` separators via ``rfind()``. That
heuristic split on common abbreviations (e.g., ``"e.g."``, ``"i.e."``,
``"etc."``, ``"Fig."``, ``"Eq."``) and produced truncated or
mid-sentence windows. Both call sites then graded the wrong text
against the chunk, biasing strip / verifier decisions.

The new approach uses a regex for genuine sentence ends — punctuation
followed by whitespace and then a capital letter or open quote — and
maintains a small list of common abbreviations that should NOT count
as sentence ends. The result is the trailing sentence of the
preceding text, with a word-count cap as a fallback.
"""

from __future__ import annotations

import re

# Sentence-end pattern: punctuation, then whitespace, then either an
# uppercase letter or an opening quote / paren that itself precedes
# uppercase text. The lookbehind on the leading character lets us
# avoid splitting on a punctuation that is itself part of an
# abbreviation (handled by the suppression list below).
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[\"\(\[]?[A-Z])")

# Tokens that end with a period but are NOT sentence terminators.
# Lowercased; matched against the last whitespace-delimited word
# preceding a candidate split point.
#
# Note: ``etc.``, ``vs.``, ``viz.`` are deliberately NOT in this set.
# In real prose they often DO end a sentence ("apples, oranges, etc.
# Next, consider..."), and the legacy behaviour of treating them as
# sentence ends produced reasonable claim windows. The entries here
# are the abbreviations that almost never end a sentence in technical
# writing.
_ABBREV_NO_BREAK = frozenset(
    [
        "e.g.", "i.e.", "et", "al.", "et.al.", "et al.", "cf.",
        "fig.", "figs.", "eq.", "eqn.", "eqns.",
        "sec.", "secs.", "ch.", "chap.", "chs.", "chaps.",
        "no.", "nos.", "vol.", "vols.", "pp.", "pg.", "p.",
        "mr.", "mrs.", "ms.", "dr.", "prof.", "st.",
        "jan.", "feb.", "mar.", "apr.", "jun.", "jul.", "aug.",
        "sep.", "sept.", "oct.", "nov.", "dec.",
        "u.s.", "u.k.", "e.u.", "n.b.",
    ]
)


def split_into_sentences(text: str) -> list:
    """Split ``text`` into sentences using the same regex and
    abbreviation-suppression list as :func:`extract_claim_sentence`.

    Used by the chunker (:mod:`src.grounding.knowledge_base`) when a
    chunk is too long for the embedder's per-input limit; the chunk is
    re-emitted as a sequence of sub-chunks split on REAL sentence
    boundaries (not on every period that follows ``e.g.`` or ``Fig.``)
    so each sub-chunk is independently coherent.

    Returns a list of trimmed sentence strings. Empty input → empty list.
    A text with no detected sentence end returns a single-element list
    (the whole text), so callers can always assume the list is non-empty
    when input is non-empty.
    """
    if not text:
        return []
    split_indices = [0]
    for m in _SENTENCE_END_RE.finditer(text):
        head = text[: m.start()].rstrip()
        last_word = head.rsplit(None, 1)[-1].lower() if head.split() else ""
        if last_word in _ABBREV_NO_BREAK:
            continue
        split_indices.append(m.end())
    sentences = []
    for a, b in zip(split_indices, split_indices[1:] + [len(text)]):
        piece = text[a:b].strip()
        if piece:
            sentences.append(piece)
    return sentences or [text.strip()]


def extract_claim_sentence(
    preceding: str,
    *,
    fallback_word_cap: int = 30,
) -> str:
    """Return the last full sentence in ``preceding``.

    ``preceding`` is the text immediately before a citation token
    (typically the last 200-300 characters of the artifact). We split
    on sentence ends, skipping splits that follow common abbreviations,
    and return the final non-empty span. If no sentence end is found
    we fall back to the trailing ``fallback_word_cap`` words.

    The output never contains the citation token itself — callers
    pass the text BEFORE the token's match start.
    """
    if not preceding:
        return ""

    # Walk candidate split points right-to-left. The right-most valid
    # one bounds the claim sentence.
    candidates = []
    for m in _SENTENCE_END_RE.finditer(preceding):
        # Inspect the word ending at the split punctuation; if it
        # matches a known abbreviation, this isn't a real split.
        head = preceding[: m.start()].rstrip()
        last_word = head.rsplit(None, 1)[-1].lower() if head.split() else ""
        if last_word in _ABBREV_NO_BREAK:
            continue
        candidates.append(m.end())

    if candidates:
        tail = preceding[candidates[-1] :].strip()
        if tail:
            return tail
        # If the tail after the last split is empty, fall back to the
        # span between the previous split and the last one (the
        # citation came at the very end of a sentence with no claim
        # text after the period — use the sentence that JUST ended).
        if len(candidates) >= 2:
            return preceding[candidates[-2] : candidates[-1]].strip()
        # Only one split, and the tail is empty: use the head.
        return preceding[: candidates[-1]].strip()

    # No sentence end found — return the trailing N words as a
    # graceful fallback (matches the legacy behaviour).
    words = preceding.split()
    if not words:
        return ""
    return " ".join(words[-fallback_word_cap:])
