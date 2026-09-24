"""Offline test of the /api/course/render-video endpoint (rendering is monkeypatched)."""
import os
import time

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

os.environ.setdefault("OPENAI_API_KEY", "dummy")
import api_server  # noqa: E402
import src.video as video_mod  # noqa: E402


def test_render_video_endpoint_runs_background_task(tmp_path, monkeypatch):
    exp = tmp_path / "exp" / "demo"
    (exp / "chapter_1").mkdir(parents=True)
    (exp / "chapter_1" / "script.md").write_text("## Section 1: Only\nHello.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(api_server, "tasks", {"parent": {"task_id": "parent", "status": "completed", "exp_name": "demo", "course_name": "Demo"}})
    monkeypatch.setattr(api_server, "task_logs", {})
    monkeypatch.setattr("src.video_media._TOOL_CACHE", {"ffmpeg": "/bin/true", "ffprobe": "/bin/true"})

    seen = {}

    def fake_render(exp_dir, *, options, course_name, chapters, log):
        seen.update(exp_dir=exp_dir, voice=options.voice, tts=options.tts_model, course=course_name, chapters=chapters)
        log("rendering…")
        return [{"chapter_dir": f"{exp_dir}chapter_1", "video": "x.mp4", "duration_seconds": 1.0, "slides": 1}]

    monkeypatch.setattr(video_mod, "render_course_videos", fake_render)

    client = TestClient(api_server.app)
    r = client.post("/api/course/render-video/parent", json={"voice": "nova", "chapters": [1]}, headers={"X-OpenAI-API-Key": "sk-test"})
    assert r.status_code == 200, r.text
    vid_task = r.json()["task_id"]
    assert r.json()["parent_task_id"] == "parent"
    # TestClient runs background tasks before returning
    for _ in range(50):
        if api_server.tasks[vid_task]["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)
    task = api_server.tasks[vid_task]
    assert task["status"] == "completed", task
    assert task["exp_name"] == "demo" and task["videos"][0]["video"] == "x.mp4"
    assert seen == {"exp_dir": "./exp/demo/", "voice": "nova", "tts": "gpt-4o-mini-tts", "course": "Demo", "chapters": [1]}
    assert os.environ.get("OPENAI_API_KEY") == "dummy"  # key restored after the job

    r404 = client.post("/api/course/render-video/nope", headers={"X-OpenAI-API-Key": "sk-test"})
    assert r404.status_code == 404
