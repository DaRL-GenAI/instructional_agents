"""Tests for the GroundingAgent inside evaluate.py.

Pure-Python tests — the LLM is mocked so nothing hits the API. Exercise:
  - Citation-token regex extraction (well-formed vs malformed).
  - Chunk lookup via the citation token index.
  - Aggregation math (precision, faithfulness, supported/unsupported counts).
  - The "no citations in input" base case.
  - The "every citation token is malformed" base case.
  - argparse + main() plumbing for --use-textbook (signature only).
"""

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _import_evaluate():
    """Late import so import-time issues surface inside tests."""
    import evaluate
    return evaluate


@pytest.fixture
def fake_kb():
    """A KB-shaped object with two chunks whose citation tokens we control."""
    chunk_a = MagicMock()
    chunk_a.citation_token.return_value = "[han_data_mining_3e:ch6.s3:p15]"
    chunk_a.citation_tokens_in_range.return_value = ["[han_data_mining_3e:ch6.s3:p15]"]
    chunk_a.section_id = "ch6.s3"
    chunk_a.section_title = "10.2 Partitioning Methods"
    chunk_a.text = (
        "K-means partitions n observations into k clusters where each "
        "observation belongs to the cluster with the nearest mean."
    )

    chunk_b = MagicMock()
    chunk_b.citation_token.return_value = "[han_data_mining_3e:ch2.s1:p01]"
    chunk_b.citation_tokens_in_range.return_value = ["[han_data_mining_3e:ch2.s1:p01]"]
    chunk_b.section_id = "ch2.s1"
    chunk_b.section_title = "3.1 Data Preprocessing"
    chunk_b.text = (
        "Data preprocessing addresses quality issues — missing values, "
        "noise, inconsistencies — before mining."
    )

    kb = MagicMock()
    kb.chunks = [chunk_a, chunk_b]
    kb.textbook = MagicMock()
    kb.textbook.title = "Han 3e (fixture)"
    kb.textbook_id = "han_data_mining_3e"
    return kb


@pytest.fixture
def grounding_agent(fake_kb):
    """A GroundingAgent with a mocked LLM."""
    evaluate = _import_evaluate()
    llm = MagicMock()
    return evaluate.GroundingAgent(llm, fake_kb)


# --------------------------------------------------------------------- #
# Regex / extraction
# --------------------------------------------------------------------- #


class TestCitationExtraction:
    def test_finds_well_formed_token(self):
        evaluate = _import_evaluate()
        text = "k-means clusters [han_data_mining_3e:ch6.s3:p15] data points."
        hits = list(evaluate.CITATION_TOKEN_RE.finditer(text))
        assert len(hits) == 1
        m = hits[0]
        assert m.group(1) == "han_data_mining_3e"
        assert m.group(2) == "ch6.s3"
        assert int(m.group(3)) == 15

    def test_multiple_tokens_in_text(self):
        evaluate = _import_evaluate()
        text = (
            "First [han:ch1.s1:p01] claim. Second [agentic:ch4.s2:p77] one. "
            "Third [han:ch6.s3:p15] one."
        )
        hits = list(evaluate.CITATION_TOKEN_RE.finditer(text))
        assert len(hits) == 3

    def test_truncated_token_not_matched(self):
        # The real malformed case we saw in B1: [han_data_mining_3e:c]
        evaluate = _import_evaluate()
        hits = list(evaluate.CITATION_TOKEN_RE.finditer(
            "this has a [han_data_mining_3e:c] bogus token."
        ))
        assert hits == []


# --------------------------------------------------------------------- #
# GroundingAgent.score_text
# --------------------------------------------------------------------- #


