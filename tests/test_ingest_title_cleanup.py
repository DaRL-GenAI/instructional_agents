"""Tests for chapter/section heading title cleanup at ingest.

PDF extraction leaves markdown emphasis and trailing page numbers on heading
titles (e.g. "**K-Means Clustering 445**"). Those titles are what the course
contract binds topics against, so they are cleaned where Chapter/Section are
constructed. The page-number strip is conservative — it must not eat real
trailing numbers like "Chapter 8" or "Top 10 Algorithms".
"""

from __future__ import annotations

from src.textbook.ingest_md import _clean_heading_title


class TestCleanHeadingTitle:
    def test_strips_brackets_emphasis_and_pagenum(self):
        assert _clean_heading_title("10.3 **[Hierarchical Methods]**") == "10.3 Hierarchical Methods"
        assert _clean_heading_title("10.1 [Cluster Analysis]") == "10.1 Cluster Analysis"

    def test_strips_bold_and_trailing_pagenum(self):
        assert _clean_heading_title("**K-Means Clustering 445**") == "K-Means Clustering"
        assert _clean_heading_title("1.1 **Why Data Mining? 1**") == "1.1 Why Data Mining?"
        assert _clean_heading_title("**Classification: Basic Concepts 327**") == "Classification: Basic Concepts"

    def test_preserves_chapter_section_part_numbers(self):
        assert _clean_heading_title("Chapter 8") == "Chapter 8"
        assert _clean_heading_title("Section 3") == "Section 3"
        assert _clean_heading_title("Part 2") == "Part 2"

    def test_preserves_meaningful_trailing_numbers(self):
        assert _clean_heading_title("Top 10 Algorithms") == "Top 10 Algorithms"
        assert _clean_heading_title("Clustering in 2 Dimensions") == "Clustering in 2 Dimensions"
        # 4-digit numbers (years) are space-anchored away from the 1-3 digit rule
        assert _clean_heading_title("Methods Since 2020") == "Methods Since 2020"

    def test_preserves_already_clean_titles(self):
        assert _clean_heading_title("The K-Means Clustering Method") == "The K-Means Clustering Method"
        assert _clean_heading_title("DBSCAN") == "DBSCAN"

    def test_handles_empty(self):
        assert _clean_heading_title("") == ""
        assert _clean_heading_title("   ") == ""
