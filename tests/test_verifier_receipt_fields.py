"""The verification report records grounding state and coverage.

Two properties a reader of a report needs in order to interpret it:

1. **Grounding state.** A chapter the contract could not bind to any source
   section is written without retrieved evidence. Its report must say so —
   otherwise "no flagged claims" reads as "verified clean" when the chapter
   was never grounded in the first place. The fields are additive: what gets
   verified is unchanged, only what the report discloses.
2. **Coverage.** Verification is capped at ``_MAX_CLAIMS`` claims in document
   order. When a chapter segments more claims than that, the report must
   expose both numbers so the unchecked tail is visible.
"""

from __future__ import annotations

from src.grounding.content_verifier import ContentVerifier, _MAX_CLAIMS


def _verifier() -> ContentVerifier:
    v = ContentVerifier.__new__(ContentVerifier)
    v.llm = None            # no LLM call: we assert on report structure only
    v.retriever = None
    v.model = "test-model"
    return v


class TestGroundingState:
    def test_unbound_chapter_is_marked_not_grounded(self):
        r = _verifier().verify_chapter(
            "c1", "Chapter", {"slides": "A claim. Another claim."},
            section_ids=[])
        assert r["grounded"] is False
        assert r["bound_sections"] == []

    def test_bound_chapter_records_its_sections(self):
        r = _verifier().verify_chapter(
            "c1", "Chapter", {"slides": "A claim."},
            section_ids=["ch1.s1", "ch2.s3"])
        assert r["grounded"] is True
        assert r["bound_sections"] == ["ch1.s1", "ch2.s3"]

    def test_unbound_chapter_does_not_report_zero_flags_as_clean(self):
        """The failure this prevents: an ungrounded chapter silently reporting
        0 unsupported claims, indistinguishable from a verified one."""
        r = _verifier().verify_chapter(
            "c1", "Chapter", {"slides": "A claim."}, section_ids=None)
        assert r["unsupported_claim_count"] == 0
        assert r["grounded"] is False          # ...but the state disambiguates


class TestCoverageDisclosure:
    def test_short_chapter_is_not_capped(self):
        r = _verifier().verify_chapter(
            "c1", "Chapter", {"slides": "One. Two. Three."},
            section_ids=["ch1.s1"])
        assert r["claims_capped"] is False
        assert r["claims_segmented"] == r["claims_checked"]

    def test_long_chapter_exposes_the_unchecked_tail(self):
        many = " ".join(f"Claim number {i} is stated here." for i in range(200))
        r = _verifier().verify_chapter(
            "c1", "Chapter", {"slides": many}, section_ids=["ch1.s1"])
        assert r["claims_checked"] == _MAX_CLAIMS
        assert r["claims_segmented"] > _MAX_CLAIMS
        assert r["claims_capped"] is True
