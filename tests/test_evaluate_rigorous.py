"""Tests for evaluate.py --rigorous opt-in measurement mode.

The default (non-rigorous) path must stay byte-identical to upstream: one judge
sample per metric, a silent 3.0 on parse failure, the original Perfect/Good/Poor
rubric bands, and no core_quality aggregate. Rigorous mode (opt-in) makes the
judge deterministic, takes the median of N samples, uses anchored bands, records
a null sentinel instead of 3.0, and emits a core_quality headline that excludes
metrics the grounded generator structurally cannot satisfy on saved artifacts.
"""

from __future__ import annotations

from typing import List

import evaluate
from evaluate import (
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
    score = agent.score_single_metric("slide_content", "f.tex", "body", "accuracy")
    return score, llm, agent


class TestDefaultPathUnchanged:
    def test_default_is_not_rigorous(self):
        assert EvaluationAgent(FakeLLM([])).rigorous is False

    def test_single_sample_returns_score(self):
        score, llm, _ = _score(['{"THOUGHT": "x", "SCORE": 4.0}'], rigorous=False)
        assert score == 4.0
        assert llm.calls == 1  # exactly one sample in the default path

    def test_parse_failure_defaults_to_3(self):
        # all 3 retries unparseable -> upstream silent 3.0 (never None)
        score, llm, _ = _score(["not json", "still not", "nope"], rigorous=False)
        assert score == 3.0
        assert llm.calls == 3  # the upstream 3-retry loop is preserved

    def test_default_prompt_uses_upstream_bands(self):
        _, llm, _ = _score(['{"SCORE": 3.0}'], rigorous=False)
        user_msg = llm.last_messages[1]["content"]
        assert "5.0: Perfect" in user_msg
        assert "Fully satisfies the criterion" not in user_msg


class TestRigorousScoring:
    def test_flag_propagates(self):
        assert EvaluationAgent(FakeLLM([]), rigorous=True).rigorous is True

    def test_median_of_n_samples(self):
        # three parseable samples 2,4,5 -> median 4; one LLM call per sample
        score, llm, _ = _score(
            ['{"SCORE": 2.0}', '{"SCORE": 4.0}', '{"SCORE": 5.0}'], rigorous=True
        )
        assert score == 4.0
        assert llm.calls == RIGOROUS_SAMPLES

    def test_all_fail_returns_none_sentinel(self):
        # every sample (and its retries) unparseable -> None, not 3.0
        score, _, _ = _score(["x"] * 20, rigorous=True)
        assert score is None

    def test_rigorous_prompt_uses_anchored_bands(self):
        _, llm, _ = _score(['{"SCORE": 3.0}'], rigorous=True)
        user_msg = llm.last_messages[1]["content"]
        assert "Fully satisfies the criterion" in user_msg
        assert "5.0: Perfect" not in user_msg


class TestSentinelFilteringInAggregates:
    def test_none_scores_excluded_from_averages(self):
        agent = EvaluationAgent(FakeLLM([]), rigorous=True)
        # stub scoring: attribution is a sentinel (None), every other metric 2.0
        def fake_score(file_type, filename, content, metric):
            return None if metric.startswith("attribution") else 2.0
        agent.score_single_metric = fake_score

        results = agent.evaluate_files(
            {"slide_content": [{"filename": "c1.tex", "content": "x"}]}
        )
        fr = results["slide_content"]["files"][0]
        assert fr["scores"]["attribution"] is None        # sentinel kept in the record
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
                    {"filename": "c1.tex", "scores": {"accuracy": 4.0, "attribution": 1.0}},
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
