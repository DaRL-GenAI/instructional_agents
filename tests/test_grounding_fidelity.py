"""Tests for the binary Grounding Fidelity aggregate (external-review Open #5).

The 1-5 rubric can't resolve grounding changes (judge central tendency buries a
real fix in 3.8 → 3.9). `aggregate_grounding_fidelity` reuses the ContentVerifier's
already-binary per-chapter reports (claims supported / unsupported) and rolls them
into one sharp, A/B-comparable percentage. Reads existing
`content_verification.json` files → zero eval-time LLM cost; returns None for a
vanilla run with no reports (so the default eval path is untouched).
"""

from __future__ import annotations

import json

from evaluate import aggregate_grounding_fidelity


def _write_report(exp_root, chapter, claims, flagged):
    d = exp_root / chapter
    d.mkdir(parents=True, exist_ok=True)
    (d / "content_verification.json").write_text(json.dumps({
        "chapter_id": chapter,
        "claims_checked": claims,
        "unsupported_claim_count": flagged,
        "summary": f"{claims - flagged}/{claims} claims supported",
    }), encoding="utf-8")


class TestAggregateGroundingFidelity:
    def test_aggregates_across_chapters(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        root = tmp_path / "exp" / "demo"
        _write_report(root, "chapter_1", 50, 9)
        _write_report(root, "chapter_2", 50, 5)
        _write_report(root, "chapter_3", 50, 2)
        gf = aggregate_grounding_fidelity("demo")
        assert gf["total_claims"] == 150
        assert gf["total_flagged"] == 16
        assert gf["fidelity_pct"] == round(100.0 * 134 / 150, 1)   # 89.3
        assert gf["chapters_scored"] == 3
        assert [c["chapter"] for c in gf["per_chapter"]] == [
            "chapter_1", "chapter_2", "chapter_3"]

    def test_none_when_no_reports(self, tmp_path, monkeypatch):
        # Vanilla / ungrounded run — no verification files → no metric, no-op.
        monkeypatch.chdir(tmp_path)
        (tmp_path / "exp" / "vanilla").mkdir(parents=True)
        assert aggregate_grounding_fidelity("vanilla") is None
        assert aggregate_grounding_fidelity("does_not_exist") is None

    def test_skips_zero_claim_and_failopen_reports(self, tmp_path, monkeypatch):
        # A chapter whose verifier found no claims (or failed open) must not
        # dilute the rate — only chapters with claims_checked > 0 count.
        monkeypatch.chdir(tmp_path)
        root = tmp_path / "exp" / "demo"
        _write_report(root, "chapter_1", 40, 4)
        _write_report(root, "chapter_2", 0, 0)          # no claims → skipped
        gf = aggregate_grounding_fidelity("demo")
        assert gf["total_claims"] == 40
        assert gf["chapters_scored"] == 1
        assert gf["fidelity_pct"] == 90.0

    def test_perfect_and_zero(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        root = tmp_path / "exp" / "perfect"
        _write_report(root, "chapter_1", 30, 0)
        assert aggregate_grounding_fidelity("perfect")["fidelity_pct"] == 100.0
        root2 = tmp_path / "exp" / "zero"
        _write_report(root2, "chapter_1", 20, 20)
        assert aggregate_grounding_fidelity("zero")["fidelity_pct"] == 0.0
