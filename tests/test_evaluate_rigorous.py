"""Tests for ``src/evaluate.py --rigorous`` opt-in measurement mode.

The default (non-rigorous) path must stay unchanged: one judge sample per
metric, a silent 3.0 on parse failure, the original Perfect/Good/Poor rubric
bands, and no core_quality aggregate. Rigorous mode (opt-in) makes the judge
deterministic, takes the median of N samples, uses anchored bands, records a
null sentinel instead of 3.0, and emits a core_quality headline that excludes
metrics the grounded generator structurally cannot satisfy on saved artifacts.

Scores are stored as ``{"score": float | None, "thought": str}`` records.
"""

from __future__ import annotations

from typing import List

import src.evaluate as evaluate
from src.evaluate import (
    EvaluationAgent,
    CourseEvaluationSystem,
    RIGOROUS_SAMPLES,
    RIGOROUS_SEED,
    RIGOROUS_TEMPERATURE,
    CORE_QUALITY_EXCLUDED_METRICS,
)


class FakeLLM:
    """Duck-typed LLM: returns queued responses, records every call."""

    def __init__(self, responses: List[str]):
        self._responses = list(responses)
        self.calls = 0
        self.last_messages = None

    def generate_response(self, messages, stream=False):
        self.calls += 1
        self.last_messages = messages
        resp = self._responses.pop(0) if self._responses else '{"SCORE": 3.0}'
        return resp, 0.0, 0


def _score(resp_list, rigorous):
    llm = FakeLLM(resp_list)
    agent = EvaluationAgent(llm, rigorous=rigorous)
    score, thought = agent.score_single_metric("slide_content", "f.tex", "body", "accuracy")
    return score, thought, llm


class TestDefaultPathUnchanged:
    def test_default_is_not_rigorous(self):
        assert EvaluationAgent(FakeLLM([])).rigorous is False

    def test_single_sample_returns_score_and_thought(self):
        score, thought, llm = _score(['{"THOUGHT": "x", "SCORE": 4.0}'], rigorous=False)
        assert score == 4.0
        assert thought == "x"
        assert llm.calls == 1  # exactly one sample in the default path

    def test_parse_failure_defaults_to_3(self):
        # all 3 retries unparseable -> silent 3.0 (never None)
        score, thought, llm = _score(["not json", "still not", "nope"], rigorous=False)
        assert score == 3.0
        assert thought == ""
        assert llm.calls == 3  # the 3-retry loop is preserved

    def test_default_prompt_uses_original_bands(self):
        _, _, llm = _score(['{"SCORE": 3.0}'], rigorous=False)
        user_msg = llm.last_messages[1]["content"]
        assert "5.0: Perfect" in user_msg
        assert "Fully satisfies the criterion" not in user_msg


class TestRigorousScoring:
    def test_flag_propagates(self):
        assert EvaluationAgent(FakeLLM([]), rigorous=True).rigorous is True

    def test_median_of_n_samples(self):
        # three parseable samples 2,4,5 -> median 4; one LLM call per sample
        score, thought, llm = _score(
            ['{"SCORE": 2.0, "THOUGHT": "low"}', '{"SCORE": 4.0, "THOUGHT": "mid"}',
             '{"SCORE": 5.0, "THOUGHT": "high"}'],
            rigorous=True,
        )
        assert score == 4.0
        assert thought == "mid"  # rationale of the sample closest to the median
        assert llm.calls == RIGOROUS_SAMPLES

    def test_all_fail_returns_none_sentinel(self):
        # every sample (and its retries) unparseable -> None, not 3.0
        score, thought, _ = _score(["x"] * 20, rigorous=True)
        assert score is None
        assert thought == ""

    def test_rigorous_prompt_uses_anchored_bands(self):
        _, _, llm = _score(['{"SCORE": 3.0}'], rigorous=True)
        user_msg = llm.last_messages[1]["content"]
        assert "Fully satisfies the criterion" in user_msg
        assert "5.0: Perfect" not in user_msg


