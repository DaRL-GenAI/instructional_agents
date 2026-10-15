"""Tests for the embedder-size-limit defenses.

Three layers covered:

  * Layer 1 — :func:`src.grounding.knowledge_base._split_chunk_if_oversized`
    splits a parent chunk on sentence boundaries when its text exceeds
    the configured ceiling. Sub-chunks share their parent's section /
    page metadata so the citation token stays stable.

  * Layer 2 — :class:`src.grounding.retriever.OpenAIEmbedder` splits
    oversized inputs on sentence boundaries before calling the API,
    embeds the pieces, and mean-pools the resulting vectors back into
    one row. The output shape (one vector per input) is preserved.

  * Layer 3 — :class:`src.slides.SlidesDeliberation`'s ``_build_evidence_block``
    aborts the run when retrieval fails the same way many times in a
    row, instead of silently retrying and racking up cost.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.grounding.knowledge_base import (
    MAX_CHUNK_CHARS,
    _split_chunk_if_oversized,
    Chunk,
)


def _make_chunk(text: str, *, chunk_id: str = "tb:ch1.s1:c00",
                page_start: int = 5, page_end: int = 7) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        textbook_id="tb",
        chapter_id="ch1",
        chapter_title="Test Chapter",
        section_id="ch1.s1",
        section_title="Test Section",
        para_ids=["p1", "p2"],
        page_start=page_start,
        page_end=page_end,
        kinds=["prose"],
    )


class TestLayer1ChunkSplit:
    def test_undersized_chunk_passes_through(self):
        c = _make_chunk("This is a short chunk. It fits comfortably.")
        out = _split_chunk_if_oversized(c)
        assert out == [c]

    def test_oversized_chunk_is_split_on_sentence_boundaries(self):
        # Build a chunk text whose char count exceeds the ceiling, made
        # of multiple sentences. Each sentence is ~60 chars; we need
        # enough to clearly exceed MAX_CHUNK_CHARS.
        sentence = (
            "K-means partitions n observations into k clusters by minimising variance. "
        )
        text = sentence * (MAX_CHUNK_CHARS // len(sentence) + 5)
        c = _make_chunk(text)
        subs = _split_chunk_if_oversized(c)
        assert len(subs) >= 2
        # Each sub-chunk fits the ceiling.
        for s in subs:
            assert len(s.text) <= MAX_CHUNK_CHARS

    def test_sub_chunks_inherit_section_and_page_metadata(self):
        sentence = "K-means partitions data into clusters. " * 200
        text = sentence + "Centroids are updated iteratively. " * 600
        c = _make_chunk(text, page_start=12, page_end=15)
        subs = _split_chunk_if_oversized(c)
        for s in subs:
            assert s.textbook_id == "tb"
            assert s.section_id == "ch1.s1"
            assert s.page_start == 12
            assert s.page_end == 15
            assert s.chapter_id == "ch1"

    def test_sub_chunks_share_citation_token_with_parent(self):
        """Citation token is keyed on (textbook_id, section_id, page_start)
        — sub-chunks inherit all three so their token is identical to
        the parent's. The ambiguous-token rescue picks the best at score
        time."""
        sentence = "Sentence about clustering. " * 200
        text = sentence * 50
        c = _make_chunk(text, page_start=20)
        subs = _split_chunk_if_oversized(c)
        assert all(s.citation_token() == c.citation_token() for s in subs)

    def test_sub_chunk_ids_are_unique_and_traceable(self):
        sentence = "Sentence. " * 50
        text = sentence * 600
        c = _make_chunk(text, chunk_id="tb:ch1.s1:c07")
        subs = _split_chunk_if_oversized(c)
        ids = [s.chunk_id for s in subs]
        assert len(ids) == len(set(ids))  # unique
        # Sub-chunk ids include the parent id as a prefix
        assert all(i.startswith(c.chunk_id) for i in ids)

    def test_information_is_preserved_across_split(self):
        """No data loss — concatenating sub-chunk texts (modulo
        whitespace) should yield the original chunk text."""
        sentence_a = "First sentence. "
        sentence_b = "Second sentence. "
        text = (sentence_a + sentence_b) * 2000  # ~ 64k chars
        c = _make_chunk(text)
        subs = _split_chunk_if_oversized(c)
        # Words appear in the same order across the union of sub-chunks.
        original_words = text.split()
        recombined = []
        for s in subs:
            recombined.extend(s.text.split())
        assert recombined == original_words

    def test_single_sentence_longer_than_ceiling_falls_back_to_hard_slice(self):
        """Last-resort: one sentence that itself exceeds ceiling. We
        slice on character boundaries rather than dropping it."""
        text = "x" * (MAX_CHUNK_CHARS + 5000)  # one 'sentence', no boundaries
        c = _make_chunk(text)
        subs = _split_chunk_if_oversized(c)
        assert len(subs) >= 2
        for s in subs:
            assert len(s.text) <= MAX_CHUNK_CHARS
        # Reassembly preserves all characters.
        assert "".join(s.text for s in subs) == text


class TestLayer2EmbedderGuard:
    """The embedder splits oversized inputs into pieces, embeds the
    pieces, and mean-pools the resulting vectors back into one row.
    Output shape (one vector per input) stays stable."""

    def test_undersized_inputs_embedded_normally(self):
        from src.grounding.retriever import OpenAIEmbedder, EMBED_INPUT_CHAR_CEILING
        fake_client = MagicMock()
        fake_client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[1.0, 2.0, 3.0]),
                  MagicMock(embedding=[4.0, 5.0, 6.0])]
        )
        emb = OpenAIEmbedder(client=fake_client)
        vecs = emb.embed(["short text one", "short text two"])
        assert vecs.shape == (2, 3)
        # No splitting happened — exactly the inputs we passed went through.
        called = fake_client.embeddings.create.call_args.kwargs["input"]
        assert called == ["short text one", "short text two"]

    def test_oversized_input_split_and_mean_pooled(self):
        from src.grounding.retriever import OpenAIEmbedder, EMBED_INPUT_CHAR_CEILING
        # Two sentences each containing enough chars to exceed the ceiling
        # only when combined. Build a text that splits into >=2 pieces.
        sentence = "K-means clusters points by minimising within-cluster variance. "
        long = sentence * ((EMBED_INPUT_CHAR_CEILING // len(sentence)) + 5)
        fake_client = MagicMock()
        # Whatever number of pieces gets sent in, return a vector per piece
        def _create(model, input):
            return MagicMock(data=[
                MagicMock(embedding=[1.0, 0.0, 0.0]) for _ in input
            ])
        fake_client.embeddings.create.side_effect = _create
        emb = OpenAIEmbedder(client=fake_client)
        vecs = emb.embed([long])
        # Output shape unchanged: one row per input
        assert vecs.shape == (1, 3)
        # The API received multiple pieces (the input was split)
        sent = fake_client.embeddings.create.call_args.kwargs["input"]
        assert len(sent) >= 2
        for s in sent:
            assert len(s) <= EMBED_INPUT_CHAR_CEILING

    def test_mixed_batch_keeps_output_shape(self):
        from src.grounding.retriever import OpenAIEmbedder, EMBED_INPUT_CHAR_CEILING
        sentence = "Sentence one. "
        long = sentence * ((EMBED_INPUT_CHAR_CEILING // len(sentence)) + 5)
        fake_client = MagicMock()
        def _create(model, input):
            return MagicMock(data=[
                MagicMock(embedding=[1.0, 0.0]) for _ in input
            ])
        fake_client.embeddings.create.side_effect = _create
        emb = OpenAIEmbedder(client=fake_client)
        # Three inputs: short / oversized / short. Output should be 3
        # rows regardless of how the oversized one was sliced internally.
        vecs = emb.embed(["short A", long, "short B"])
        assert vecs.shape == (3, 2)


class TestLayer3FailFastOnRetrievalErrors:
    """When retrieval fails the same way 10 times in a row, the
    evidence-block builder raises rather than letting the loop drift
    silently. The counter resets on a successful retrieval."""

    def _make_deliberation(self):
        from src.slides import SlidesDeliberation
        # Bypass __init__; populate only what _build_evidence_block uses.
        d = SlidesDeliberation.__new__(SlidesDeliberation)
        d.retriever = MagicMock()
        d.knowledge_base = MagicMock()
        d.knowledge_base.toc = MagicMock(return_value="")
        d.section_ids = []
        d.textbook_id = "tb"
        # Reset class-level counters for test isolation
        type(d)._consecutive_retrieval_failures = 0
        type(d)._last_retrieval_error_type = None
        return d

    def test_first_few_failures_fall_back_silently(self):
        d = self._make_deliberation()
        d.retriever.search.side_effect = RuntimeError("transient blip")
        # Up to 9 consecutive failures shouldn't raise
        for _ in range(9):
            evidence, rules = d._build_evidence_block("query", artifact="slide")
            assert evidence == ""
            assert rules == ""

    def test_tenth_consecutive_same_failure_raises(self):
        d = self._make_deliberation()
        d.retriever.search.side_effect = ValueError(
            "rate limit reached for embedding"
        )
        with pytest.raises(RuntimeError, match="failed 10 times in a row"):
            for _ in range(10):
                d._build_evidence_block("query", artifact="slide")

    def test_different_error_classes_reset_the_counter(self):
        """Two different error TYPES alternating don't trigger the
        fail-fast — the counter tracks consecutive failures of the SAME
        class so transient errors of varying kinds don't spuriously
        abort the run."""
        d = self._make_deliberation()
        # Alternate two distinct error types
        errs = [RuntimeError("A"), ValueError("B")] * 20
        d.retriever.search.side_effect = errs
        # Should not raise even after 40 calls of alternating errors
        for _ in range(40):
            try:
                d._build_evidence_block("query", artifact="slide")
            except RuntimeError as e:
                if "failed 10 times" in str(e):
                    pytest.fail("alternating errors should not trigger fail-fast")
                # Re-raise other RuntimeErrors (they're the retriever's)
        # Counter never reached threshold for either class

    def test_successful_retrieval_resets_the_counter(self):
        d = self._make_deliberation()
        # 5 failures, then a success, then 8 more failures — should NOT
        # raise (success reset the counter, so the second streak is only 8).
        results_call = 0
        def _side_effect(*args, **kwargs):
            nonlocal results_call
            results_call += 1
            if results_call <= 5:
                raise ValueError("flaky")
            if results_call == 6:
                return []  # success but empty results
            raise ValueError("flaky")
        d.retriever.search.side_effect = _side_effect
        # 14 calls: 5 fail, 1 succeed, 8 fail. The 8 after success should
        # not breach the threshold of 10.
        for _ in range(14):
            d._build_evidence_block("query", artifact="slide")
        # Reached here without raising → counter was reset by the success