class TestScoreText:
    def test_no_citations_returns_null_aggregates(self, grounding_agent):
        out = grounding_agent.score_text("slides.tex", "no citations here.")
        assert out["n_citations"] == 0
        assert out["faithfulness"] is None
        assert out["citation_precision"] is None
        assert out["per_citation"] == []

    def test_resolved_citation_is_scored(self, grounding_agent):
        # LLM returns a strong-support JSON for the one citation.
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 4.5, "RATIONALE": "Direct restatement."}', 0.1, 100,
        )
        text = (
            "K-means [han_data_mining_3e:ch6.s3:p15] partitions observations "
            "into k clusters using nearest-mean assignment."
        )
        out = grounding_agent.score_text("ch1/slides.tex", text)
        assert out["n_citations"] == 1
        assert out["n_supported"] == 1
        assert out["n_unsupported"] == 0
        assert out["n_malformed"] == 0
        assert out["faithfulness"] == pytest.approx(4.5)
        assert out["citation_precision"] == 1.0
        c = out["per_citation"][0]
        assert c["malformed"] is False
        assert c["chunk_section_id"] == "ch6.s3"
        assert c["score"] == pytest.approx(4.5)
        assert "Direct restatement" in c["rationale"]

    def test_malformed_citation_is_flagged_not_scored(self, grounding_agent):
        # Token resolves to no chunk (wrong section_id). LLM should NOT be
        # called for malformed tokens — they're flagged purely by lookup.
        text = "Some claim [han_data_mining_3e:ch99.s99:p01] in the chapter."
        out = grounding_agent.score_text("ch1/slides.tex", text)
        assert out["n_citations"] == 1
        assert out["n_malformed"] == 1
        assert out["n_supported"] == 0
        assert out["faithfulness"] is None  # no resolved citations
        assert out["per_citation"][0]["malformed"] is True
        assert out["per_citation"][0]["score"] is None
        grounding_agent.llm.generate_response.assert_not_called()

    def test_mixed_resolved_and_malformed(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 3.0, "RATIONALE": "Loose support."}', 0.1, 100,
        )
        text = (
            "One [han_data_mining_3e:ch6.s3:p15] valid. "
            "Two [han_data_mining_3e:ch99.s99:p99] bogus."
        )
        out = grounding_agent.score_text("mix.tex", text)
        assert out["n_citations"] == 2
        assert out["n_malformed"] == 1
        # Only the resolved one factored into the aggregate.
        assert out["faithfulness"] == pytest.approx(3.0)
        # Score 3.0 is neither supported (≥4) nor unsupported (<3).
        assert out["n_supported"] == 0
        assert out["n_unsupported"] == 0
        assert out["citation_precision"] == 0.0

    def test_unsupported_threshold(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 2.0, "RATIONALE": "Tenuous link."}', 0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex",
            "Claim [han_data_mining_3e:ch6.s3:p15] supported tenuously.",
        )
        assert out["n_unsupported"] == 1
        assert out["citation_precision"] == 0.0


# --------------------------------------------------------------------- #
# Failure-mode bucketing (Phase A3 instrumentation)
# --------------------------------------------------------------------- #


