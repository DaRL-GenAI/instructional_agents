"""Tests for the advisory ContentVerifier (citation-free grounding signal).

Locks the contract the slides.py hook will depend on: claim segmentation that
skips figure/visual-marker lines, defensive JSON parsing, fail-open on any LLM
error, no mutation of the artifacts, and construction without a retriever
(vanilla path never invokes it, but it must import + construct cleanly).
"""

from __future__ import annotations

from src.grounding.content_verifier import (
    ContentVerifier,
    _segment_claims,
    _parse_json,
    report_line,
)


class _FakeLLM:
    def __init__(self, resp=None, raise_=False):
        self._resp = resp
        self._raise = raise_
        self.messages = None

    def generate_response(self, messages, stream=False):
        self.messages = messages
        if self._raise:
            raise RuntimeError("boom")
        return self._resp, 0.0, 0


class TestSegmentClaims:
    def test_splits_items_and_sentences(self):
        text = ("\\item K-Means partitions data into k clusters. "
                "\\item DBSCAN finds dense regions of arbitrary shape.")
        claims = _segment_claims(text)
        assert any("K-Means partitions" in c for c in claims)
        assert any("DBSCAN finds" in c for c in claims)

    def test_skips_figure_and_visual_marker_lines(self):
        text = (
            "K-Means clusters data into k groups of points.\n"
            "\\includegraphics[width=0.5\\textwidth]{/x/fig.png}\n"
            "[IMAGE_PATH: /x/fig.png]\n"
            "[LATEX: x^2 + y^2]\n"
        )
        claims = _segment_claims(text)
        assert all("includegraphics" not in c for c in claims)
        assert all("IMAGE_PATH" not in c and "LATEX" not in c for c in claims)
        assert any("K-Means" in c for c in claims)

    def test_drops_short_fragments(self):
        assert _segment_claims("K-Means.") == []          # < 4 words

    def test_caps_claims(self):
        text = "\n".join(
            f"This is claim number {i} about clustering methods." for i in range(100)
        )
        assert len(_segment_claims(text)) <= 50


class TestParseJson:
    def test_wellformed(self):
        assert _parse_json('{"unsupported": []}') == {"unsupported": []}

    def test_brace_wrapped(self):
        out = _parse_json('Here you go: {"unsupported": [{"index": 1}]} done')
        assert out["unsupported"][0]["index"] == 1

    def test_garbage_and_empty(self):
        assert _parse_json("not json at all") == {}
        assert _parse_json("") == {}


class TestVerifyChapter:
    def test_flags_unsupported(self):
        llm = _FakeLLM(resp='{"unsupported":[{"index":2,"claim":"x","reason":"drift"}]}')
        v = ContentVerifier(retriever=None, llm=llm)
        rep = v.verify_chapter(
            "ch1", "Cluster Analysis",
            {"slides": "K-Means partitions data into k clusters. "
                       "PCA reduces dimensions of the dataset."},
            None,
        )
        assert rep["claims_checked"] == 2
        assert rep["unsupported_claim_count"] == 1
        assert "1/2 claims supported" in rep["summary"]
        assert "error" not in rep

    def test_fail_open_on_llm_error(self):
        v = ContentVerifier(retriever=None, llm=_FakeLLM(raise_=True))
        rep = v.verify_chapter(
            "ch1", "T", {"slides": "K-Means partitions data into clusters of points."}, None
        )
        assert rep["unsupported_claim_count"] == 0
        assert "error" in rep                             # fail-open recorded

    def test_no_claims_skips_llm(self):
        v = ContentVerifier(retriever=None, llm=_FakeLLM(raise_=True))  # would raise if called
        rep = v.verify_chapter("ch1", "T", {"slides": "\\includegraphics{/x/a.png}"}, None)
        assert rep["claims_checked"] == 0
        assert "error" not in rep                         # LLM never called

    def test_never_mutates_artifacts(self):
        v = ContentVerifier(retriever=None, llm=_FakeLLM(resp='{"unsupported":[]}'))
        artifacts = {"slides": "K-Means partitions data into k clusters of points."}
        before = dict(artifacts)
        v.verify_chapter("ch1", "T", artifacts, None)
        assert artifacts == before

    def test_constructs_with_retriever_none(self):
        assert ContentVerifier(retriever=None, llm=_FakeLLM()) is not None

    def test_uses_writer_evidence_when_provided(self):
        # The exact evidence the writer was given is what the verifier checks
        # against — not a fresh chapter-title retrieval.
        llm = _FakeLLM(resp='{"unsupported":[]}')
        v = ContentVerifier(retriever=None, llm=llm)
        v.verify_chapter(
            "ch1", "Cluster Analysis",
            {"slides": "K-Means partitions data into k clusters of points."},
            None,
            writer_evidence="[E1] WRITER_EVIDENCE_MARKER the textbook passage.",
        )
        user_msg = llm.messages[-1]["content"]
        assert "WRITER_EVIDENCE_MARKER" in user_msg


class TestReportLine:
    def test_line_format(self):
        assert "content-verify" in report_line({"chapter_id": "ch1", "summary": "3/4 supported"})
        assert "ERROR" in report_line({"chapter_id": "ch1", "summary": "x", "error": "Boom"})
