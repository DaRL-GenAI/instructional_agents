"""Tests for the hybrid retriever (BM25 + dense cosine + RRF).

Uses the labelled mini PDF fixture as the primary KB. Dense path tested
with a deterministic HashEmbedder so no API key is needed. A Layer-2
test against the real Han PDFs runs only when those files are present.
"""

from pathlib import Path

import numpy as np
import pytest

from src.grounding import (
    Chunk,
    HashEmbedder,
    HybridRetriever,
    TextbookKnowledgeBase,
)
from src.grounding.knowledge_base import _paragraph_chunks
from src.grounding.retriever import (
    COSINE_FLOOR,
    DEFAULT_TOP_K,
    RRF_K,
    _tokenize,
)
from src.textbook.schema import Chapter, PageSpan, Paragraph, Section

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"
HAN_DIR = PROJECT_ROOT / "data" / "textbooks" / "han_data_mining_3e"


# -------------------------------- helpers ---------------------------------


def _para(idx: int, text: str, page: int = 1, kind: str = "prose") -> Paragraph:
    return Paragraph(
        para_id=f"ch1.s1.p{idx:02d}", text=text, page=page, kind=kind,
    )


def _section(section_id: str, paras: list[Paragraph]) -> Section:
    pages = [p.page for p in paras] or [1]
    return Section(
        section_id=section_id,
        title="A Section",
        pages=PageSpan(start=min(pages), end=max(pages)),
        paragraphs=paras,
        concepts=[],
    )


def _chapter(section: Section) -> Chapter:
    return Chapter(
        chapter_id="ch1", number=1, title="Chapter 1", pages=section.pages,
        sections=[section], learning_objectives=[],
    )


def _kb_from_paragraphs(paras_by_section: dict[str, list[Paragraph]],
                        textbook_id: str = "tb") -> TextbookKnowledgeBase:
    """Hand-build a TextbookKnowledgeBase from labelled paragraphs."""
    from src.textbook.schema import Textbook
    sections = [_section(sid, ps) for sid, ps in paras_by_section.items()]
    chapter = Chapter(
        chapter_id="ch1", number=1, title="Chapter 1",
        pages=PageSpan(start=1, end=1),
        sections=sections, learning_objectives=[],
    )
    chunks: list[Chunk] = []
    for sec in sections:
        chunks.extend(_paragraph_chunks(sec, chapter, textbook_id))
    tb = Textbook(
        textbook_id=textbook_id, title="Test", authors=[], edition=None,
        source_format="pdf", parser_quality=1.0, chapters=[chapter],
    )
    return TextbookKnowledgeBase(textbook=tb, chunks=chunks)


# -------------------------------- tokenizer -------------------------------


class TestTokenizer:
    def test_lowercase_and_split(self):
        assert _tokenize("Decision Trees Are Useful") == ["decision", "trees", "useful"]

    def test_stopwords_dropped(self):
        assert "the" not in _tokenize("the quick brown fox")

    def test_punctuation_stripped(self):
        assert _tokenize("data, mining; pre-processing!") == [
            "data", "mining", "pre", "processing",
        ]


# -------------------------------- OpenAIEmbedder lazy client --------------


class TestOpenAIEmbedderLazyClient:
    """The OpenAI client must NOT be constructed until .embed() is called.

    Otherwise just *building* a HybridRetriever — even one whose dense
    index is going to be served from disk cache — would require
    OPENAI_API_KEY in the environment. That broke a couple of the
    shell-pasted preview snippets in LEARNINGS.md.
    """

    def test_construct_does_not_create_client(self, monkeypatch):
        # Pretend no key is set in the environment.
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
        from src.grounding import OpenAIEmbedder
        # Should NOT raise — client construction is deferred.
        emb = OpenAIEmbedder()
        assert emb._client is None


# -------------------------------- HashEmbedder ----------------------------


class TestHashEmbedder:
    def test_dimension(self):
        emb = HashEmbedder(dim=32)
        out = emb.embed(["hello world"])
        assert out.shape == (1, 32)

    def test_l2_normalised(self):
        out = HashEmbedder(dim=32).embed(["the quick brown fox", "lazy dog jumps"])
        for row in out:
            assert pytest.approx(float(np.linalg.norm(row)), abs=1e-5) == 1.0

    def test_similar_strings_have_high_cosine(self):
        emb = HashEmbedder(dim=128)
        a, b, c = emb.embed([
            "decision trees split on features to classify",
            "decision trees classify by splitting on features",
            "the chef prepared a lovely dinner",
        ])
        assert float(a @ b) > float(a @ c)


# -------------------------------- end-to-end ------------------------------


class TestHybridRetrievalSynthetic:
    """Exercises the full BM25+dense+RRF pipeline on hand-built chunks."""

    @pytest.fixture
    def retriever(self, tmp_path: Path) -> HybridRetriever:
        kb = _kb_from_paragraphs({
            "ch1.s1": [_para(0, "decision trees split nodes by feature thresholds; "
                                "a tree classifies new examples by walking branches.")],
            "ch1.s2": [_para(1, "support vector machines find a separating hyperplane "
                                "that maximises the margin between classes.")],
            "ch1.s3": [_para(2, "naive bayes assumes feature independence given the class "
                                "and applies bayes rule to estimate probabilities.")],
        })
        return HybridRetriever(kb, embedder=HashEmbedder(dim=64), cache_dir=tmp_path)

    def test_query_returns_relevant_chunk_first(self, retriever):
        results = retriever.search("how do decision trees classify examples?")
        assert results
        top = results[0]
        assert "decision trees" in top.chunk.text.lower()

    def test_search_respects_top_k(self, retriever):
        results = retriever.search("classification", top_k=2)
        assert len(results) <= 2

    def test_section_filter_restricts_results(self, retriever):
        # Query terms appear in the SVM chunk (s2); the filter must keep us
        # there even though the same query has weak signal in s1/s3.
        results = retriever.search("hyperplane margin", section_ids=["ch1.s2"])
        assert results
        assert all(r.chunk.section_id == "ch1.s2" for r in results)

    def test_section_filter_unknown_returns_empty(self, retriever):
        assert retriever.search("anything", section_ids=["nope.s99"]) == []

    def test_results_carry_per_index_diagnostics(self, retriever):
        results = retriever.search("decision trees")
        # At least one result was retrieved by BOTH indexes.
        assert any(r.bm25_rank is not None and r.dense_rank is not None for r in results)

    def test_scores_are_sorted_descending(self, retriever):
        results = retriever.search("classification")
        scores = [r.rrf_score for r in results]
        assert scores == sorted(scores, reverse=True)


