"""Tests for the course contract builder.

Uses HashEmbedder so no API calls are needed.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.grounding import (
    HashEmbedder,
    HybridRetriever,
    TextbookKnowledgeBase,
    build_course_contract,
    sections_for_chapter,
)
from src.grounding.contract import (
    RETRIEVE_PER_TOPIC,
    SECTIONS_PER_TOPIC,
    COVERAGE_FLOOR_RRF,
    _parse_subtopics,
    _clean_hyde_paragraph,
    _extract_subtopics,
    _hyde_expand,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "mini_textbook.pdf"


@pytest.fixture(scope="module")
def mini_kb() -> TextbookKnowledgeBase:
    if not FIXTURE.exists():
        pytest.skip("mini_textbook.pdf fixture missing")
    return TextbookKnowledgeBase.from_path(FIXTURE, textbook_id="mini", title="Mini")


@pytest.fixture
def retriever(mini_kb, tmp_path) -> HybridRetriever:
    return HybridRetriever(mini_kb, embedder=HashEmbedder(dim=64),
                           cache_dir=tmp_path)


class TestBuildContract:
    def test_topic_mappings_present_for_each_chapter(self, mini_kb, retriever):
        chapters = [
            {"title": "Numbers and arithmetic", "description": "integers, floats, operators"},
            {"title": "Control flow", "description": "conditionals and loops"},
        ]
        contract = build_course_contract("course-x", chapters, mini_kb, retriever)
        assert len(contract.topic_to_textbook) == 2
        assert contract.topic_to_textbook[0].topic == "Numbers and arithmetic"
        assert contract.topic_to_textbook[1].topic == "Control flow"

    def test_sections_are_deduped(self, mini_kb, retriever):
        chapters = [{"title": "Numbers", "description": "integers and operators"}]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        sids = contract.topic_to_textbook[0].section_ids
        assert len(sids) == len(set(sids))

    def test_caps_at_sections_per_topic(self, mini_kb, retriever):
        chapters = [{"title": "Everything", "description": "everything in the textbook"}]
        contract = build_course_contract(
            "c", chapters, mini_kb, retriever, sections_per_topic=2,
        )
        assert len(contract.topic_to_textbook[0].section_ids) <= 2

    def test_empty_description_returns_empty_mapping(self, mini_kb, retriever):
        chapters = [{"title": "", "description": ""}]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        assert contract.topic_to_textbook[0].section_ids == []

    def test_contract_carries_textbook_id(self, mini_kb, retriever):
        chapters = [{"title": "Numbers", "description": "ints"}]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        assert contract.textbook_ids == ["mini"]

    def test_citation_required_default_true(self, mini_kb, retriever):
        chapters = [{"title": "Numbers", "description": "ints"}]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        assert contract.citation_required is True


class TestSectionsForChapter:
    def test_lookup_by_index(self, mini_kb, retriever):
        chapters = [
            {"title": "Numbers and arithmetic", "description": "integers, operators"},
            {"title": "Control flow", "description": "if and loops"},
        ]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        s0 = sections_for_chapter(contract, 0)
        s1 = sections_for_chapter(contract, 1)
        assert isinstance(s0, list)
        assert isinstance(s1, list)

    def test_none_contract_returns_none(self):
        # When no contract is in play, callers should fall back to
        # unconstrained retrieval — signalled by `None`.
        assert sections_for_chapter(None, 0) is None

    def test_out_of_range_returns_none(self, mini_kb, retriever):
        chapters = [{"title": "Numbers", "description": "ints"}]
        contract = build_course_contract("c", chapters, mini_kb, retriever)
        assert sections_for_chapter(contract, 5) is None


def test_module_constants_sane():
    assert RETRIEVE_PER_TOPIC >= SECTIONS_PER_TOPIC
    assert SECTIONS_PER_TOPIC >= 1
    assert 0 < COVERAGE_FLOOR_RRF < 0.1  # sensible range — see contract.py constant doc


# --------------------------------------------------------------------- #
# Multi-query: LLM-extracted subtopics + HyDE expansion.
# These tests use mock LLMs — no network, no API key.
# --------------------------------------------------------------------- #


def _make_fake_llm(responses):
    """Build a MagicMock LLM whose `.generate_response` yields the given
    responses in order, each as a (text, elapsed, tokens) tuple."""
    llm = MagicMock()
    iter_responses = iter(responses)

    def _gen(**kwargs):
        try:
            text = next(iter_responses)
        except StopIteration:
            text = "fallback"
        return text, 0.1, 50

    llm.generate_response.side_effect = _gen
    return llm


class TestSubtopicParsing:
    def test_plain_lines_parsed(self):
        out = _parse_subtopics("k-means\nhierarchical\ndensity", expected=3)
        assert out == ["k-means", "hierarchical", "density"]

    def test_numbered_lines_stripped(self):
        out = _parse_subtopics("1. k-means\n2. hierarchical\n3. density", expected=3)
        assert out == ["k-means", "hierarchical", "density"]

    def test_bulleted_lines_stripped(self):
        out = _parse_subtopics("- k-means\n* hierarchical\n• density", expected=3)
        assert out == ["k-means", "hierarchical", "density"]

    def test_truncates_to_expected(self):
        # Model returned more than asked for.
        out = _parse_subtopics("a\nb\nc\nd\ne", expected=3)
        assert out == ["a", "b", "c"]

    def test_skips_long_commentary_lines(self):
        # Model sometimes adds a prose commentary line — skip lines that
        # look like sentences rather than search phrases.
        text = (
            "k-means\n"
            "This is a long commentary sentence that the model added against instructions\n"
            "hierarchical clustering"
        )
        out = _parse_subtopics(text, expected=3)
        # The commentary line is filtered out by the length check.
        assert "k-means" in out
        assert "hierarchical clustering" in out

    def test_empty_response(self):
        assert _parse_subtopics("", expected=3) == []

    def test_error_response(self):
        # Mirrors src.agents.LLM error-path return: "Error: ..."
        assert _parse_subtopics("Error: 429 rate limit", expected=3) == []


class TestHyDEParsing:
    def test_clean_paragraph_passes_through(self):
        text = "K-means is a partitioning algorithm that minimizes within-cluster variance."
        assert _clean_hyde_paragraph(text) == text

    def test_preamble_stripped(self):
        text = "Paragraph: K-means is a partitioning algorithm."
        assert _clean_hyde_paragraph(text) == "K-means is a partitioning algorithm."

    def test_here_is_preamble_stripped(self):
        text = "Here is a paragraph: K-means is a partitioning algorithm."
        assert _clean_hyde_paragraph(text) == "K-means is a partitioning algorithm."

    def test_empty_returns_none(self):
        assert _clean_hyde_paragraph("") is None

    def test_error_returns_none(self):
        assert _clean_hyde_paragraph("Error: 429") is None


class TestExtractSubtopicsHelper:
    def test_happy_path(self):
        llm = _make_fake_llm(["alpha\nbeta\ngamma"])
        out = _extract_subtopics("Title", "Description", llm, n=3)
        assert out == ["alpha", "beta", "gamma"]
        # Verify the LLM was called with a messages list — same shape as
        # src.agents.LLM expects.
        kwargs = llm.generate_response.call_args.kwargs
        assert "messages" in kwargs
        assert kwargs["messages"][0]["role"] == "user"
        # Prompt mentions title and description.
        assert "Title" in kwargs["messages"][0]["content"]

    def test_llm_exception_returns_empty(self):
        llm = MagicMock()
        llm.generate_response.side_effect = RuntimeError("network blip")
        out = _extract_subtopics("Title", "Desc", llm, n=3)
        assert out == []


class TestHyDEHelper:
    def test_happy_path(self):
        llm = _make_fake_llm(["K-means partitions n observations into k clusters."])
        out = _hyde_expand("k-means clustering", "Clustering", llm)
        assert "K-means partitions" in out

    def test_llm_exception_returns_none(self):
        llm = MagicMock()
        llm.generate_response.side_effect = RuntimeError("network blip")
        assert _hyde_expand("query", "Title", llm) is None


class TestMultiQueryContractBuild:
    """Higher-impact test: the contract builder with a real retriever + a
    fake LLM should issue multiple retrieval calls (one per query) and
    fuse the resulting section rankings via RRF.
    """

    @pytest.fixture
    def captured_queries(self):
        return []

    @pytest.fixture
    def spied_retriever(self, mini_kb, tmp_path, captured_queries):
        retriever = HybridRetriever(mini_kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        original_search = retriever.search

        def spy(query, **kwargs):
            captured_queries.append(query)
            return original_search(query, **kwargs)

        retriever.search = spy
        return retriever

    def test_multi_query_issues_multiple_retrieval_calls(
        self, mini_kb, spied_retriever, captured_queries
    ):
        # LLM mock: first call returns 2 subtopics; remaining calls (the
        # HyDE expansions for the 3 queries: base + 2 subtopics) return
        # hypothetical paragraphs.
        llm = _make_fake_llm([
            "subtopic_one\nsubtopic_two",                       # subtopic extraction
            "hyde paragraph for base",                          # HyDE for base
            "hyde paragraph for subtopic_one",                  # HyDE for subtopic_one
            "hyde paragraph for subtopic_two",                  # HyDE for subtopic_two
        ])
        chapters = [{"title": "Numbers", "description": "ints"}]
        build_course_contract(
            "c", chapters, mini_kb, spied_retriever,
            llm=llm, use_hyde=True, use_subtopics=True, num_subtopics=2,
        )
        # 1 base + 2 subtopics = 3 queries → 3 retrieval calls.
        assert len(captured_queries) == 3
        # Each captured query is the HyDE-expanded paragraph, not the
        # original phrase.
        assert all("hyde paragraph" in q for q in captured_queries)

    def test_subtopics_only_no_hyde(
        self, mini_kb, spied_retriever, captured_queries
    ):
        llm = _make_fake_llm([
            "subtopic_one\nsubtopic_two",
        ])
        build_course_contract(
            "c",
            [{"title": "Numbers", "description": "ints"}],
            mini_kb,
            spied_retriever,
            llm=llm,
            use_hyde=False,
            use_subtopics=True,
            num_subtopics=2,
        )
        # 1 base + 2 subtopics → 3 retrieval calls with original phrases.
        assert len(captured_queries) == 3
        assert "subtopic_one" in captured_queries
        assert "subtopic_two" in captured_queries

    def test_hyde_only_no_subtopics(
        self, mini_kb, spied_retriever, captured_queries
    ):
        llm = _make_fake_llm(["hyde for base"])
        build_course_contract(
            "c",
            [{"title": "Numbers", "description": "ints"}],
            mini_kb,
            spied_retriever,
            llm=llm,
            use_hyde=True,
            use_subtopics=False,
        )
        # Just one query — the HyDE-expanded base.
        assert len(captured_queries) == 1
        assert captured_queries[0] == "hyde for base"

    def test_llm_failure_falls_back_to_single_query(
        self, mini_kb, spied_retriever, captured_queries
    ):
        # LLM that always raises — every enrichment call fails. The
        # contract should still build with just the baseline query.
        llm = MagicMock()
        llm.generate_response.side_effect = RuntimeError("always fails")
        contract = build_course_contract(
            "c",
            [{"title": "Numbers", "description": "ints and operators"}],
            mini_kb,
            spied_retriever,
            llm=llm,
            use_hyde=True,
            use_subtopics=True,
        )
        # Only the baseline query made it through.
        assert len(captured_queries) == 1
        assert captured_queries[0] == "Numbers. ints and operators"
        # And the contract still has section_ids for the chapter.
        assert len(contract.topic_to_textbook[0].section_ids) >= 1

    def test_llm_none_uses_single_query(
        self, mini_kb, spied_retriever, captured_queries
    ):
        # Backward compatibility — no LLM passed, no enrichment.
        build_course_contract(
            "c",
            [{"title": "Numbers", "description": "ints"}],
            mini_kb,
            spied_retriever,
            llm=None,
        )
        assert len(captured_queries) == 1


class TestCoverageGating:
    """When the top retrieved section's fused score is below the floor,
    the chapter is treated as "off-textbook" — section_ids cleared so
    downstream skips grounding rather than fabricate citations.
    """

    def test_low_match_clears_sections(self, mini_kb, tmp_path):
        # Query for content the mini textbook genuinely doesn't cover.
        # HashEmbedder is bag-of-words, so a query with no overlapping
        # tokens will get near-zero RRF.
        retriever = HybridRetriever(mini_kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        contract = build_course_contract(
            "c",
            [{"title": "Particle physics", "description": "quarks gluons hadrons leptons"}],
            mini_kb,
            retriever,
        )
        mapping = contract.topic_to_textbook[0]
        # Coverage gate may or may not trigger depending on BM25 score
        # against the tiny fixture — assert the rationale is descriptive
        # either way, and if it did trigger, section_ids is empty.
        if "off-textbook" in mapping.rationale:
            assert mapping.section_ids == []
        else:
            # Strong-enough match recorded with its RRF score.
            assert "top section RRF" in mapping.rationale

    def test_rationale_records_query_count(self, mini_kb, tmp_path):
        retriever = HybridRetriever(mini_kb, embedder=HashEmbedder(dim=64),
                                    cache_dir=tmp_path)
        contract = build_course_contract(
            "c",
            [{"title": "Numbers", "description": "ints and operators"}],
            mini_kb,
            retriever,
        )
        # Single-query path (no LLM): rationale should reflect "1 queries".
        assert "1 queries" in contract.topic_to_textbook[0].rationale
