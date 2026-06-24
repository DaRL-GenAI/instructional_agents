"""Tests for equation-only VLM extraction (grounded ingest path).

Locks the contract the paged ingester depends on: a PNG-header pre-filter that
skips figure-shaped crops, clean-LaTeX post-processing, and fail-open behavior
(no API key / non-equation / error → "" so the caller keeps the image).
"""

from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from src.textbook.equation_vlm import (
    _clean_latex,
    _png_dimensions,
    extract_equation_latex,
    looks_like_equation,
)


def _write_png(path, w, h):
    """Write a file with a valid PNG signature + IHDR width/height (enough for
    _png_dimensions, which only reads the first 24 bytes)."""
    head = (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13) + b"IHDR"
        + struct.pack(">II", w, h)
    )
    path.write_bytes(head + b"\x00" * 16)
    return str(path)


def _client_returning(content):
    c = MagicMock()
    c.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    return c


class TestPngDimensions:
    def test_reads_dims(self, tmp_path):
        p = _write_png(tmp_path / "eq.png", 600, 90)
        assert _png_dimensions(p) == (600, 90)

    def test_non_png_returns_zero(self, tmp_path):
        p = tmp_path / "x.png"
        p.write_bytes(b"not a png")
        assert _png_dimensions(p) == (0, 0)


class TestLooksLikeEquation:
    def test_wide_crop_is_candidate(self, tmp_path):
        assert looks_like_equation(_write_png(tmp_path / "w.png", 545, 101)) is True

    def test_tall_or_square_figure_skipped(self, tmp_path):
        assert looks_like_equation(_write_png(tmp_path / "t.png", 692, 913)) is False

    def test_unreadable_defaults_to_true(self, tmp_path):
        p = tmp_path / "bad.png"
        p.write_bytes(b"garbage")
        # never silently skip a real equation when we can't measure it
        assert looks_like_equation(p) is True


class TestCleanLatex:
    def test_strips_dollar_and_display_wrappers(self):
        assert _clean_latex(r"$\bar{x}=1$") == r"\bar{x}=1"
        assert _clean_latex(r"\[ a+b \]") == "a+b"

    def test_strips_code_fence(self):
        assert _clean_latex("```latex\n\\frac{a}{b}\n```") == r"\frac{a}{b}"


class TestExtractEquationLatex:
    def test_returns_clean_latex_for_equation(self, tmp_path):
        p = _write_png(tmp_path / "eq.png", 500, 90)
        client = _client_returning(r"\bar{x} = \frac{\sum w_i x_i}{\sum w_i}")
        out = extract_equation_latex(p, client=client)
        assert out == r"\bar{x} = \frac{\sum w_i x_i}{\sum w_i}"

    def test_none_response_returns_empty(self, tmp_path):
        p = _write_png(tmp_path / "fig.png", 500, 500)
        out = extract_equation_latex(p, client=_client_returning("NONE"))
        assert out == ""

    def test_fail_open_on_client_error(self, tmp_path):
        p = _write_png(tmp_path / "eq.png", 500, 90)
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        assert extract_equation_latex(p, client=client) == ""

    def test_fail_open_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        p = _write_png(tmp_path / "eq.png", 500, 90)
        # no client + no key → "" (never raises, caller keeps the image)
        assert extract_equation_latex(p) == ""

    def test_missing_file_returns_empty(self):
        assert extract_equation_latex("/no/such/file.png", client=_client_returning("x")) == ""