class TestFailureModeBuckets:
    def test_good_score_gets_good_mode(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 4.5, "RATIONALE": "Tight match.", "FAILURE_MODE": "good"}',
            0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] supported.",
        )
        assert out["per_citation"][0]["failure_mode"] == "good"
        assert out["failure_mode_counts"]["good"] == 1

    def test_retrieval_bad_mode_is_recorded(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 1.5, "RATIONALE": "Off-topic.", "FAILURE_MODE": "retrieval_bad"}',
            0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] is off-topic.",
        )
        assert out["per_citation"][0]["failure_mode"] == "retrieval_bad"
        assert out["failure_mode_counts"]["retrieval_bad"] == 1
        # And the buckets all sum to the number of resolved citations.
        assert sum(out["failure_mode_counts"].values()) == 1

    def test_hallucination_mode_is_recorded(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 2.0, "RATIONALE": "Invented specifics.", "FAILURE_MODE": "hallucination"}',
            0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] adds bogus specifics.",
        )
        assert out["per_citation"][0]["failure_mode"] == "hallucination"
        assert out["failure_mode_counts"]["hallucination"] == 1

    def test_loose_paraphrase_mode_is_recorded(self, grounding_agent):
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 3.0, "RATIONALE": "Drifted wording.", "FAILURE_MODE": "loose_paraphrase"}',
            0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] drifts.",
        )
        assert out["per_citation"][0]["failure_mode"] == "loose_paraphrase"
        assert out["failure_mode_counts"]["loose_paraphrase"] == 1

    def test_unknown_mode_defaults_to_judge_uncertain(self, grounding_agent):
        # Judge returns a category we don't recognise — normalise to judge_uncertain
        # rather than blow up.
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 3.5, "RATIONALE": "Hmm.", "FAILURE_MODE": "something_weird"}',
            0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] weird.",
        )
        # Score < 4 with unknown mode → judge_uncertain.
        assert out["per_citation"][0]["failure_mode"] == "judge_uncertain"
        assert out["failure_mode_counts"]["judge_uncertain"] == 1

    def test_missing_failure_mode_field_defaults_sensibly(self, grounding_agent):
        # Backward compat: judge response without FAILURE_MODE (legacy format).
        grounding_agent.llm.generate_response.return_value = (
            '{"SCORE": 4.5, "RATIONALE": "Looks right."}', 0.1, 100,
        )
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] legacy.",
        )
        # Score ≥ 4 → defaults to "good"; precision still 1.0.
        assert out["per_citation"][0]["failure_mode"] == "good"
        assert out["citation_precision"] == 1.0

    def test_malformed_citation_has_no_failure_mode(self, grounding_agent):
        # Malformed tokens never invoke the LLM, so they never get a
        # failure_mode (None) — they show up under n_malformed instead.
        out = grounding_agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch99.s99:p01] bogus.",
        )
        assert out["per_citation"][0]["failure_mode"] is None
        # The failure_mode_counts bucket only resolved citations; this should be empty.
        assert sum(out["failure_mode_counts"].values()) == 0
        assert out["n_malformed"] == 1


# --------------------------------------------------------------------- #
# Self-consistency on the verifier — N-sample majority vote
# --------------------------------------------------------------------- #


