import base64
from pathlib import Path

import pytest

from src.slide_io import atomic_write, parse_json_object, valid_png_bytes


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Wl2ZQAAAABJRU5ErkJggg=="
)


def test_parse_json_object_handles_fenced_model_output() -> None:
    assert parse_json_object('prefix ```json\\n{"ok": true}\\n``` suffix') == {
        "ok": True
    }
    assert parse_json_object("no object") is None


def test_atomic_write_cleans_up_after_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"

    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write(path, "{}")

    assert not path.with_suffix(".json.tmp").exists()


def test_png_validation_rejects_a_truncated_file_with_a_valid_header() -> None:
    assert valid_png_bytes(PNG_BYTES)
    assert not valid_png_bytes(PNG_BYTES[:-12])
