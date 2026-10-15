"""Tests for configuration management, CLI argument parsing, and catalog loading."""

import json
import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch

from run import load_catalog
from src.ADDIE import ADDIE


CATALOG_DIR = Path(__file__).resolve().parents[1] / "catalog"


def load_packaged_catalog(name: str = "default_catalog") -> dict:
    return json.loads((CATALOG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def map_addie_catalog(catalog_data: dict) -> dict:
    addie = object.__new__(ADDIE)
    addie.catalog = True
    addie.set_catalog(catalog_data)
    return addie.catalog_dict


class TestLoadCatalog:
    """Tests for catalog loading in run.py"""

    def test_load_default_copilot(self):
        result = load_catalog(catalog_dir="copilot", catalog_name="default_copilot")
        assert isinstance(result, dict)
        assert "learning_objectives" in result
        assert "syllabus" in result
        assert "slides" in result
        assert "script" in result
        assert "assessment" in result
        assert "overall" in result
        # All values should be empty strings for defaults
        for v in result.values():
            assert v == ""

    def test_load_catalog_from_file(self):
        catalog_data = {
            "course_structure": {"topics": ["ML", "DL"]},
            "student_profile": {"level": "graduate"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = os.path.join(tmpdir, "test_catalog.json")
            with open(catalog_path, "w") as f:
                json.dump(catalog_data, f)

            result = load_catalog(catalog_dir=tmpdir, catalog_name="test_catalog")

        assert result["course_structure"]["topics"] == ["ML", "DL"]
        assert result["student_profile"]["level"] == "graduate"

    def test_load_catalog_missing_file(self):
        result = load_catalog(catalog_dir="/nonexistent", catalog_name="missing")
        assert result == {}

    def test_load_catalog_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = os.path.join(tmpdir, "bad.json")
            with open(bad_file, "w") as f:
                f.write("not valid json {{{")

            result = load_catalog(catalog_dir=tmpdir, catalog_name="bad")
        assert result == {}

    def test_legacy_catalog_without_style_preferences_remains_valid(self):
        catalog_data = load_packaged_catalog()
        catalog_data.pop("presentation_style_preferences")

        mapped = map_addie_catalog(catalog_data)

        assert mapped["presentation_style_preferences"] == {}

    def test_catalog_preserves_structured_style_preferences(self):
        catalog_data = load_packaged_catalog()
        expected = catalog_data["presentation_style_preferences"]

        mapped = map_addie_catalog(catalog_data)

        assert mapped["presentation_style_preferences"] == expected

    @pytest.mark.parametrize("catalog_name", ("default_catalog", "mwe_catalog"))
    def test_packaged_catalogs_pass_addie_style_preference_validation(
        self, catalog_name
    ):
        catalog_data = load_packaged_catalog(catalog_name)

        mapped = map_addie_catalog(catalog_data)

        assert mapped["presentation_style_preferences"]

    @pytest.mark.parametrize(
        ("preferences", "message"),
        [
            ("minimal", "must be a JSON object"),
            (
                {"color_preferences": ["blue"]},
                "requires text values for populated fields",
            ),
            (
                {"unknown_preference": "value"},
                "contains unsupported fields",
            ),
        ],
    )
    def test_malformed_style_preferences_are_rejected_before_generation(
        self, preferences, message
    ):
        catalog_data = load_packaged_catalog()
        catalog_data["presentation_style_preferences"] = preferences

        with pytest.raises(ValueError, match=message):
            map_addie_catalog(catalog_data)


class TestCLIArgs:
    """Tests for CLI argument parsing structure."""

    def test_run_py_importable(self):
        """run.py should be importable without side effects."""
        import run
        assert hasattr(run, "run_instructional_design")
        assert hasattr(run, "run_optimization")
        assert hasattr(run, "load_catalog")