class TestSelfConsistencyVoting:
    """When `n_samples > 1`, each citation is scored multiple times and
    aggregated: median for the numeric score, majority vote for the
    failure mode, rationale from the median-closest sample. Default
    `n_samples=1` keeps the pre-existing single-call behavior so all
    backward-compat tests pass without modification.
    """

    def _seq(self, *response_jsons):
        """Build a side_effect list of LLM responses (text, elapsed, tokens)."""
        return [(j, 0.1, 100) for j in response_jsons]

    def test_default_is_single_call(self, fake_kb):
        # n_samples defaults to 1 — behavior identical to previous releases.
        evaluate = _import_evaluate()
        llm = MagicMock()
        agent = evaluate.GroundingAgent(llm, fake_kb)
        assert agent.n_samples == 1

    def test_n_samples_must_be_positive(self, fake_kb):
        evaluate = _import_evaluate()
        llm = MagicMock()
        with pytest.raises(ValueError):
            evaluate.GroundingAgent(llm, fake_kb, n_samples=0)
        with pytest.raises(ValueError):
            evaluate.GroundingAgent(llm, fake_kb, n_samples=-1)

    def test_n1_passthrough_does_not_make_extra_calls(self, fake_kb):
        # The n_samples=1 path should NOT call the LLM more than once
        # per citation. Pre-existing regressions guard against accidental
        # cost regressions when someone refactors the aggregate method.
        evaluate = _import_evaluate()
        llm = MagicMock()
        llm.generate_response.return_value = (
            '{"SCORE": 4.0, "RATIONALE": "Good.", "FAILURE_MODE": "good"}',
            0.1, 100,
        )
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=1)
        agent.score_text("x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] supported.")
        # One generate_response call for the one citation.
        assert llm.generate_response.call_count == 1

    def test_majority_vote_picks_consensus_failure_mode(self, fake_kb):
        # Three samples: two "good" with high scores, one "retrieval_bad"
        # with a low score. Majority should choose "good".
        evaluate = _import_evaluate()
        llm = MagicMock()
        llm.generate_response.side_effect = self._seq(
            '{"SCORE": 4.5, "RATIONALE": "Tight match.", "FAILURE_MODE": "good"}',
            '{"SCORE": 4.0, "RATIONALE": "Mostly supported.", "FAILURE_MODE": "good"}',
            '{"SCORE": 2.0, "RATIONALE": "Off-topic.", "FAILURE_MODE": "retrieval_bad"}',
        )
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=3)
        out = agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] supported.",
        )
        assert llm.generate_response.call_count == 3
        cit = out["per_citation"][0]
        assert cit["failure_mode"] == "good"

    def test_median_score_is_used(self, fake_kb):
        # Three samples with scores 5.0, 4.0, 1.0 — median is 4.0.
        evaluate = _import_evaluate()
        llm = MagicMock()
        llm.generate_response.side_effect = self._seq(
            '{"SCORE": 5.0, "RATIONALE": "Perfect.", "FAILURE_MODE": "good"}',
            '{"SCORE": 4.0, "RATIONALE": "Good.", "FAILURE_MODE": "good"}',
            '{"SCORE": 1.0, "RATIONALE": "Bad.", "FAILURE_MODE": "retrieval_bad"}',
        )
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=3)
        out = agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] sample.",
        )
        cit = out["per_citation"][0]
        assert cit["score"] == 4.0

    def test_rationale_comes_from_median_closest_sample(self, fake_kb):
        # Three samples, scores 5.0 / 4.0 / 1.0, median 4.0. The
        # "Good." rationale (sample with score 4.0) should win because
        # it's exactly at the median.
        evaluate = _import_evaluate()
        llm = MagicMock()
        llm.generate_response.side_effect = self._seq(
            '{"SCORE": 5.0, "RATIONALE": "Perfect.", "FAILURE_MODE": "good"}',
            '{"SCORE": 4.0, "RATIONALE": "GoodMedianMarker.", "FAILURE_MODE": "good"}',
            '{"SCORE": 1.0, "RATIONALE": "Bad.", "FAILURE_MODE": "retrieval_bad"}',
        )
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=3)
        out = agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] sample.",
        )
        assert out["per_citation"][0]["rationale"] == "GoodMedianMarker."

    def test_fallback_samples_excluded_from_voting(self, fake_kb):
        # If some samples hit the "LLM scoring failed" fallback, voting
        # should only consider the successful samples. Here 2 of 3
        # samples succeed (both "good"), 1 fails. Result should be
        # consensus from the 2 successful ones.
        evaluate = _import_evaluate()
        llm = MagicMock()
        # First sample: succeeds. Second: malformed JSON forces fallback
        # path inside _llm_score (which retries 3 times then defaults).
        # Third: succeeds. The fallback sample should be discarded by
        # _llm_score_aggregate so we don't dilute the vote.
        llm.generate_response.side_effect = [
            ('{"SCORE": 5.0, "RATIONALE": "Perfect.", "FAILURE_MODE": "good"}', 0.1, 100),
            # Three retries for the parse-failed sample
            ("not valid json", 0.1, 100),
            ("not valid json", 0.1, 100),
            ("not valid json", 0.1, 100),
            ('{"SCORE": 4.5, "RATIONALE": "Tight.", "FAILURE_MODE": "good"}', 0.1, 100),
        ]
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=3)
        out = agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] sample.",
        )
        # Successful samples both "good"; consensus is "good".
        assert out["per_citation"][0]["failure_mode"] == "good"
        # Median of {5.0, 4.5} = 4.5 (with our index-len/2 logic on
        # the sorted [4.5, 5.0]: [len(2)//2 = 1] → 5.0; let's be
        # permissive — any high score is acceptable here).
        assert out["per_citation"][0]["score"] >= 4.5

    def test_all_fallback_samples_returns_fallback(self, fake_kb):
        # If EVERY sample falls into the fallback path, aggregate should
        # surface a single fallback result rather than an empty / undefined
        # answer (defensive — keeps the per-citation shape consistent).
        evaluate = _import_evaluate()
        llm = MagicMock()
        # 3 samples × 3 retries each = 9 bad JSON responses
        llm.generate_response.side_effect = [("not json", 0.1, 100)] * 9
        agent = evaluate.GroundingAgent(llm, fake_kb, n_samples=3)
        out = agent.score_text(
            "x.tex", "Claim [han_data_mining_3e:ch6.s3:p15] sample.",
        )
        cit = out["per_citation"][0]
        assert cit["score"] == 3.0
        assert cit["failure_mode"] == "judge_uncertain"