class TestSentinelFilteringInAggregates:
    def test_none_scores_excluded_from_averages(self):
        agent = EvaluationAgent(FakeLLM([]), rigorous=True)
        # stub scoring: attribution is a sentinel (None), every other metric 2.0
        def fake_score(file_type, filename, content, metric):
            return (None, "") if metric.startswith("attribution") else (2.0, "ok")
        agent.score_single_metric = fake_score

        results = agent.evaluate_files(
            {"slide_content": [{"filename": "c1.tex", "content": "x"}]}
        )
        fr = results["slide_content"]["files"][0]
        assert fr["scores"]["attribution"] == {"score": None, "thought": ""}  # sentinel kept in the record
        assert fr["average"] == 2.0                        # average over numeric only
        assert results["slide_content"]["summary"]["min_score"] == 2.0
        assert results["overall_summary"]["summary"]["average_score"] == 2.0


class TestCoreQualityAggregate:
    def _bare_system(self):
        # _with_core_quality uses only its argument + the module constant
        return CourseEvaluationSystem.__new__(CourseEvaluationSystem)

    def test_core_quality_excludes_structural_metrics(self):
        results = {
            "slide_content": {
                "files": [
                    {
                        "filename": "c1.tex",
                        "scores": {
                            "accuracy": {"score": 4.0, "thought": ""},
                            "attribution": {"score": 1.0, "thought": ""},
                        },
                    },
                ],
                "summary": {"total_files": 1, "average_score": 2.5, "max_score": 4.0, "min_score": 1.0},
            },
            "overall_summary": {
                "summary": {"total_files": 1, "average_score": 2.5, "max_score": 4.0, "min_score": 1.0}
            },
        }
        out = self._bare_system()._with_core_quality(results)
        assert "core_quality" in out
        # attribution (1.0) excluded -> only accuracy 4.0 contributes
        assert out["core_quality"]["summary"]["average_score"] == 4.0
        assert "attribution" in out["core_quality"]["summary"]["excluded_metrics"]

    def test_excluded_set_covers_known_structural_floors(self):
        assert {"attribution", "availability", "accessibility", "transparency_of_policies"} <= CORE_QUALITY_EXCLUDED_METRICS


class TestSaveResultsSkipsAggregateEntries:
    def test_markdown_writer_ignores_entries_without_files(self, tmp_path):
        # overall_summary / core_quality have no 'files' key; the markdown
        # writer must skip them instead of raising KeyError.
        system = CourseEvaluationSystem.__new__(CourseEvaluationSystem)
        system.rigorous = True
        system.eval_dir = tmp_path
        results = {
            "syllabus": {
                "files": [{"filename": "s.md", "average": 3.0,
                           "scores": {"coherence": {"score": 3.0, "thought": "t"}}}],
                "summary": {"total_files": 1, "average_score": 3.0, "max_score": 3.0, "min_score": 3.0},
            },
            "overall_summary": {
                "summary": {"total_files": 1, "average_score": 3.0, "max_score": 3.0, "min_score": 3.0}
            },
        }
        system.save_evaluation_results(results)
        md = (tmp_path / "evaluation_summary.md").read_text(encoding="utf-8")
        assert "## syllabus" in md
        assert "## overall_summary" not in md
        assert "## core_quality" not in md
        assert "core_quality" in results  # added by rigorous mode


class TestDeterminismWiring:
    def _record_llm(self, monkeypatch):
        captured = {}

        class RecLLM:
            def __init__(self, model_name="gpt-4o-mini", seed=None, temperature=None):
                captured["seed"] = seed
                captured["temperature"] = temperature

        monkeypatch.setattr(evaluate, "LLM", RecLLM)
        return captured

    def test_rigorous_builds_seeded_zero_temp_judge(self, monkeypatch, tmp_path):
        captured = self._record_llm(monkeypatch)
        monkeypatch.chdir(tmp_path)
        CourseEvaluationSystem("gpt-4o-mini", "unit_exp", rigorous=True)
        assert captured["seed"] == RIGOROUS_SEED
        assert captured["temperature"] == RIGOROUS_TEMPERATURE

    def test_default_builds_plain_judge(self, monkeypatch, tmp_path):
        captured = self._record_llm(monkeypatch)
        monkeypatch.chdir(tmp_path)
        CourseEvaluationSystem("gpt-4o-mini", "unit_exp", rigorous=False)
        # default path: LLM(model_name=model_name) -> seed/temperature left at defaults
        assert captured["seed"] is None
        assert captured["temperature"] is None
