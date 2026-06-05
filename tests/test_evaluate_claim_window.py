"""Tests for the sentence-bounded claim window in GroundingAgent.

The verifier extracts a small window of text around each citation as
the "claim" it asks the LLM judge to score. The window is now
sentence-bounded — finding the SPECIFIC sentence containing the
citation rather than a fixed-character window — which makes the
judge's input cleaner and reduces variance.
"""

from unittest.mock import MagicMock

from evaluate import GroundingAgent


def _agent():
    """Build a GroundingAgent with a trivial KB and a stub LLM."""
    kb = MagicMock()
    kb.chunks = []
    kb.textbook_id = "t"
    return GroundingAgent(llm=MagicMock(), knowledge_base=kb)


class TestSentenceBoundedClaimWindow:
    def test_extracts_sentence_containing_citation(self):
        agent = _agent()
        text = (
            "First unrelated sentence. "
            "K-means partitions n observations [t:ch6.s3:p15] using nearest-mean assignment. "
            "Third unrelated sentence."
        )
        tok = "[t:ch6.s3:p15]"
        start = text.index(tok)
        cite = {"token": tok, "start": start, "end": start + len(tok)}
        claim = agent._claim_window(text, cite)
        assert "K-means partitions" in claim
        assert "nearest-mean assignment" in claim
        # Adjacent unrelated sentences should NOT be in the cleaned window
        assert "First unrelated" not in claim
        assert "Third unrelated" not in claim

    def test_tiny_sentence_expands_to_neighbours(self):
        agent = _agent()
        text = (
            "Background context sentence one. "
            "Yes [t:ch1.s1:p01]. "
            "Following clarification sentence."
        )
        tok = "[t:ch1.s1:p01]"
        start = text.index(tok)
        claim = agent._claim_window(text, {"token": tok, "start": start, "end": start + len(tok)})
        # The minimal sentence "Yes [tok]." is too short → expand to
        # include adjacent sentences for context
        assert "Background context" in claim or "Following clarification" in claim

    def test_citation_at_end_of_sentence_handled(self):
        agent = _agent()
        text = "The result follows from clustering [t:ch1.s1:p01]. Next sentence."
        tok = "[t:ch1.s1:p01]"
        start = text.index(tok)
        claim = agent._claim_window(text, {"token": tok, "start": start, "end": start + len(tok)})
        assert "result follows from clustering" in claim
        assert "Next sentence" not in claim

    def test_first_sentence_with_citation_handled(self):
        agent = _agent()
        text = "First sentence introduces ensemble methods [t:ch4.s7:p51]. Second sentence."
        tok = "[t:ch4.s7:p51]"
        start = text.index(tok)
        claim = agent._claim_window(text, {"token": tok, "start": start, "end": start + len(tok)})
        assert "First sentence introduces" in claim
        assert "Second sentence" not in claim

    def test_only_one_sentence_returns_it(self):
        agent = _agent()
        text = "Just one sentence here [t:ch1.s1:p01] no other content"
        tok = "[t:ch1.s1:p01]"
        start = text.index(tok)
        claim = agent._claim_window(text, {"token": tok, "start": start, "end": start + len(tok)})
        assert "Just one sentence" in claim

    def test_hard_cap_applied_when_expansion_overflows(self):
        agent = _agent()
        long_sentence = "Background " * 200
        text = f"{long_sentence}[t:ch1.s1:p01] [end]"
        tok = "[t:ch1.s1:p01]"
        start = text.index(tok)
        claim = agent._claim_window(text, {"token": tok, "start": start, "end": start + len(tok)})
        assert len(claim) <= agent.CLAIM_WINDOW_CHARS
