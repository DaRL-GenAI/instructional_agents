"""Tests for v7 Step 9 — WriteTimeVerifier (LLM YES/NO citation gate)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock

from src.grounding.write_time_verifier import WriteTimeVerifier


@dataclass
class _StubChunk:
    section_id: str
    page_start: int = 1
    page_end: int = 1
    textbook_id: str = "han"
    text: str = "passage content"

    def citation_token(self) -> str:
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        return [
            f"[{self.textbook_id}:{self.section_id}:p{p:02d}]"
            for p in range(self.page_start, self.page_end + 1)
        ]


class _StubKB:
    def __init__(self, chunks):
        self.chunks = chunks


def _stub_llm(yes_then_no=None, all_yes=False, all_no=False):
    """Build a stub LLM whose generate_response returns YES or NO.

    Production signature: llm.generate_response(messages, stream) → tuple.
    The MagicMock side_effect/return_value covers both positional and
    keyword call shapes.
    """
    llm = MagicMock()
    if all_yes:
        llm.generate_response.return_value = ("YES", 0.1, 50)
    elif all_no:
        llm.generate_response.return_value = ("NO", 0.1, 50)
    elif yes_then_no:
        llm.generate_response.side_effect = [
            (ans, 0.1, 50) for ans in yes_then_no
        ]
    return llm


class TestVerifyOne:
    def test_yes_keeps_citation(self):
        kb = _StubKB([_StubChunk("ch1.s1", text="K-means clustering")])
        llm = _stub_llm(all_yes=True)
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = "K-means partitions data [han:ch1.s1:p01]."
        out = v.strip_unsupported(text)
        assert "[han:ch1.s1:p01]" in out

    def test_no_strips_citation(self):
        kb = _StubKB([_StubChunk("ch1.s1", text="Database normalization")])
        llm = _stub_llm(all_no=True)
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = "K-means partitions data [han:ch1.s1:p01]."
        out = v.strip_unsupported(text)
        assert "[han:ch1.s1:p01]" not in out
        assert "K-means partitions data" in out

    def test_fail_open_on_llm_error(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        llm = MagicMock()
        llm.generate_response.side_effect = RuntimeError("API down")
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = "Claim [han:ch1.s1:p01]."
        out = v.strip_unsupported(text)
        # Fail-open: keep citation on error
        assert "[han:ch1.s1:p01]" in out
        assert v.calls_error == 1


class TestMixedYesNo:
    def test_strips_only_no_citations(self):
        kb = _StubKB([
            _StubChunk("ch1.s1", text="K-means"),
            _StubChunk("ch2.s2", text="Database normalization"),
        ])
        # First call YES (ch1.s1), second NO (ch2.s2)
        llm = _stub_llm(yes_then_no=["YES", "NO"])
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = (
            "K-means partitions data [han:ch1.s1:p01]. "
            "Centroids update each iteration [han:ch2.s2:p01]."
        )
        out = v.strip_unsupported(text)
        assert "[han:ch1.s1:p01]" in out
        assert "[han:ch2.s2:p01]" not in out


class TestCaching:
    def test_repeated_same_claim_only_calls_once(self):
        kb = _StubKB([_StubChunk("ch1.s1", text="K-means")])
        llm = _stub_llm(all_yes=True)
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = (
            "Same claim [han:ch1.s1:p01]. "
            "Same claim [han:ch1.s1:p01]."
        )
        v.strip_unsupported(text)
        # Cache hit on second occurrence — only ONE LLM call
        assert v.calls_made == 1


class TestEdgeCases:
    def test_empty_text_no_op(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        v = WriteTimeVerifier(kb=kb, llm=MagicMock())
        assert v.strip_unsupported("") == ""
        assert v.strip_unsupported(None) is None

    def test_no_llm_no_op(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        v = WriteTimeVerifier(kb=kb, llm=None)
        text = "Claim [han:ch1.s1:p01]."
        assert v.strip_unsupported(text) == text

    def test_unknown_token_left_alone(self):
        kb = _StubKB([_StubChunk("ch1.s1")])
        llm = _stub_llm(all_no=True)  # would strip if processed
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = "Claim [han:ch99.s99:p01]."
        out = v.strip_unsupported(text)
        # Unknown token — _verify_one returns True (let malformed-strip handle)
        assert "[han:ch99.s99:p01]" in out


class TestReport:
    def test_report_counts(self):
        kb = _StubKB([
            _StubChunk("ch1.s1", text="K-means"),
            _StubChunk("ch2.s2", text="Other"),
        ])
        llm = _stub_llm(yes_then_no=["YES", "NO"])
        v = WriteTimeVerifier(kb=kb, llm=llm)
        text = "A [han:ch1.s1:p01]. B [han:ch2.s2:p01]."
        v.strip_unsupported(text)
        report = v.report()
        assert "2 LLM calls" in report
        assert "YES=1" in report
        assert "NO=1" in report
        assert "stripped 1" in report
