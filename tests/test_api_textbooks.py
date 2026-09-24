"""Tests for the textbook-grounding API surface in api_server.py.

Covers /api/textbooks/upload (API-key requirement, single and multi-file
uploads, validation) and /api/textbooks/list, plus the textbook_path
validation used by /api/course/generate. Uploads are redirected to a
temporary directory so nothing lands in the repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("httpx")

import api_server  # noqa: E402
from fastapi import HTTPException  # noqa: E402

HEADERS = {"X-OpenAI-API-Key": "sk-test-not-real"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(api_server, "UPLOADED_TEXTBOOK_DIR", tmp_path / "data" / "textbooks")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return fastapi_testclient.TestClient(api_server.app)


def _md(name="book.md", body=b"# Chapter 1: Intro\n\nSome prose.\n"):
    return ("files", (name, body, "text/markdown"))


class TestUploadRequiresApiKey:
    def test_missing_key_is_rejected_before_writing(self, client, tmp_path):
        r = client.post("/api/textbooks/upload", files=[_md()])
        assert r.status_code == 400
        assert "API Key" in r.json()["detail"]
        assert not (tmp_path / "data" / "textbooks").exists()

    def test_env_key_is_accepted_like_course_generate(self, client, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
        r = client.post("/api/textbooks/upload", files=[_md()])
        assert r.status_code == 200


class TestUpload:
    def test_single_markdown_file(self, client, tmp_path):
        r = client.post("/api/textbooks/upload", files=[_md("My Book.md")], headers=HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["kind"] == "file" and data["n_files"] == 1
        saved = Path(data["path"])
        assert saved.exists()
        assert saved.parent == (tmp_path / "data" / "textbooks").resolve()
        assert saved.name.startswith("uploaded_") and saved.name.endswith("_My_Book.md")

    def test_multi_file_upload_becomes_directory(self, client):
        files = [_md("ch1.md"), _md("ch2.md"), _md("ch1.md")]
        r = client.post("/api/textbooks/upload", files=files, headers=HEADERS)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["kind"] == "directory" and data["n_files"] == 3
        names = sorted(p.name for p in Path(data["path"]).iterdir())
        assert names == ["ch1.md", "ch1_2.md", "ch2.md"]

    def test_mixed_kinds_rejected(self, client):
        files = [_md("a.md"), ("files", ("b.pdf", b"%PDF-1.4 x", "application/pdf"))]
        r = client.post("/api/textbooks/upload", files=files, headers=HEADERS)
        assert r.status_code == 400
        assert "Mixed" in r.json()["detail"]

    def test_bad_extension_rejected(self, client):
        r = client.post("/api/textbooks/upload",
                        files=[("files", ("x.docx", b"zzz", "application/octet-stream"))],
                        headers=HEADERS)
        assert r.status_code == 400

    def test_fake_pdf_rejected_and_removed(self, client, tmp_path):
        r = client.post("/api/textbooks/upload",
                        files=[("files", ("x.pdf", b"not a pdf", "application/pdf"))],
                        headers=HEADERS)
        assert r.status_code == 400
        assert not list((tmp_path / "data" / "textbooks").glob("*.pdf"))

    def test_uploaded_textbook_is_listed(self, client):
        client.post("/api/textbooks/upload", files=[_md("listed.md")], headers=HEADERS)
        r = client.get("/api/textbooks/list")
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["textbooks"]]
        assert any(i.endswith("_listed") for i in ids)


class TestTextbookPathValidation:
    def test_none_passes_through(self):
        assert api_server._validate_textbook_path(None) is None

    def test_path_outside_root_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(api_server, "UPLOADED_TEXTBOOK_DIR", tmp_path / "data" / "textbooks")
        outside = tmp_path / "elsewhere.md"
        outside.write_text("x")
        with pytest.raises(HTTPException) as exc:
            api_server._validate_textbook_path(str(outside))
        assert exc.value.status_code == 400

    def test_missing_path_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(api_server, "UPLOADED_TEXTBOOK_DIR", tmp_path / "data" / "textbooks")
        with pytest.raises(HTTPException):
            api_server._validate_textbook_path(str(tmp_path / "data" / "textbooks" / "nope.pdf"))

    def test_relative_path_resolves_against_repo_root(self, monkeypatch):
        # A relative path is interpreted relative to the repository, not cwd.
        monkeypatch.chdir("/")
        root = api_server.REPO_ROOT
        rel = "data/textbooks/does_not_exist.pdf"
        with pytest.raises(HTTPException) as exc:
            api_server._validate_textbook_path(rel)
        assert str(root) not in exc.value.detail  # message echoes the user's input
        assert exc.value.detail.endswith(rel)

    def test_generate_rejects_bad_textbook_path_before_creating_task(self, client, tmp_path):
        n_tasks = len(api_server.tasks)
        r = client.post("/api/course/generate", headers=HEADERS,
                        json={"course_name": "X", "textbook_path": str(tmp_path / "missing.pdf")})
        assert r.status_code == 400
        assert len(api_server.tasks) == n_tasks