# -------------------------------- cache -----------------------------------


class TestEmbeddingCache:
    def test_cache_round_trips(self, tmp_path: Path):
        kb = _kb_from_paragraphs({
            "ch1.s1": [_para(0, "a paragraph about apples and oranges")]
        })
        r1 = HybridRetriever(kb, embedder=HashEmbedder(dim=64), cache_dir=tmp_path)
        r1.ensure_indexed()
        # A cache file (.npz) and its sidecar (.json) now exist.
        files = sorted(p.name for p in tmp_path.iterdir())
        assert any(f.endswith(".npz") for f in files)
        assert any(f.endswith(".json") for f in files)

        # Build a fresh retriever — it should pick up the cached embeddings
        # rather than re-embedding.
        r2 = HybridRetriever(kb, embedder=HashEmbedder(dim=64), cache_dir=tmp_path)
        r2.ensure_indexed()
        assert r2._embeddings is not None
        assert r1._embeddings is not None
        np.testing.assert_array_equal(r1._embeddings, r2._embeddings)

    def test_cache_invalidated_when_chunks_change(self, tmp_path: Path):
        kb_a = _kb_from_paragraphs({"ch1.s1": [_para(0, "first version " * 4)]})
        HybridRetriever(kb_a, embedder=HashEmbedder(dim=64),
                        cache_dir=tmp_path).ensure_indexed()

        # Different chunks → different cache key → different file written.
        kb_b = _kb_from_paragraphs({
            "ch1.s1": [_para(0, "first version " * 4)],
            "ch1.s2": [_para(1, "extra section added " * 4)],
        })
        HybridRetriever(kb_b, embedder=HashEmbedder(dim=64),
                        cache_dir=tmp_path).ensure_indexed()
        npz_files = list(tmp_path.glob("*.npz"))
        assert len(npz_files) == 2


# -------------------------------- guards ----------------------------------


class TestGuards:
    def test_empty_kb_rejected(self):
        from src.textbook.schema import Textbook
        empty_kb = TextbookKnowledgeBase(
            textbook=Textbook(textbook_id="x", title="x", authors=[], edition=None,
                              source_format="pdf", parser_quality=1.0, chapters=[]),
            chunks=[],
        )
        with pytest.raises(ValueError, match="no chunks"):
            HybridRetriever(empty_kb, embedder=HashEmbedder(dim=8))


# -------------------------------- mini PDF (Layer 1) ----------------------


@pytest.mark.skipif(not FIXTURE.exists(), reason="mini_textbook.pdf fixture missing")
class TestRetrievalOnPdfFixture:
    """End-to-end on the labelled mini PDF — exercises the real ingest +
    chunk + retrieve pipeline with no API call."""

    def test_search_returns_results(self, tmp_path: Path):
        kb = TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        results = retriever.search("numbers and arithmetic operators")
        assert results
        # The fixture's two prose paragraphs about numbers/operators should
        # rank above the loops/conditionals ones.
        top_text = results[0].chunk.text.lower()
        assert "numbers" in top_text or "operators" in top_text


# -------------------------------- Han (Layer 2, optional) -----------------


@pytest.mark.skipif(not HAN_DIR.exists(), reason="Han chapter PDFs not present")
class TestRetrievalOnHan:
    """Real-data smoke. Uses HashEmbedder — no API. Proves the retriever
    keeps up at full-textbook scale (thousands of chunks)."""

    def test_returns_results_in_reasonable_time(self, tmp_path: Path):
        import time as _time
        kb = TextbookKnowledgeBase.from_path(HAN_DIR, textbook_id="han", title="External Textbook")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=128),
                                    cache_dir=tmp_path)
        retriever.ensure_indexed()
        t0 = _time.perf_counter()
        results = retriever.search("k-means clustering algorithm",
                                   top_k=DEFAULT_TOP_K)
        elapsed = _time.perf_counter() - t0
        assert results
        assert elapsed < 1.0  # numpy cosine on ~1k chunks should be sub-second

    def test_section_filter_narrows_results(self, tmp_path: Path):
        kb = TextbookKnowledgeBase.from_path(HAN_DIR, textbook_id="han", title="External Textbook")
        retriever = HybridRetriever(kb, embedder=HashEmbedder(dim=128),
                                    cache_dir=tmp_path)
        # Pick the first available section id from the loaded textbook.
        first_section = next(
            s.section_id for c in kb.textbook.chapters for s in c.sections
        )
        results = retriever.search("anything", section_ids=[first_section])
        assert all(r.chunk.section_id == first_section for r in results)


# -------------------------------- module constants ------------------------


def test_module_constants_sane():
    assert DEFAULT_TOP_K >= 1
    assert RRF_K > 0
    assert 0.0 <= COSINE_FLOOR <= 1.0