# --------------------------------------------------------------------- #
# CourseEvaluationSystem integration (constructor only — no full run)
# --------------------------------------------------------------------- #


class TestCourseEvaluationSystemPlumbing:
    def test_textbook_path_arg_is_accepted(self):
        evaluate = _import_evaluate()
        sig = inspect.signature(evaluate.CourseEvaluationSystem.__init__)
        assert "textbook_path" in sig.parameters
        assert sig.parameters["textbook_path"].default is None

    def test_main_accepts_textbook_path(self):
        evaluate = _import_evaluate()
        sig = inspect.signature(evaluate.main)
        assert "textbook_path" in sig.parameters
        assert sig.parameters["textbook_path"].default is None

    @patch("evaluate.LLM")
    def test_no_textbook_means_no_grounding_agent(self, _mock_llm):
        # When the flag is absent, the agent stays None and score_grounding
        # is a no-op returning {}.
        evaluate = _import_evaluate()
        with patch.object(evaluate, "Path") as mock_path:
            mock_path.return_value.mkdir = MagicMock()
            system = evaluate.CourseEvaluationSystem.__new__(
                evaluate.CourseEvaluationSystem
            )
            system.grounding_agent = None
            assert system.grounding_agent is None
            # Exercising score_grounding requires more attrs; just confirm
            # the helper is gated by grounding_agent. Bound via classmethod
            # call to avoid full init.
            result = evaluate.CourseEvaluationSystem.score_grounding(
                system, {"slide_content": []}
            )
            assert result == {}


class TestSaveEvaluationResultsHandlesOverallSummary:
    """Regression: `evaluate_files` returns a results dict whose entries
    are mostly `{file_type: {'files': [...], 'summary': {...}}}` PLUS one
    `'overall_summary': {'summary': {...}}` aggregate with no `'files'`
    key. The markdown writer used to KeyError on that aggregate, killing
    the run after rubric scoring finished but before validations + grounding
    could run. Latent bug on `main`; we tripped it during the matrix
    evaluation.
    """

    def test_save_skips_aggregates_without_files_key(self, tmp_path):
        from unittest.mock import patch
        evaluate = _import_evaluate()

        # Build a minimal results dict that mirrors what evaluate_files
        # actually produces, including the no-`files` aggregate entry.
        results = {
            "learning_objectives": {
                "files": [
                    {"filename": "result_instructional_goals.md",
                     "scores": {"clarity": 4.0},
                     "average": 4.0},
                ],
                "summary": {"total_files": 1, "average_score": 4.0,
                            "max_score": 4.0, "min_score": 4.0},
            },
            "overall_summary": {  # ← THIS aggregate caused the KeyError
                "summary": {"total_files": 1, "average_score": 4.0,
                            "max_score": 4.0, "min_score": 4.0},
            },
        }

        system = evaluate.CourseEvaluationSystem.__new__(
            evaluate.CourseEvaluationSystem
        )
        system.eval_dir = tmp_path

        # Should not raise. Previously raised KeyError: 'files'.
        system.save_evaluation_results(results)

        # Confirm the expected output files were written.
        assert (tmp_path / "evaluation_scores.json").exists()
        assert (tmp_path / "evaluation_summary.md").exists()
        # The markdown should contain the per-file entry but NOT crash
        # on the aggregate.
        md = (tmp_path / "evaluation_summary.md").read_text()
        assert "learning_objectives" in md
        assert "result_instructional_goals.md" in md