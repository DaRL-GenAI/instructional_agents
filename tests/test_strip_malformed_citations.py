"""Tests for the malformed citation token stripper.

The LLM occasionally emits citation-shaped tokens that don't match
the canonical format (truncated section, missing page, etc.). Without
stripping, the verifier counts these as `malformed` in its
failure-mode bucket and the precision metric undercounts the writer's
actual quality. Stripping at write-time leaves the surrounding claim
text intact.
"""

from src.slides import _strip_malformed_citation_tokens


class TestStripMalformedCitationTokens:
    TID = "han_data_mining_3e"

    def test_well_formed_token_preserved(self):
        text = (
            "K-means partitions n observations [han_data_mining_3e:ch6.s3:p15] "
            "into k clusters."
        )
        assert _strip_malformed_citation_tokens(text, self.TID) == text

    def test_truncated_token_stripped(self):
        text = "K-means partitions observations [han_data_mining_3e:c] using nearest mean."
        out = _strip_malformed_citation_tokens(text, self.TID)
        assert "[han_data_mining_3e:c]" not in out
        assert "K-means partitions observations" in out
        assert "using nearest mean" in out

    def test_textbook_only_token_stripped(self):
        text = "k-NN works well [han_data_mining_3e] in low dimensions."
        out = _strip_malformed_citation_tokens(text, self.TID)
        assert "[han_data_mining_3e]" not in out
        assert "k-NN works well" in out
        assert "in low dimensions" in out

    def test_missing_page_token_stripped(self):
        text = "Define entropy [han_data_mining_3e:ch4.s2] formally."
        out = _strip_malformed_citation_tokens(text, self.TID)
        assert "[han_data_mining_3e:ch4.s2]" not in out
        assert "Define entropy" in out

    def test_other_bracketed_text_untouched(self):
        # LaTeX options, square-bracket markdown — must not be stripped
        text = (
            "\\begin{frame}[fragile]{Title}\n"
            "\\includegraphics[width=0.5\\textwidth]{figure.png}\n"
            "[1] reference style bibliography\n"
        )
        assert _strip_malformed_citation_tokens(text, self.TID) == text

    def test_mixed_well_formed_and_malformed(self):
        text = (
            "First claim [han_data_mining_3e:ch1.s1:p01] is supported. "
            "Second claim [han_data_mining_3e:c] is malformed. "
            "Third claim [han_data_mining_3e:ch2.s3:p17] is also supported."
        )
        out = _strip_malformed_citation_tokens(text, self.TID)
        # Well-formed tokens preserved
        assert "[han_data_mining_3e:ch1.s1:p01]" in out
        assert "[han_data_mining_3e:ch2.s3:p17]" in out
        # Malformed stripped
        assert "[han_data_mining_3e:c]" not in out

    def test_empty_textbook_id_no_op(self):
        text = "Some claim with [anything:looking:like-a-citation] in it."
        assert _strip_malformed_citation_tokens(text, "") == text
        assert _strip_malformed_citation_tokens(text, None) == text

    def test_empty_text_no_op(self):
        assert _strip_malformed_citation_tokens("", self.TID) == ""
        assert _strip_malformed_citation_tokens(None, self.TID) is None

    def test_different_textbook_id_not_stripped(self):
        # Tokens referencing OTHER textbooks shouldn't be touched
        text = "Different textbook [other_textbook:ch1.s1:p01] reference."
        assert _strip_malformed_citation_tokens(text, self.TID) == text
