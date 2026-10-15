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
        assert any("WRITER_EVIDENCE_MARKER" in m["content"]
                   for m in llm.messages)


class TestSegmentationAuditFixes:
    """Fixes from the 2026-08-29 ch1-4 bench audit."""

    def test_textbf_argument_is_kept(self):
        claims = _segment_claims(
            "The \\textbf{mode} is the value that appears most frequently "
            "in the data set.")
        assert any("The mode is the value" in c for c in claims)

    def test_beamer_template_junk_dropped(self):
        text = ("[wd=.3\\paperwidth,ht=2.25ex,dp=1ex,center]author in "
                "head/foot%\n"
                "K-Means partitions data into k clusters of points.")
        claims = _segment_claims(text)
        assert all("head/foot" not in c and "wd=" not in c for c in claims)
        assert any("K-Means" in c for c in claims)

    def test_participants_will_is_meta_discourse(self):
        assert _segment_claims(
            "Participants will learn to compute statistical measures.") == []

    def test_summarize_stub_is_imperative(self):
        assert _segment_claims(
            "Summarize the location of data values in sets.") == []

    def test_latex_comment_lines_dropped(self):
        claims = _segment_claims(
            "% Turn off navigation symbols entirely now\n"
            "K-Means partitions data into k clusters of points.")
        assert all("navigation symbols" not in c for c in claims)
        assert any("K-Means" in c for c in claims)

    def test_the_lecture_will_is_meta_discourse(self):
        assert _segment_claims(
            "The lecture will cover data structures for computations.") == []


class _SeqLLM:
    """Fake LLM returning a sequence of responses (last one repeats)."""

    def __init__(self, resps):
        self._resps = list(resps)
        self.calls = []

    def generate_response(self, messages, stream=False):
        self.calls.append(messages)
        resp = self._resps.pop(0) if len(self._resps) > 1 else self._resps[0]
        return resp, 0.0, 0


_EVIDENCE = ("[E1] K-Means partitions data into k clusters by minimizing "
             "within-cluster variance. PCA reduces dimensions of the dataset "
             "using eigenvectors.")
_SLIDES = ("K-Means partitions data into k clusters. "
           "PCA reduces dimensions of the dataset.")


def _verify(resp_or_llm, slides=_SLIDES):
    llm = (resp_or_llm if hasattr(resp_or_llm, "generate_response")
           else _SeqLLM([resp_or_llm]))
    v = ContentVerifier(retriever=None, llm=llm)
    return v.verify_chapter("ch1", "Cluster Analysis", {"slides": slides},
                            None, writer_evidence=_EVIDENCE)


