"""Tests for the textbook IR cache.

Covers:
    1. Round-trip: save → load returns an equal Textbook IR
    2. Cache miss returns None when no file exists
    3. Schema-validation failure returns None (corrupt cache file)
    4. Save creates parent directories as needed
    5. Subsequent ingestion via TextbookKnowledgeBase.from_path uses
       the cache on the second call (no second VLM extraction call)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.grounding.ir_cache import cache_path, load_ir, save_ir
from src.textbook.schema import Chapter, PageSpan, Paragraph, Section, Textbook


def _tiny_textbook(textbook_id="t") -> Textbook:
    return Textbook(
        textbook_id=textbook_id,
        title="T",
        authors=["A"],
        edition=None,
        source_format="pdf",
        parser_quality=1.0,
        chapters=[
            Chapter(
                chapter_id="ch1", number=1, title="Intro",
                pages=PageSpan(start=1, end=3),
                sections=[
                    Section(
                        section_id="ch1.s1", title="Overview",
                        pages=PageSpan(start=1, end=2),
                        paragraphs=[
                            Paragraph(
                                para_id="ch1.s1.p01",
                                text="First paragraph.",
                                page=1, kind="prose",
                            ),
                        ],
                        concepts=[],
                    ),
                ],
                learning_objectives=[],
            ),
        ],
    )


class TestCachePath:
    def test_uses_ir_subdir(self, tmp_path):
        p = cache_path(tmp_path, "han_data_mining_3e")
        assert p.parent.name == "ir"
        assert p.name == "han_data_mining_3e.json"

    def test_handles_string_cache_dir(self, tmp_path):
        p = cache_path(str(tmp_path), "x")
        assert p.parent.name == "ir"


class TestSaveAndLoad:
    def test_save_creates_parent_dirs(self, tmp_path):
        tb = _tiny_textbook()
        target = tmp_path / "deeply" / "nested" / "cache"
        out = save_ir(target, "t", tb)
        assert out.exists()
        assert out.parent.exists()
        assert out.parent.name == "ir"

    def test_round_trip_preserves_content(self, tmp_path):
        tb = _tiny_textbook(textbook_id="round_trip")
        save_ir(tmp_path, "round_trip", tb)
        loaded = load_ir(tmp_path, "round_trip")
        assert loaded is not None
        assert loaded.textbook_id == "round_trip"
        assert len(loaded.chapters) == 1
        assert loaded.chapters[0].sections[0].paragraphs[0].text == "First paragraph."

    def test_round_trip_pages_intact(self, tmp_path):
        tb = _tiny_textbook()
        save_ir(tmp_path, "t", tb)
        loaded = load_ir(tmp_path, "t")
        assert loaded.chapters[0].pages == PageSpan(start=1, end=3)
        assert loaded.chapters[0].sections[0].pages == PageSpan(start=1, end=2)


class TestCacheMiss:
    def test_missing_file_returns_none(self, tmp_path):
        assert load_ir(tmp_path, "does_not_exist") is None

    def test_corrupt_json_returns_none(self, tmp_path):
        p = cache_path(tmp_path, "broken")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{ not valid json", encoding="utf-8")
        assert load_ir(tmp_path, "broken") is None

    def test_schema_invalid_returns_none(self, tmp_path):
        p = cache_path(tmp_path, "wrong_schema")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"unrelated": "fields"}', encoding="utf-8")
        assert load_ir(tmp_path, "wrong_schema") is None


class TestFromPathUsesIrCache:
    """End-to-end: TextbookKnowledgeBase.from_path uses the cache on
    the second call so the underlying ingester is NOT invoked twice."""

    @patch("src.grounding.knowledge_base._ingest")
    def test_second_call_loads_from_cache(self, mock_ingest, tmp_path):
        from src.grounding.knowledge_base import TextbookKnowledgeBase

        # First call: ingester is hit, IR is cached.
        fake_tb = _tiny_textbook(textbook_id="cached_textbook")
        mock_ingest.return_value = fake_tb
        fake_pdf = tmp_path / "src.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")
        kb1 = TextbookKnowledgeBase.from_path(
            fake_pdf,
            textbook_id="cached_textbook",
            ir_cache_dir=tmp_path / "cache",
        )
        assert mock_ingest.call_count == 1
        # Keyed by textbook_id + a content fingerprint, not the bare stem.
        cached = list((tmp_path / "cache" / "ir").glob("cached_textbook_*.json"))
        assert len(cached) == 1

        # Second call: should NOT call the ingester again.
        kb2 = TextbookKnowledgeBase.from_path(
            fake_pdf,
            textbook_id="cached_textbook",
            ir_cache_dir=tmp_path / "cache",
        )
        assert mock_ingest.call_count == 1  # unchanged
        assert kb2.textbook.textbook_id == "cached_textbook"
        assert len(kb2.chunks) == len(kb1.chunks)

    @patch("src.grounding.knowledge_base._ingest")
    def test_use_ir_cache_false_bypasses_cache(self, mock_ingest, tmp_path):
        from src.grounding.knowledge_base import TextbookKnowledgeBase

        fake_tb = _tiny_textbook(textbook_id="bypass")
        mock_ingest.return_value = fake_tb
        fake_pdf = tmp_path / "src.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        TextbookKnowledgeBase.from_path(
            fake_pdf, textbook_id="bypass",
            ir_cache_dir=tmp_path / "cache",
            use_ir_cache=False,
        )
        TextbookKnowledgeBase.from_path(
            fake_pdf, textbook_id="bypass",
            ir_cache_dir=tmp_path / "cache",
            use_ir_cache=False,
        )
        assert mock_ingest.call_count == 2
        assert not (tmp_path / "cache").exists()

    @patch("src.grounding.knowledge_base._ingest")
    def test_changed_source_content_misses_cache(self, mock_ingest, tmp_path):
        """Same file NAME, different bytes -> cache miss (keyed on content)."""
        from src.grounding.knowledge_base import TextbookKnowledgeBase

        mock_ingest.return_value = _tiny_textbook(textbook_id="same_name")
        fake_pdf = tmp_path / "book.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 version one")
        TextbookKnowledgeBase.from_path(
            fake_pdf, textbook_id="same_name", ir_cache_dir=tmp_path / "cache",
        )
        fake_pdf.write_bytes(b"%PDF-1.4 version two, different content")
        TextbookKnowledgeBase.from_path(
            fake_pdf, textbook_id="same_name", ir_cache_dir=tmp_path / "cache",
        )
        assert mock_ingest.call_count == 2
        assert len(list((tmp_path / "cache" / "ir").glob("same_name_*.json"))) == 2

    @patch("src.grounding.knowledge_base._ingest")
    def test_no_cache_dir_means_no_cache(self, mock_ingest, tmp_path, monkeypatch):
        """Without ``ir_cache_dir`` nothing is written anywhere (in
        particular, never into the repository root)."""
        from src.grounding.knowledge_base import TextbookKnowledgeBase

        mock_ingest.return_value = _tiny_textbook(textbook_id="nocache")
        fake_pdf = tmp_path / "book.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4 fake")
        monkeypatch.chdir(tmp_path)
        TextbookKnowledgeBase.from_path(fake_pdf, textbook_id="nocache")
        TextbookKnowledgeBase.from_path(fake_pdf, textbook_id="nocache")
        assert mock_ingest.call_count == 2
        assert sorted(p.name for p in tmp_path.iterdir()) == ["book.pdf"]
        repo_root = Path(__file__).resolve().parents[1]
        assert not (repo_root / ".grounding_cache").exists()
