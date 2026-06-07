"""Tests for the VLM adapter.

Covers:
    1. Schema models (FigureComponent, EquationComponent, TableComponent,
       AlgorithmComponent) validate as expected.
    2. ExtractedPage default factory and notes field.
    3. VlmExtractor lazy client construction.
    4. extract() returns empty extraction on render failure (defensive
       error handling).
    5. extract() returns empty extraction on VLM call failure (defensive
       error handling).
    6. extract() returns parsed VLM response on the happy path.
    7. PNG save-to-disk behavior when figures_dir is configured.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.textbook.vlm_adapter import (
    AlgorithmComponent,
    EquationComponent,
    ExtractedPage,
    FigureComponent,
    TableComponent,
    VlmExtractor,
)


class TestComponentModels:
    def test_figure_component_round_trip(self):
        f = FigureComponent(
            label="Figure 10.16",
            caption="OPTICS terminology",
            description="Diagram showing point p with core-distance circle "
                        "and two query points q1 and q2.",
            pedagogical_point="Reachability distance combines core-distance "
                              "and true distance.",
        )
        assert f.type == "figure"
        assert f.label == "Figure 10.16"

    def test_equation_component_round_trip(self):
        e = EquationComponent(
            label="(10.5)",
            latex=r"\text{reach-dist}_\varepsilon(p, q) = "
                  r"\max\{\text{core-dist}_\varepsilon(p), d(p, q)\}",
            description="The reachability distance from p to q.",
        )
        assert e.type == "equation"
        assert "max" in e.latex

    def test_table_component_round_trip(self):
        t = TableComponent(
            label="Table 2.1",
            caption="Sample customer data",
            headers=["ID", "Age", "Region"],
            rows=[["1", "25", "East"], ["2", "47", "West"]],
        )
        assert t.type == "table"
        assert len(t.rows) == 2
        assert t.rows[0][2] == "East"

    def test_algorithm_component_round_trip(self):
        a = AlgorithmComponent(
            label="Algorithm 8.2",
            name="k-means",
            steps=[
                "Initialize k cluster centroids randomly.",
                "Assign each point to nearest centroid.",
                "Recompute centroids as means of assigned points.",
                "Repeat steps 2-3 until convergence.",
            ],
        )
        assert a.type == "algorithm"
        assert len(a.steps) == 4


class TestExtractedPage:
    def test_default_empty(self):
        page = ExtractedPage()
        assert page.components == []
        assert page.notes == ""

    def test_can_carry_multiple_component_types(self):
        page = ExtractedPage(
            components=[
                FigureComponent(label="F1", caption="c", description="d",
                                pedagogical_point="p"),
                EquationComponent(label="(1)", latex="x = y", description="d"),
            ],
            notes="Two components on this page.",
        )
        assert len(page.components) == 2
        assert page.components[0].type == "figure"
        assert page.components[1].type == "equation"


class TestVlmExtractorClient:
    def test_lazy_client_constructed_on_first_access(self):
        with patch("openai.OpenAI") as mock_openai:
            mock_openai.return_value = MagicMock(name="mock_client")
            ex = VlmExtractor()
            assert ex._client is None  # not built yet
            _ = ex.client  # trigger lazy build
            assert ex._client is not None
            mock_openai.assert_called_once()

    def test_explicit_client_bypasses_construction(self):
        injected = MagicMock(name="injected_client")
        ex = VlmExtractor(client=injected)
        assert ex.client is injected

    def test_figures_dir_created_at_init(self, tmp_path):
        fdir = tmp_path / "figs" / "nested"
        ex = VlmExtractor(figures_dir=fdir)
        assert fdir.exists()
        assert fdir.is_dir()


class TestRenderPagePng:
    def test_save_as_writes_png_to_disk(self, tmp_path):
        ex = VlmExtractor(client=MagicMock())
        # Mock the PyMuPDF page.get_pixmap chain
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"\x89PNG fakepng"
        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix
        save_path = tmp_path / "out.png"
        bytes_returned = ex.render_page_png(mock_page, save_as=save_path)
        assert bytes_returned == b"\x89PNG fakepng"
        assert save_path.exists()
        assert save_path.read_bytes() == b"\x89PNG fakepng"


class TestExtract:
    def test_render_failure_returns_empty_extraction(self):
        ex = VlmExtractor(client=MagicMock())
        mock_page = MagicMock()
        mock_page.get_pixmap.side_effect = RuntimeError("boom")
        result = ex.extract(mock_page, textbook_id="t", page_num=1)
        assert isinstance(result, ExtractedPage)
        assert result.components == []

    def test_vlm_call_failure_returns_empty_extraction(self):
        client = MagicMock()
        client.beta.chat.completions.parse.side_effect = RuntimeError("api down")
        ex = VlmExtractor(client=client)
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png"
        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix
        result = ex.extract(mock_page, textbook_id="t", page_num=1)
        assert isinstance(result, ExtractedPage)
        assert result.components == []

    def test_happy_path_returns_parsed_components(self):
        # Mock OpenAI response with one figure component
        parsed_extraction = ExtractedPage(
            components=[FigureComponent(
                label="Figure 10.16",
                caption="OPTICS terminology",
                description="Point p with core-distance circle.",
                pedagogical_point="Reachability combines core-dist and d(p,q).",
            )],
            notes="",
        )
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.parsed = parsed_extraction
        client = MagicMock()
        client.beta.chat.completions.parse.return_value = completion
        ex = VlmExtractor(client=client)
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"png"
        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix
        result = ex.extract(mock_page, textbook_id="han", page_num=476)
        assert len(result.components) == 1
        assert result.components[0].type == "figure"
        assert result.components[0].label == "Figure 10.16"

    def test_png_saved_to_figures_dir_on_extract(self, tmp_path):
        completion = MagicMock()
        completion.choices = [MagicMock()]
        completion.choices[0].message.parsed = ExtractedPage()
        client = MagicMock()
        client.beta.chat.completions.parse.return_value = completion
        figs = tmp_path / "figs"
        ex = VlmExtractor(client=client, figures_dir=figs)
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b"\x89PNG fake"
        mock_page = MagicMock()
        mock_page.get_pixmap.return_value = mock_pix
        ex.extract(mock_page, textbook_id="han_data_mining_3e", page_num=476)
        saved = figs / "han_data_mining_3e_p0476.png"
        assert saved.exists()
        assert saved.read_bytes() == b"\x89PNG fake"


class TestRateLimitRetry:
    """v7.1 — VLM rate-limit retry behaviour."""

    def _make_extractor(self, side_effects):
        """Build a VlmExtractor whose _call_vlm raises in sequence then
        returns ExtractedPage on the final call."""
        client = MagicMock()
        ex = VlmExtractor(client=client)
        # Patch _call_vlm directly (we test the retry wrapper, not the
        # internals of the OpenAI call).
        ex._call_vlm = MagicMock(side_effect=side_effects)
        # Speed up tests — collapse sleeps to ~no-op
        ex._VLM_RETRY_BASE_SLEEP_S = 0.001
        ex._VLM_RETRY_RATE_LIMIT_SLEEP_S = 0.001
        return ex

    def _rate_limit_error(self, retry_after_ms=None):
        msg = "Rate limit reached for gpt-4o ... rate_limit_exceeded"
        if retry_after_ms is not None:
            msg += f" Please try again in {retry_after_ms}ms. Visit ..."
        # Wrap in an exception whose class name contains RateLimitError
        class RateLimitError(Exception):
            pass
        return RateLimitError(msg)

    def test_rate_limit_then_success(self):
        good = ExtractedPage()
        ex = self._make_extractor([
            self._rate_limit_error(retry_after_ms=500),
            good,
        ])
        result = ex._call_vlm_with_retry(b"png", "han", 264)
        assert result is good
        assert ex._call_vlm.call_count == 2

    def test_rate_limit_retries_then_gives_up(self):
        # All 6 attempts fail with rate limit
        ex = self._make_extractor([
            self._rate_limit_error(retry_after_ms=100)
        ] * 6)
        result = ex._call_vlm_with_retry(b"png", "han", 264)
        # Defensive: returns empty extraction, doesn't raise
        assert isinstance(result, ExtractedPage)
        assert result.components == []
        assert ex._call_vlm.call_count == 6

    def test_transient_error_retries(self):
        good = ExtractedPage()
        ex = self._make_extractor([
            TimeoutError("read timeout"),
            ConnectionError("network blip"),
            good,
        ])
        result = ex._call_vlm_with_retry(b"png", "han", 100)
        assert result is good
        assert ex._call_vlm.call_count == 3

    def test_success_on_first_attempt_no_retry(self):
        good = ExtractedPage()
        ex = self._make_extractor([good])
        result = ex._call_vlm_with_retry(b"png", "han", 1)
        assert result is good
        assert ex._call_vlm.call_count == 1


class TestParseRetryAfter:
    """v7.1 — parse OpenAI's retry-after hint from the error string."""

    def test_parses_milliseconds(self):
        msg = "Please try again in 892ms. Visit ..."
        s = VlmExtractor._parse_retry_after(msg)
        # Adds 2s safety margin + clamps to >= 5s
        assert s == 5.0

    def test_parses_seconds(self):
        msg = "Please try again in 30s. Visit ..."
        s = VlmExtractor._parse_retry_after(msg)
        assert s == 32.0  # 30 + 2 safety margin

    def test_returns_none_when_no_hint(self):
        msg = "rate_limit_exceeded with no parseable hint"
        s = VlmExtractor._parse_retry_after(msg)
        assert s is None

    def test_clamps_to_minimum_5s(self):
        msg = "Please try again in 100ms. Visit ..."
        s = VlmExtractor._parse_retry_after(msg)
        assert s >= 5.0