class TestQuoteAnchoredJudging:
    def test_anchored_pass_counts_supported(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"K-Means partitions data into k clusters"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["judge_protocol"] == "quote_anchored_v1"
        assert rep["unsupported_claim_count"] == 0
        assert len(rep["supported_claims"]) == 2
        assert "quote" in rep["supported_claims"][0]

    def test_fabricated_quote_is_flagged_unanchored(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"K-Means was invented in 1967 by MacQueen"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["unsupported_claim_count"] == 1
        assert rep["flagged_claims"][0]["flag_kind"] == "unanchored_pass"

    def test_missing_quote_is_flagged_unanchored(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"supported"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["flagged_claims"][0]["flag_kind"] == "unanchored_pass"

    def test_unsupported_verdict_keeps_reason(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"unsupported","reason":"drift"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        f = rep["flagged_claims"][0]
        assert f["flag_kind"] == "judged_unsupported" and f["reason"] == "drift"

    def test_missing_verdict_is_flagged(self):
        rep = _verify(
            '{"claims":[{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["flagged_claims"][0]["flag_kind"] == "no_verdict"
        assert rep["unsupported_claim_count"] == 1

    def test_quote_matching_tolerates_case_and_punctuation(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"k-means partitions DATA, into k clusters!"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["unsupported_claim_count"] == 0

    def test_quote_matching_folds_pdf_ligatures(self):
        # PDF-extracted evidence carries ligatures (ﬁ → fi); a judge quote
        # typed in plain ascii must still anchor.
        llm = _SeqLLM([
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"classification assigns labels to data records"}]}'])
        v = ContentVerifier(retriever=None, llm=llm)
        rep = v.verify_chapter(
            "ch1", "T",
            {"slides": "Classification assigns labels to data records."},
            None,
            writer_evidence="[E1] Classiﬁcation assigns labels to data records.",
        )
        assert rep["unsupported_claim_count"] == 0

    def test_quote_matching_tolerates_pdf_glued_words(self):
        # PDF extraction can glue words together ("Google'sFlu Trends"); a
        # correctly quoted passage must still anchor via letter-sequence match.
        llm = _SeqLLM([
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"Flu Trends uses specific search terms as indicators"}]}'])
        v = ContentVerifier(retriever=None, llm=llm)
        rep = v.verify_chapter(
            "ch1", "T",
            {"slides": "Flu Trends used search terms to track flu activity."},
            None,
            writer_evidence="[E1] Google’sFlu Trends uses speciﬁc "
                            "search terms as indicators of ﬂu activity.",
        )
        assert rep["unsupported_claim_count"] == 0

    def test_short_quote_is_unanchored(self):
        rep = _verify(
            '{"claims":[{"index":1,"verdict":"supported","quote":"into k clusters"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}')
        assert rep["flagged_claims"][0]["flag_kind"] == "unanchored_pass"

    def test_retry_recovers_from_bad_format(self):
        llm = _SeqLLM([
            '{"unsupported":[]}',  # old format → corrective retry
            '{"claims":[{"index":1,"verdict":"supported",'
            '"quote":"K-Means partitions data into k clusters"},'
            '{"index":2,"verdict":"supported",'
            '"quote":"PCA reduces dimensions of the dataset"}]}',
        ])
        rep = _verify(llm)
        assert len(llm.calls) == 2
        assert rep["judge_protocol"] == "quote_anchored_v1"
        assert rep["unsupported_claim_count"] == 0

    def test_legacy_fallback_recorded_after_two_bad_replies(self):
        rep = _verify('{"unsupported":[{"index":2,"claim":"x","reason":"r"}]}')
        assert rep["judge_protocol"] == "legacy_fallback"
        assert rep["unsupported_claim_count"] == 1
        assert "supported_claims" not in rep  # legacy passes are unauditable


class TestReportLine:
    def test_line_format(self):
        assert "content-verify" in report_line({"chapter_id": "ch1", "summary": "3/4 supported"})
        assert "ERROR" in report_line({"chapter_id": "ch1", "summary": "x", "error": "Boom"})


class TestTitlesAndFramesExcluded:
    """Protocol change: claims are sentences — titles and frames are not claims."""

    def test_frametitle_content_is_not_a_claim(self):
        tex = ("\\frametitle{Case Study: Google Flu Trends Overview}\n"
               "The system analyzes search queries related to flu symptoms.")
        claims = _segment_claims(tex, limit=None)
        assert claims == ["The system analyzes search queries related to flu symptoms."]

    def test_inline_frame_title_is_not_a_claim(self):
        tex = ("\\begin{frame}[t]{Ethical Implications of Data Mining Today}\n"
               "\\item Privacy concerns arise when mining personal data records.\n"
               "\\end{frame}")
        claims = _segment_claims(tex, limit=None)
        assert claims == ["Privacy concerns arise when mining personal data records."]

    def test_markdown_headings_and_bold_lines_dropped(self):
        text = ("## Section 3: Why Data Mining?\n"
                "**Transition to Frame 3**\n"
                "Data mining extracts useful patterns from very large datasets.")
        claims = _segment_claims(text, limit=None)
        assert claims == ["Data mining extracts useful patterns from very large datasets."]

    def test_numeric_fragments_dropped(self):
        assert _segment_claims("= 230 = 39.13%", limit=None) == []

    def test_block_title_is_not_a_claim(self):
        tex = ("\\begin{block}{Case Study: Google Flu Trends}\n"
               "The project predicted flu activity from search query volumes.\n"
               "\\end{block}")
        claims = _segment_claims(tex, limit=None)
        assert claims == ["The project predicted flu activity from search query volumes."]

    def test_titlecase_heading_bullet_dropped(self):
        tex = ("\\item Data Mining Tools Overview\n"
               "\\item Several open tools support the full mining workflow today.")
        claims = _segment_claims(tex, limit=None)
        assert claims == ["Several open tools support the full mining workflow today."]

    def test_list_introducer_dropped(self):
        tex = ("A few examples include:\n"
               "\\item Retail basket analysis reveals products bought together.")
        claims = _segment_claims(tex, limit=None)
        assert claims == ["Retail basket analysis reveals products bought together."]

    def test_headless_definition_dropped(self):
        assert _segment_claims(": Removing noise and inconsistencies in data.", limit=None) == []

    def test_mangled_math_residue_dropped(self):
        assert _segment_claims("For the attribute , branches would correspond to categories.", limit=None) == []

    def test_course_meta_discourse_dropped(self):
        text = ("Students will also learn to summarize data using statistics.\n"
                "Identify the maximum value in the dataset.\n"
                "The interquartile range is the difference between the third and first quartiles.")
        claims = _segment_claims(text, limit=None)
        assert claims == ["The interquartile range is the difference between the third and first quartiles."]
