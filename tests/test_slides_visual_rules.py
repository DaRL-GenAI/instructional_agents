"""Tests for the v3 visual-content rule block in _build_evidence_block.

Covers:
    1. Vanilla preservation: no markers in evidence → no rule block
       added (empty string returned by _build_visual_content_rules).
    2. Each marker triggers its corresponding rule line for slides.
    3. Script artifact gets narration-flavored rules instead of LaTeX-
       emission rules.
    4. Multiple markers in one evidence text all surface in the rule
       block.
    5. End-to-end via _build_evidence_block: with a mocked retriever
       returning a chunk containing v3 markers, the returned
       evidence_block includes the VISUAL CONTENT RULES section.
"""

from unittest.mock import MagicMock

from src.slides import SlidesDeliberation


def _bare_deliberation():
    """Construct a SlidesDeliberation skeleton sufficient for testing
    the rule builder without exercising the full pipeline."""
    d = SlidesDeliberation.__new__(SlidesDeliberation)
    d.retriever = None
    d.section_ids = None
    d.textbook_id = None
    return d


class TestBuildVisualContentRules:
    def test_no_markers_returns_empty_string(self):
        d = _bare_deliberation()
        # Plain prose, no v3 markers
        rules = d._build_visual_content_rules("Some plain prose excerpt.", "slide")
        assert rules == ""

    def test_image_path_marker_adds_includegraphics_rule_for_slide(self):
        d = _bare_deliberation()
        text = "Figure 8.22 [IMAGE_PATH: /figs/p53.png] [DESCRIPTION: x]"
        rules = d._build_visual_content_rules(text, "slide")
        assert "VISUAL CONTENT RULES" in rules
        assert "\\includegraphics" in rules
        assert "IMAGE_PATH" in rules

    def test_image_path_marker_adds_narration_rule_for_script(self):
        d = _bare_deliberation()
        text = "Figure 8.22 [IMAGE_PATH: /figs/p53.png]"
        rules = d._build_visual_content_rules(text, "script")
        assert "VISUAL CONTENT RULES" in rules
        # Script rule should mention narrating; should NOT instruct to
        # emit \includegraphics (the slide does that)
        assert "\\includegraphics" not in rules
        assert "Narrate" in rules or "narrate" in rules

    def test_latex_marker_adds_display_math_rule_for_slide(self):
        d = _bare_deliberation()
        text = "Equation: [LATEX: x^2 + y^2 = r^2]"
        rules = d._build_visual_content_rules(text, "slide")
        assert "LATEX" in rules
        # Should instruct to use display math
        assert "\\[" in rules or "display math" in rules

    def test_latex_marker_for_script_does_not_emit_raw_latex(self):
        d = _bare_deliberation()
        text = "[LATEX: x^2 = y]"
        rules = d._build_visual_content_rules(text, "script")
        # Script should advise plain-English description, not raw LaTeX
        assert "plain English" in rules

    def test_table_marker_adds_tabular_rule_for_slide(self):
        d = _bare_deliberation()
        text = "[TABLE: | A | B |\n| 1 | 2 |]"
        rules = d._build_visual_content_rules(text, "slide")
        assert "tabular" in rules
        assert "TABLE" in rules

    def test_algorithm_marker_adds_enumerated_list_rule(self):
        d = _bare_deliberation()
        text = "[ALGORITHM_STEPS: 1. step a 2. step b]"
        rules = d._build_visual_content_rules(text, "slide")
        assert "enumerated list" in rules
        assert "ALGORITHM_STEPS" in rules

    def test_description_and_insight_markers_get_combined_rule(self):
        d = _bare_deliberation()
        text = "[DESCRIPTION: shows x] [INSIGHT: matters because y]"
        rules = d._build_visual_content_rules(text, "slide")
        assert "DESCRIPTION" in rules
        assert "INSIGHT" in rules

    def test_multiple_markers_all_appear_in_rule_block(self):
        d = _bare_deliberation()
        text = (
            "[IMAGE_PATH: /a.png] [LATEX: x=y] [TABLE: ...] "
            "[ALGORITHM_STEPS: 1. do x]"
        )
        rules = d._build_visual_content_rules(text, "slide")
        assert "IMAGE_PATH" in rules
        assert "LATEX" in rules
        assert "TABLE" in rules
        assert "ALGORITHM_STEPS" in rules


class TestBuildEvidenceBlockIntegration:
    def test_retriever_none_returns_empty_pair(self):
        d = _bare_deliberation()
        evidence, rules = d._build_evidence_block("query", "slide")
        assert evidence == ""
        assert rules == ""

    def test_evidence_block_includes_visual_rules_when_marker_present(self):
        d = _bare_deliberation()
        # Mock the retriever to return one chunk with a v3 image marker
        mock_chunk = MagicMock()
        mock_chunk.text = (
            "Figure 8.22 OPTICS terminology [IMAGE_PATH: /figures/han_p476.png] "
            "[DESCRIPTION: Two scatter plots showing core-distance.]"
        )
        mock_chunk.citation_token.return_value = "[han:ch10.s4:p476]"
        mock_chunk.chapter_title = "Cluster Analysis"
        mock_chunk.section_title = "OPTICS"
        mock_chunk.page_start = 476
        mock_result = MagicMock()
        mock_result.chunk = mock_chunk
        d.retriever = MagicMock()
        d.retriever.search.return_value = [mock_result]
        evidence, rules = d._build_evidence_block("OPTICS", "slide")
        assert "VISUAL CONTENT RULES" in evidence
        assert "\\includegraphics" in evidence

    def test_evidence_block_omits_visual_rules_when_no_markers(self):
        d = _bare_deliberation()
        # Plain chunk with no v3 markers
        mock_chunk = MagicMock()
        mock_chunk.text = "K-means partitions observations into k clusters."
        mock_chunk.citation_token.return_value = "[han:ch10.s2:p450]"
        mock_chunk.chapter_title = "Cluster Analysis"
        mock_chunk.section_title = "k-means"
        mock_chunk.page_start = 450
        mock_result = MagicMock()
        mock_result.chunk = mock_chunk
        d.retriever = MagicMock()
        d.retriever.search.return_value = [mock_result]
        evidence, _ = d._build_evidence_block("k-means", "slide")
        assert "VISUAL CONTENT RULES" not in evidence
