"""Verifier: a judge that never answers (API error echoed as text) yields a
"judge failed" receipt, never a pass; evidence longer than the shard limit is
judged in pieces and the verdicts merged (supported if any shard anchors a
quote, flagged only if every shard flags)."""

from __future__ import annotations

import json

from src.grounding import content_verifier as cv
from src.grounding.content_verifier import ContentVerifier, _shard_evidence

DECK = r"""
\begin{frame}[fragile]
\frametitle{Two facts}
Alpha systems store the alpha value in a dedicated field. Beta notes are free text written by clinicians.
\end{frame}
"""


class _LLM:
    """Scripted judge: supports a claim only when its keyword is in the evidence."""
    def __init__(self, error=False):
        self.error = error
        self.calls = 0

    def generate_response(self, messages, stream=False):
        self.calls += 1
        if self.error:
            return "Error: Error code: 400 - context_length_exceeded", 0.0, 0
        user = messages[-1]["content"]
        evidence = user.split("CLAIMS:")[0].replace("EVIDENCE:", "").strip()
        claims = [l.split(". ", 1)[1] for l in user.split("CLAIMS:")[1].split("\n") if l[:1].isdigit()]
        out = []
        for i, c in enumerate(claims, 1):
            key = c.split()[0].lower()           # "alpha" / "beta"
            if key in evidence.lower():
                quote = next(p for p in evidence.split("\n\n") if key in p.lower()).strip()[:60]
                out.append({"index": i, "verdict": "supported", "quote": quote})
            else:
                out.append({"index": i, "verdict": "unsupported", "reason": "not in this shard"})
        return json.dumps({"claims": out}), 0.0, 0


def _verifier(llm):
    v = ContentVerifier.__new__(ContentVerifier)
    v.llm = llm
    v.model = "scripted"
    v.retriever = None
    return v


class TestJudgeError:
    def test_error_reply_is_not_a_pass(self):
        r = _verifier(_LLM(error=True)).verify_chapter(
            "c1", "T", {"slides": DECK}, ["s1"], full_source_text="some evidence")
        assert r["judge_protocol"] == "judge_error"
        assert r["supported_claims"] == [] and r["flagged_claims"] == []
        assert r["claims_unverified"] == 2
        assert r["summary"].startswith("judge failed: 0/2")
        assert "context_length_exceeded" in r["error"]


class TestSharding:
    def test_shard_split_respects_paragraphs(self):
        ev = "\n\n".join(["p" * 100] * 10)
        shards = _shard_evidence(ev, 350)
        assert len(shards) == 4 and all(len(s) <= 350 for s in shards)
        assert "\n\n".join(shards) == ev

    def test_claims_merge_across_shards(self, monkeypatch):
        monkeypatch.setattr(cv, "_EVIDENCE_SHARD_CHARS", 120)
        shard_a = "Alpha systems keep the alpha value in a field. " * 2
        shard_b = "Beta notes are free text written by clinicians. " * 2
        llm = _LLM()
        r = _verifier(llm).verify_chapter(
            "c1", "T", {"slides": DECK}, ["s1"], full_source_text=shard_a + "\n\n" + shard_b)
        assert r["evidence_shards"] == 2
        assert sorted(s["index"] for s in r["supported_claims"]) == [1, 2]
        assert r["flagged_claims"] == []
        assert {s["index"]: s["shard"] for s in r["supported_claims"]} == {1: 1, 2: 2}
        assert "[2 evidence shards]" in r["summary"]
        assert llm.calls == 2

    def test_flag_only_when_every_shard_flags(self, monkeypatch):
        monkeypatch.setattr(cv, "_EVIDENCE_SHARD_CHARS", 120)
        ev = ("Alpha systems keep the alpha value in a field. " * 2) + "\n\n" + ("Nothing relevant here at all. " * 3)
        r = _verifier(_LLM()).verify_chapter(
            "c1", "T", {"slides": DECK}, ["s1"], full_source_text=ev)
        assert [s["index"] for s in r["supported_claims"]] == [1]
        assert [f["index"] for f in r["flagged_claims"]] == [2]
        assert r["summary"].startswith("1/2 claims supported (1 flagged) [2 evidence shards]")

    def test_small_evidence_single_call_unchanged(self):
        llm = _LLM()
        r = _verifier(llm).verify_chapter(
            "c1", "T", {"slides": DECK}, ["s1"], full_source_text="Alpha and beta both appear here.")
        assert "evidence_shards" not in r and llm.calls == 1
