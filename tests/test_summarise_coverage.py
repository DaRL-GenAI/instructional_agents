"""Tests for the page-coverage + per-class precision summary helper.

The summary writer surfaces metrics that were previously computed in
ad-hoc scripts after-the-fact: page-coverage (the recall side of the
dial), per-class precision (the prose/visual tradeoff), and the top
contributing section per failure mode (debugging target). Having
them in evaluate.py means every run reports them automatically.
"""

from types import SimpleNamespace

from evaluate import _chunk_is_visual, _summarise_coverage


def _chunk(textbook_id="t", chapter_id="ch1", section_id="ch1.s1",
           page_start=1, page_end=1, text="prose content"):
    c = SimpleNamespace(
        textbook_id=textbook_id, chapter_id=chapter_id,
        section_id=section_id, page_start=page_start, page_end=page_end,
        text=text,
    )
    c.citation_tokens_in_range = lambda: [
        f"[{textbook_id}:{section_id}:p{p:02d}]"
        for p in range(page_start, page_end + 1)
    ]
    c.citation_token = lambda: f"[{textbook_id}:{section_id}:p{page_start:02d}]"
    return c


def _kb(chunks):
    return SimpleNamespace(chunks=chunks)


def _file_data(citations):
    return [{"per_citation": citations}]


class TestChunkIsVisual:
    def test_image_path_marker_detected(self):
        c = _chunk(text="Figure 8.22 [IMAGE_PATH: /a.png]")
        assert _chunk_is_visual(c)

    def test_latex_marker_detected(self):
        c = _chunk(text="Equation [LATEX: x^2 = y]")
        assert _chunk_is_visual(c)

    def test_table_marker_detected(self):
        c = _chunk(text="Table 2.1 [TABLE: | A | B |]")
        assert _chunk_is_visual(c)

    def test_algorithm_marker_detected(self):
        c = _chunk(text="Algorithm 8.2 [ALGORITHM_STEPS: 1. init]")
        assert _chunk_is_visual(c)

    def test_plain_prose_not_visual(self):
        c = _chunk(text="K-means partitions n observations into k clusters.")
        assert not _chunk_is_visual(c)


class TestSummariseCoverage:
    def test_no_kb_returns_zero_pages(self):
        out = _summarise_coverage(None, [])
        assert out["total_pages_in_textbook"] == 0
        assert out["distinct_pages_cited"] == 0
        assert out["page_coverage_pct"] is None

    def test_page_coverage_basic(self):
        chunks = [_chunk(page_start=1, page_end=1),
                  _chunk(page_start=2, page_end=2)]
        kb = _kb(chunks)
        files = _file_data([
            {"token": "[t:ch1.s1:p01]", "score": 4.5, "failure_mode": "good"},
        ])
        out = _summarise_coverage(kb, files)
        assert out["total_pages_in_textbook"] == 2
        assert out["distinct_pages_cited"] == 1
        assert out["page_coverage_pct"] == 50.0

    def test_multi_page_chunk_attributes_all_pages_to_coverage(self):
        # A 3-page chunk cited once → covers all 3 pages
        chunks = [_chunk(page_start=3, page_end=5)]
        kb = _kb(chunks)
        files = _file_data([
            {"token": "[t:ch1.s1:p04]", "score": 4.5, "failure_mode": "good"},
        ])
        out = _summarise_coverage(kb, files)
        assert out["distinct_pages_cited"] == 3

    def test_per_class_precision_splits_visual_and_prose(self):
        prose_chunk = _chunk(text="plain prose", page_start=1, page_end=1)
        visual_chunk = _chunk(text="[IMAGE_PATH: /x.png]",
                              section_id="ch1.s2", page_start=2, page_end=2)
        kb = _kb([prose_chunk, visual_chunk])
        files = _file_data([
            {"token": "[t:ch1.s1:p01]", "score": 5.0, "failure_mode": "good"},
            {"token": "[t:ch1.s1:p01]", "score": 2.5, "failure_mode": "hallucination"},
            {"token": "[t:ch1.s2:p02]", "score": 4.5, "failure_mode": "good"},
        ])
        out = _summarise_coverage(kb, files)
        prose = out["per_class_precision"]["prose"]
        visual = out["per_class_precision"]["visual"]
        assert prose["n"] == 2
        assert prose["supported"] == 1
        assert prose["precision"] == 0.5
        assert visual["n"] == 1
        assert visual["supported"] == 1
        assert visual["precision"] == 1.0

    def test_top_section_per_failure_mode(self):
        kb = _kb([
            _chunk(section_id="ch1.s1", page_start=1, page_end=1),
            _chunk(section_id="ch2.s3", page_start=2, page_end=2),
        ])
        files = _file_data([
            {"token": "[t:ch1.s1:p01]", "score": 2.0, "failure_mode": "retrieval_bad"},
            {"token": "[t:ch1.s1:p01]", "score": 2.0, "failure_mode": "retrieval_bad"},
            {"token": "[t:ch2.s3:p02]", "score": 2.0, "failure_mode": "retrieval_bad"},
        ])
        out = _summarise_coverage(kb, files)
        # ch1.s1 contributed 2 retrieval_bad; ch2.s3 contributed 1 → ch1.s1 wins
        top = out["per_failure_mode_top_section"]["retrieval_bad"]
        assert top["section_id"] == "ch1.s1"
        assert top["count"] == 2

    def test_robust_to_kb_without_citation_tokens_in_range(self):
        # Older Chunk shape: only has citation_token (no range method)
        c = SimpleNamespace(
            chapter_id="ch1", section_id="ch1.s1",
            page_start=1, page_end=1, text="prose",
        )
        c.citation_token = lambda: "[t:ch1.s1:p01]"
        kb = _kb([c])
        files = _file_data([
            {"token": "[t:ch1.s1:p01]", "score": 4.5, "failure_mode": "good"},
        ])
        out = _summarise_coverage(kb, files)
        assert out["distinct_pages_cited"] == 1
