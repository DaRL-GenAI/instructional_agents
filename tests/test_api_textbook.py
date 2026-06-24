"""Tests for the api_server.py textbook-grounding additions.

Covers:
 - `CourseRequest` accepts `textbook_path` (default None)
 - `_validate_textbook_path` rejects out-of-root + missing paths
 - `GET /api/textbooks/list` returns whatever's under the allowed roots
 - The endpoint is callable with no auth (path-validation only — no LLM)

These tests don't run a real course generation. They exercise the plumbing.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _import_app():
    """Late import so import-time errors surface inside tests, not collection."""
    from api_server import app, _validate_textbook_path, ALLOWED_TEXTBOOK_ROOTS
    return app, _validate_textbook_path, ALLOWED_TEXTBOOK_ROOTS


class TestCourseRequestField:
    def test_accepts_textbook_path(self):
        from api_server import CourseRequest
        req = CourseRequest(course_name="X", textbook_path="data/textbooks/foo")
        assert req.textbook_path == "data/textbooks/foo"

    def test_textbook_path_defaults_to_none(self):
        from api_server import CourseRequest
        req = CourseRequest(course_name="X")
        assert req.textbook_path is None


class TestPathValidation:
    def test_none_passes_through(self):
        _, validate, _ = _import_app()
        assert validate(None) is None
        assert validate("") is None

    def test_outside_allowed_roots_rejected(self):
        _, validate, _ = _import_app()
        with pytest.raises(HTTPException) as exc:
            validate("/etc/passwd")
        assert exc.value.status_code == 400
        assert "data/textbooks" in exc.value.detail

    def test_path_traversal_rejected(self):
        _, validate, _ = _import_app()
        # `..` should resolve away — the resulting absolute path is unlikely
        # to land under data/textbooks/ or data/repos/, so this is rejected.
        with pytest.raises(HTTPException):
            validate("data/textbooks/../../../etc/passwd")

    def test_missing_path_rejected(self):
        _, validate, _ = _import_app()
        with pytest.raises(HTTPException) as exc:
            validate("data/textbooks/this_definitely_does_not_exist_xyz")
        assert exc.value.status_code == 400
        assert "does not exist" in exc.value.detail

    def test_real_textbook_under_textbooks_root_accepted(self):
        # Han Data Mining 3e directory — the canonical test target. Skip when
        # absent (not all clones have it).
        han = Path(__file__).resolve().parents[1] / "data" / "textbooks" / "han_data_mining_3e"
        if not han.exists():
            pytest.skip("Han textbook not present")
        _, validate, _ = _import_app()
        canon = validate(str(han))
        assert canon is not None
        assert Path(canon).resolve() == han.resolve()


class TestListEndpoint:
    def test_returns_textbooks_key(self):
        app, _, _ = _import_app()
        client = TestClient(app)
        resp = client.get("/api/textbooks/list")
        assert resp.status_code == 200
        body = resp.json()
        assert "textbooks" in body
        assert isinstance(body["textbooks"], list)

    def test_entries_have_expected_shape(self):
        app, _, _ = _import_app()
        client = TestClient(app)
        body = client.get("/api/textbooks/list").json()
        for entry in body["textbooks"]:
            assert "id" in entry
            assert "title" in entry
            assert "path" in entry
            assert "kind" in entry
            assert entry["kind"] in ("file", "directory")
            # Every returned path must validate (sanity check that
            # endpoint output round-trips through the path guard).
            _, validate, _ = _import_app()
            assert validate(entry["path"]) is not None

    def test_includes_han_if_present(self):
        han = Path(__file__).resolve().parents[1] / "data" / "textbooks" / "han_data_mining_3e"
        if not han.exists():
            pytest.skip("Han textbook not present")
        app, _, _ = _import_app()
        body = TestClient(app).get("/api/textbooks/list").json()
        han_entries = [e for e in body["textbooks"] if "han" in e["id"].lower()]
        assert len(han_entries) >= 1, "Han should appear in the list when present"

    def test_includes_agentic_if_present(self):
        agentic = (
            Path(__file__).resolve().parents[1]
            / "data" / "repos" / "agentic_design_patterns"
            / "Agentic_Design_Patterns.pdf"
        )
        if not agentic.exists():
            pytest.skip("Agentic PDF not present")
        app, _, _ = _import_app()
        body = TestClient(app).get("/api/textbooks/list").json()
        agentic_entries = [e for e in body["textbooks"] if "agentic" in e["id"].lower()]
        assert len(agentic_entries) >= 1, "Agentic should appear when present"
        # Single-PDF directory should resolve to the FILE, not the dir.
        assert any(e["kind"] == "file" for e in agentic_entries)


class TestGenerateEndpointRejectsBadTextbookPath:
    """The /api/course/generate handler must validate textbook_path up
    front (before queueing a background task) so bad input returns 400
    immediately rather than 200 + a task that fails later in logs.
    """

    def test_bad_path_returns_400(self):
        app, _, _ = _import_app()
        client = TestClient(app)
        resp = client.post(
            "/api/course/generate",
            json={
                "course_name": "X",
                "textbook_path": "/etc/passwd",
                "exp_name": "test_validation",
            },
            headers={"X-OpenAI-API-Key": "sk-fake-just-for-validation-test"},
        )
        assert resp.status_code == 400
        assert "data/textbooks" in resp.text or "data/repos" in resp.text

    def test_missing_path_returns_400(self):
        app, _, _ = _import_app()
        client = TestClient(app)
        resp = client.post(
            "/api/course/generate",
            json={
                "course_name": "X",
                "textbook_path": "data/textbooks/does_not_exist_zzz",
                "exp_name": "test_validation",
            },
            headers={"X-OpenAI-API-Key": "sk-fake-just-for-validation-test"},
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.text

    def test_no_textbook_path_does_not_error(self):
        # Vanilla path: when textbook_path is omitted, validation no-ops
        # and the request proceeds (the task itself may still fail later
        # for unrelated reasons, but the handler should accept it with 200).
        app, _, _ = _import_app()
        client = TestClient(app)
        resp = client.post(
            "/api/course/generate",
            json={"course_name": "X", "exp_name": "test_vanilla_accept"},
            headers={"X-OpenAI-API-Key": "sk-fake-just-for-acceptance-test"},
        )
        assert resp.status_code == 200
        assert "task_id" in resp.json()


class TestUploadEndpoint:
    """POST /api/textbooks/upload — file upload for textbook grounding.

    Covers the validation chain (extension, magic header, size, filename
    sanitisation) and confirms the returned path round-trips through the
    path validator so it can be used as `textbook_path` on a follow-up
    `POST /api/course/generate`.
    """

    @pytest.fixture
    def client(self):
        app, _, _ = _import_app()
        return TestClient(app)

    def _cleanup_uploaded(self):
        # Remove any test artefacts under data/textbooks/uploaded_*.
        # These can be either single files (uploaded_<token>_<name>.pdf)
        # or directories (uploaded_<token>/ containing multiple files).
        import shutil
        root = Path(__file__).resolve().parents[1] / "data" / "textbooks"
        for p in root.glob("uploaded_*"):
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
            except OSError:
                pass

    # Smallest valid PDF that PyMuPDF can parse — reused across tests.
    _VALID_PDF = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000056 00000 n \n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n107\n%%EOF\n"
    )

    def test_pdf_upload_round_trips(self, client):
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[("files", ("sample.pdf", self._VALID_PDF, "application/pdf"))],
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            for key in ("id", "title", "path", "kind", "size_bytes"):
                assert key in body, f"missing {key}"
            assert body["kind"] == "file"
            assert body["path"].endswith(".pdf")
            # The returned path must validate as a usable textbook_path.
            _, validate, _ = _import_app()
            assert validate(body["path"]) is not None
            assert Path(body["path"]).exists()
        finally:
            self._cleanup_uploaded()

    def test_markdown_upload_round_trips(self, client):
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[("files", ("notes.md", b"# Chapter 1\n\nSome content.\n", "text/markdown"))],
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["path"].endswith(".md")
        finally:
            self._cleanup_uploaded()

    def test_unsupported_extension_rejected(self, client):
        resp = client.post(
            "/api/textbooks/upload",
            files=[("files", ("evil.exe", b"MZ\x90\x00", "application/octet-stream"))],
        )
        assert resp.status_code == 400
        assert "extension" in resp.text.lower()

    def test_pdf_magic_header_enforced(self, client):
        # Renamed .docx (no %PDF magic) → rejected.
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[("files", ("renamed.pdf", b"PK\x03\x04 not a pdf", "application/pdf"))],
            )
            assert resp.status_code == 400
            assert "PDF" in resp.text
        finally:
            self._cleanup_uploaded()

    def test_empty_filename_rejected(self, client):
        resp = client.post(
            "/api/textbooks/upload",
            files=[("files", ("", b"%PDF-1.4", "application/pdf"))],
        )
        # FastAPI's UploadFile schema rejects empty filenames with 422 before
        # the handler runs; our own check would also yield 400. Either is
        # acceptable — what matters is the request doesn't succeed.
        assert resp.status_code in (400, 422)

    def test_filename_sanitisation(self, client):
        # Slashes / special chars get folded to underscores.
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[("files", ("../../etc/evil name!.pdf", b"%PDF-1.4\n", "application/pdf"))],
            )
            assert resp.status_code == 200, resp.text
            path = resp.json()["path"]
            assert "/etc/evil" not in path
            assert "..." not in path
            assert Path(path).parent.name == "textbooks"
        finally:
            self._cleanup_uploaded()

    # --- Multi-file upload ---

    def test_multi_pdf_upload_creates_directory(self, client):
        """Several PDFs uploaded together → saved into one subdirectory,
        ingestable as a multi-chapter textbook."""
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[
                    ("files", ("01_intro.pdf", self._VALID_PDF, "application/pdf")),
                    ("files", ("02_data.pdf", self._VALID_PDF, "application/pdf")),
                    ("files", ("03_models.pdf", self._VALID_PDF, "application/pdf")),
                ],
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["kind"] == "directory"
            assert body["n_files"] == 3
            assert body["n_pdfs"] == 3
            target_dir = Path(body["path"])
            assert target_dir.is_dir()
            saved = sorted(p.name for p in target_dir.glob("*.pdf"))
            assert saved == ["01_intro.pdf", "02_data.pdf", "03_models.pdf"]
            _, validate, _ = _import_app()
            assert validate(body["path"]) is not None
        finally:
            self._cleanup_uploaded()

    def test_mixed_pdf_md_batch_rejected(self, client):
        """The textbook ingester refuses mixed-content directories; we
        block at the API boundary instead of letting it fail later."""
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[
                    ("files", ("ch1.pdf", self._VALID_PDF, "application/pdf")),
                    ("files", ("ch2.md", b"# Chapter 2\n", "text/markdown")),
                ],
            )
            assert resp.status_code == 400
            assert "Mixed" in resp.text
        finally:
            self._cleanup_uploaded()

    def test_duplicate_stems_deduplicated(self, client):
        """Two files with the same sanitised stem → the second gets _2."""
        try:
            resp = client.post(
                "/api/textbooks/upload",
                files=[
                    ("files", ("chapter.pdf", self._VALID_PDF, "application/pdf")),
                    ("files", ("chapter.pdf", self._VALID_PDF, "application/pdf")),
                ],
            )
            assert resp.status_code == 200, resp.text
            target_dir = Path(resp.json()["path"])
            saved = sorted(p.name for p in target_dir.glob("*.pdf"))
            assert saved == ["chapter.pdf", "chapter_2.pdf"]
        finally:
            self._cleanup_uploaded()
