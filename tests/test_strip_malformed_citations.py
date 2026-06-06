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


class TestStripUnresolvableTokens:
    """When the caller supplies a valid_tokens set, well-formed-but-
    non-existent tokens (e.g. the writer hallucinated a fake section
    that passes the format regex but doesn't resolve to any KB chunk)
    are also stripped."""

    TID = "han_data_mining_3e"
    VALID = {
        "[han_data_mining_3e:ch1.s1:p01]",
        "[han_data_mining_3e:ch2.s3:p17]",
        "[han_data_mining_3e:ch4.s7:p51]",
    }

    def test_valid_token_in_set_preserved(self):
        text = "Claim [han_data_mining_3e:ch1.s1:p01] supported."
        out = _strip_malformed_citation_tokens(text, self.TID, valid_tokens=self.VALID)
        assert "[han_data_mining_3e:ch1.s1:p01]" in out

    def test_unresolvable_token_stripped(self):
        text = "Plausible-looking but fake [han_data_mining_3e:ch99.s99:p01]."
        out = _strip_malformed_citation_tokens(text, self.TID, valid_tokens=self.VALID)
        assert "[han_data_mining_3e:ch99.s99:p01]" not in out
        assert "Plausible-looking but fake" in out

    def test_mixed_resolvable_and_unresolvable(self):
        text = (
            "Real [han_data_mining_3e:ch2.s3:p17] and "
            "fake [han_data_mining_3e:ch77.s77:p77] in one sentence."
        )
        out = _strip_malformed_citation_tokens(text, self.TID, valid_tokens=self.VALID)
        assert "[han_data_mining_3e:ch2.s3:p17]" in out
        assert "[han_data_mining_3e:ch77.s77:p77]" not in out

    def test_valid_tokens_none_falls_back_to_format_check_only(self):
        # When valid_tokens=None, all well-formed tokens are preserved
        # (the old behaviour; backward-compat).
        text = "Plausible [han_data_mining_3e:ch99.s99:p01] token."
        out = _strip_malformed_citation_tokens(text, self.TID, valid_tokens=None)
        assert "[han_data_mining_3e:ch99.s99:p01]" in out

    def test_unresolvable_still_works_with_syntactically_malformed(self):
        # Both kinds of bad tokens removed in the same pass
        text = (
            "Real [han_data_mining_3e:ch1.s1:p01]; "
            "broken [han_data_mining_3e:c]; "
            "fake [han_data_mining_3e:ch99.s99:p99]; "
            "real again [han_data_mining_3e:ch4.s7:p51]"
        )
        out = _strip_malformed_citation_tokens(text, self.TID, valid_tokens=self.VALID)
        assert "[han_data_mining_3e:ch1.s1:p01]" in out
        assert "[han_data_mining_3e:ch4.s7:p51]" in out
        assert "[han_data_mining_3e:c]" not in out
        assert "[han_data_mining_3e:ch99.s99:p99]" not in out
