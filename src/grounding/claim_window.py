"""Sentence-bounded text splitting.

``split_into_sentences`` is used by the knowledge-base chunker and the
embedder size guard to break prose on genuine sentence boundaries.

It uses a regex for genuine sentence ends — punctuation followed by
whitespace and then a capital letter or open quote — and maintains a
small list of common abbreviations (``"e.g."``, ``"i.e."``, ``"etc."``,
``"Fig."``, ``"Eq."``) that should NOT count as sentence ends, avoiding
the truncated / mid-sentence splits a naive ``rfind()`` on ``". "``
produced.
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
# Next, consider..."), so treating them as sentence ends is correct.
# The entries here are the abbreviations that almost never end a
# sentence in technical writing.
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
    """Split ``text`` into sentences on genuine sentence boundaries.

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
