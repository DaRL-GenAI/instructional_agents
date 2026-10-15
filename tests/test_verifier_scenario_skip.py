"""Verifier: frames that are hypothetical by design (discussion cases,
knowledge-check scenarios) can be set aside and COUNTED rather than judged.
Opt-in per call (``skip_frame_titles``); every existing caller is unchanged.
"""

from __future__ import annotations

import re

from src.grounding import content_verifier as cv
from src.grounding.content_verifier import ContentVerifier, _split_frames_by_title

DECK = r"""
\begin{frame}[fragile]
\frametitle{Legal Medical Record: What Counts}
The legal medical record is the organization's official record of direct patient care.
\end{frame}

\begin{frame}[fragile]{Discussion Cases: Which Copy Fits?}
A nurse is reconciling medications and finds that two lists disagree. Which source would you trust first?
\end{frame}

\begin{frame}[fragile]
\frametitle{Knowledge check 1}
You are tracing a missing result across two systems. Which system would you inspect next?
\end{frame}

\begin{frame}[fragile]
\frametitle{Answers: Follow the Source}
The laboratory system holds the result in structured fields with units.
\end{frame}
"""
PATTERN = re.compile(r"knowledge check|discussion", re.I)


class TestSplit:
    def test_both_title_forms_are_recognised(self):
        kept, skipped, titles = _split_frames_by_title(DECK, PATTERN)
        assert titles == ["Discussion Cases: Which Copy Fits?", "Knowledge check 1"]
        assert "reconciling medications" in skipped and "tracing a missing result" in skipped
        assert "reconciling medications" not in kept
        assert "official record of direct patient care" in kept
        assert "structured fields with units" in kept  # answers stay judged

    def test_no_pattern_is_identity(self):
        assert _split_frames_by_title(DECK, None) == (DECK, "", [])


class TestVerifyChapter:
    def _verifier(self):
        v = ContentVerifier.__new__(ContentVerifier)
        v.llm = None            # segmentation only; no judge calls
        v.model = "none"
        v.retriever = None
        return v

    def test_default_call_unchanged(self):
        r = self._verifier().verify_chapter("c1", "T", {"slides": DECK}, ["s1"])
        assert "scenario_frames_skipped" not in r
        assert r["claims_segmented"] == 6

    def test_skip_reports_scenarios_separately(self):
        r = self._verifier().verify_chapter(
            "c1", "T", {"slides": DECK}, ["s1"], skip_frame_titles=PATTERN)
        assert r["scenario_frames_skipped"] == 2
        assert r["scenario_sentences_skipped"] == 4
        assert r["scenario_frame_titles"] == ["Discussion Cases: Which Copy Fits?", "Knowledge check 1"]
        assert r["claims_segmented"] == 2   # the legal-record sentence + the answer sentence
        assert r["scenario_pattern"] == PATTERN.pattern
