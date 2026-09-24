"""
FastAPI server for Instructional Agents
Provides REST API endpoints for course generation
"""
import os
import json
import uuid
import asyncio
import sys
import io
from typing import Optional, Dict, Any, List, List
from pathlib import Path
from datetime import datetime
from queue import Queue
from threading import Thread

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Header, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional as Opt
import uvicorn

from run import (
    run_instructional_design,
    run_optimization,
    run_evaluation,
    run_refinement,
)
from src import __version__
from src.pdf_processor import PDFSlideProcessor
from src.ADDIE_optimize import ADDIEOptimizer
from src.textbook_reference import TextbookReferenceBuilder
import tempfile
import shutil

# Initialize FastAPI app
app = FastAPI(
    title="Instructional Agents API",
    description="API for automated course material generation",
    version=__version__
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Task storage (in production, use Redis or database)
tasks: Dict[str, Dict[str, Any]] = {}

# Log queues for each task (in production, use Redis Streams)
task_logs: Dict[str, Queue] = {}

# Request/Response models
class CourseRequest(BaseModel):
    course_name: str = Field(..., description="Name of the course to generate")
    model_name: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    exp_name: str = Field(default="default", description="Experiment name for output")
    copilot: Optional[bool] = Field(default=False, description="Enable copilot mode")
    catalog: Optional[str] = Field(default=None, description="Catalog name to use")
    catalog_data: Optional[Dict[str, Any]] = Field(default=None, description="Catalog data as JSON object")
    generate_pptx: Optional[bool] = Field(default=False, description="Also generate PPTX slides")
    run_evaluation: Optional[bool] = Field(default=False, description="Run evaluation after generation")
    run_refinement: Optional[bool] = Field(default=False, description="Run refinement after evaluation")
    refinement_threshold: Optional[float] = Field(default=3.0, description="Score threshold for selecting files to refine")
    refinement_retries: Optional[int] = Field(default=3, description="Maximum refinement retries per selected file")
    refinement_route: Optional[str] = Field(default="all", description="Refinement route to run")
    textbook_path: Optional[str] = Field(
        default=None,
        description=(
            "Path to a textbook for grounded course generation (a PDF file, a "
            "Markdown file, or a directory of either) — normally the `path` "
            "returned by POST /api/textbooks/upload. Must resolve to a path under "
            "data/textbooks/. When omitted, generation runs exactly as in the "
            "vanilla pipeline."
        ),
    )
    generate_video: Optional[bool] = Field(default=False, description="Also render narrated lecture videos (TTS + ffmpeg)")
    video_voice: Optional[str] = Field(default="alloy", description="TTS voice for lecture videos")
    video_tts_model: Optional[str] = Field(default="gpt-4o-mini-tts", description="TTS model for lecture videos")
    video_burn_subtitles: Optional[bool] = Field(default=False, description="Burn captions into the video instead of a soft track")


class VideoRequest(BaseModel):
    voice: Optional[str] = Field(default="alloy", description="TTS voice")
    tts_model: Optional[str] = Field(default="gpt-4o-mini-tts", description="TTS model")
    burn_subtitles: Optional[bool] = Field(default=False, description="Burn captions into the frames")
    chapters: Optional[List[int]] = Field(default=None, description="Chapter numbers to render (default: all)")


class OptimizeRequest(BaseModel):
    storage_id: str = Field(..., description="ID of the stored PDF files")
    user_requirements: str = Field(..., description="User's requirements for improvement")
    model_name: str = Field(default="gpt-4o-mini", description="OpenAI model to use")
    exp_name: str = Field(default="default", description="Experiment name for output")
    chapter_name: Optional[str] = Field(default=None, description="Specific chapter to optimize (None = all)")
    mode: str = Field(default="regenerate", description="Improvement strategy: 'regenerate' (per-slide full rewrite) or 'refine' (localized frame-level rewrite)")

class TaskStatus(BaseModel):
    task_id: str
    status: str  # pending, running, completed, failed
    progress: int  # 0-100
    current_stage: Optional[str] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str
    exp_name: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str

# Health check endpoint
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    # Check if OpenAI API key is set
    has_api_key = bool(os.environ.get("OPENAI_API_KEY"))
    status = "healthy" if has_api_key else "degraded"
    
    return {
        "status": status,
        "version": __version__,
        "timestamp": datetime.now().isoformat()
    }

# Helper function to get API key from header or environment
def get_api_key(x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")) -> str:
    """
    Get OpenAI API key from request header or environment variable
    Header takes precedence over environment variable
    """
    if x_openai_api_key:
        return x_openai_api_key
    env_key = os.environ.get("OPENAI_API_KEY")
    if not env_key:
        raise HTTPException(
            status_code=400,
            detail="OpenAI API Key is required. Please provide it in X-OpenAI-API-Key header or set OPENAI_API_KEY environment variable."
        )
    return env_key

# ---------------------------------------------------------------------------
# Textbook grounding (opt-in): upload + list textbooks used by
# ``CourseRequest.textbook_path``. Distinct from /api/textbook/catalog, which
# seeds a *catalog* from a textbook excerpt (no LLM, no grounding).
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent
# Uploaded textbooks live here (gitignored). All paths are resolved against
# the repository root, not the process cwd, and confined to this directory so
# the API surface cannot be used for path traversal.
UPLOADED_TEXTBOOK_DIR = REPO_ROOT / "data" / "textbooks"
ALLOWED_TEXTBOOK_EXTENSIONS = {".pdf", ".md", ".markdown"}
MAX_TEXTBOOK_UPLOAD_MB = 100


def _validate_textbook_path(textbook_path: Optional[str]) -> Optional[str]:
    """Validate that `textbook_path` exists and is under data/textbooks/.

    Returns the canonical absolute path on success; ``None`` passes through
    unchanged (vanilla pipeline). Raises HTTPException(400) otherwise.
    Relative paths are resolved against the repository root.
    """
    if not textbook_path:
        return None
    p = Path(textbook_path).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    p = p.resolve()
    root = UPLOADED_TEXTBOOK_DIR.resolve()
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"textbook_path does not exist: {textbook_path}")
    if p != root and root not in p.parents:
        raise HTTPException(
            status_code=400,
            detail=f"textbook_path must resolve to a path under data/textbooks/; got: {textbook_path}",
        )
    return str(p)


def _sanitise_stem(name: str) -> str:
    """Strip everything outside [A-Za-z0-9._-] from a filename stem."""
    import re as _re
    return _re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem).strip("._-")


def _list_available_textbooks() -> List[Dict[str, Any]]:
    """Enumerate ingestable textbook sources under data/textbooks/.

    A textbook is a top-level .pdf/.md file, or a sub-directory holding
    .pdf/.md files (each file = one chapter). A sub-directory with exactly
    one PDF is reported as that file so single-book chapter detection runs.
    """
    out: List[Dict[str, Any]] = []
    root = UPLOADED_TEXTBOOK_DIR
    if not root.exists():
        return out
    for entry in sorted(root.iterdir()):
        if entry.is_file() and entry.suffix.lower() in ALLOWED_TEXTBOOK_EXTENSIONS:
            out.append({
                "id": entry.stem,
                "title": entry.stem.replace("_", " ").replace("-", " ").title(),
                "path": str(entry.resolve()),
                "kind": "file",
            })
        elif entry.is_dir():
            pdfs = sorted(entry.glob("*.pdf"))
            mds = sorted(entry.glob("*.md")) + sorted(entry.glob("*.markdown"))
            if not pdfs and not mds:
                continue
            if len(pdfs) == 1 and not mds:
                target = pdfs[0]
                out.append({
                    "id": target.stem,
                    "title": target.stem.replace("_", " ").replace("-", " ").title(),
                    "path": str(target.resolve()),
                    "kind": "file",
                })
            else:
                out.append({
                    "id": entry.name,
                    "title": entry.name.replace("_", " ").replace("-", " ").title(),
                    "path": str(entry.resolve()),
                    "kind": "directory",
                    "n_pdfs": len(pdfs),
                    "n_mds": len(mds),
                })
    return out


async def _stream_to_disk(upload: UploadFile, target: Path, bytes_remaining: int) -> int:
    """Stream an UploadFile to `target` within a shared byte budget.

    Returns bytes written; raises HTTPException(413) when the budget is
    exceeded. The caller unlinks `target` on failure.
    """
    written = 0
    with open(target, "wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > bytes_remaining:
                raise HTTPException(
                    status_code=413,
                    detail=f"Combined upload exceeds {MAX_TEXTBOOK_UPLOAD_MB} MB limit.",
                )
            out.write(chunk)
    return written


@app.get("/api/textbooks/list")
async def list_textbooks():
    """List textbooks available for grounded course generation."""
    return {"textbooks": _list_available_textbooks()}


@app.post("/api/textbooks/upload")
async def upload_textbook(
    files: List[UploadFile] = File(...),
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key"),
):
    """Upload one or more PDF / Markdown files for grounded generation.

    Requires the same ``X-OpenAI-API-Key`` header (or env key) as
    ``/api/course/generate``. A single file lands at
    ``data/textbooks/uploaded_<token>_<name>.<ext>`` (``kind=file``); several
    files land in ``data/textbooks/uploaded_<token>/`` (``kind=directory``,
    one chapter per file). All files in one batch must be the same kind
    (all PDF or all Markdown); the combined size is capped at 100 MB; PDFs
    are sniffed for the ``%PDF`` header. The returned ``path`` is what to
    pass as ``textbook_path`` to ``/api/course/generate``.
    """
    get_api_key(x_openai_api_key)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    classified: list = []  # (file, ext, safe_stem)
    pdf_count = md_count = 0
    for f in files:
        if not f.filename or not f.filename.strip():
            raise HTTPException(status_code=400, detail="Empty filename in upload batch.")
        ext = Path(f.filename).suffix.lower()
        if ext not in ALLOWED_TEXTBOOK_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported extension {ext!r} in file {f.filename!r}. "
                       "Allowed: " + ", ".join(sorted(ALLOWED_TEXTBOOK_EXTENSIONS)),
            )
        safe_stem = _sanitise_stem(f.filename)
        if not safe_stem:
            raise HTTPException(status_code=400, detail=f"Filename {f.filename!r} has no usable characters.")
        if ext == ".pdf":
            pdf_count += 1
        else:
            md_count += 1
        classified.append((f, ext, safe_stem))
    if pdf_count and md_count:
        raise HTTPException(
            status_code=400,
            detail="Mixed PDF + Markdown upload is not supported: the textbook ingester "
                   f"requires one kind per directory ({pdf_count} PDF / {md_count} Markdown received).",
        )

    UPLOADED_TEXTBOOK_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    max_bytes = MAX_TEXTBOOK_UPLOAD_MB * 1024 * 1024

    def _check_pdf_magic(target: Path, name: str) -> None:
        with open(target, "rb") as fh:
            if not fh.read(8).startswith(b"%PDF"):
                raise HTTPException(status_code=400, detail=f"File {name!r} does not start with the %PDF header.")

    if len(classified) == 1:
        f, ext, safe_stem = classified[0]
        target = UPLOADED_TEXTBOOK_DIR / f"uploaded_{token}_{safe_stem}{ext}"
        try:
            total = await _stream_to_disk(f, target, max_bytes)
            if ext == ".pdf":
                _check_pdf_magic(target, f.filename)
        except HTTPException:
            target.unlink(missing_ok=True)
            raise
        except Exception as e:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")
        return {
            "id": target.stem,
            "title": safe_stem.replace("_", " ").replace("-", " ").title(),
            "path": _validate_textbook_path(str(target)),
            "kind": "file",
            "n_files": 1,
            "size_bytes": total,
            "size_mb": round(total / (1024 * 1024), 2),
        }

    upload_dir = UPLOADED_TEXTBOOK_DIR / f"uploaded_{token}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    written: list = []
    seen: set = set()
    try:
        for f, ext, safe_stem in classified:
            stem, dup = safe_stem, 2
            while stem in seen:  # foo.pdf + foo.pdf -> foo.pdf + foo_2.pdf
                stem = f"{safe_stem}_{dup}"; dup += 1
            seen.add(stem)
            target = upload_dir / f"{stem}{ext}"
            total += await _stream_to_disk(f, target, max_bytes - total)
            written.append(target)
            if ext == ".pdf":
                _check_pdf_magic(target, f.filename)
    except Exception as e:
        for w in written:
            w.unlink(missing_ok=True)
        if upload_dir.exists() and not any(upload_dir.iterdir()):
            upload_dir.rmdir()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}")
    return {
        "id": upload_dir.name,
        "title": f"Uploaded {len(classified)} files ({token})",
        "path": _validate_textbook_path(str(upload_dir)),
        "kind": "directory",
        "n_files": len(classified),
        "n_pdfs": pdf_count,
        "n_mds": md_count,
        "size_bytes": total,
        "size_mb": round(total / (1024 * 1024), 2),
    }


# API endpoints
@app.post("/api/course/generate")
async def generate_course(
    request: CourseRequest,
    background_tasks: BackgroundTasks,
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """
    Start a new course generation task
    """
    # Get API key from header or environment
    api_key = get_api_key(x_openai_api_key)

    # Validate the optional textbook path up front so a bad path returns 400
    # before a task is created; the canonical path is written back so the
    # background task uses the validated value (None = vanilla pipeline).
    request.textbook_path = _validate_textbook_path(request.textbook_path)
    
    task_id = str(uuid.uuid4())
    
    # Initialize task
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "current_stage": "Initializing",
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "exp_name": request.exp_name,
        "course_name": request.course_name
    }
    
    # Initialize log queue BEFORE starting the task
    if task_id not in task_logs:
        task_logs[task_id] = Queue()
    
    # Update status to "starting" immediately
    tasks[task_id]["status"] = "starting"
    tasks[task_id]["current_stage"] = "Task queued, initializing..."
    tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    # Start background task
    # Use BackgroundTasks which is the recommended way for FastAPI
    # The task will be executed after the response is sent
    background_tasks.add_task(run_generation_task, task_id, request, api_key)
    
    return {
        "task_id": task_id,
        "status": "started",
        "message": "Course generation started"
    }

@app.post("/api/course/render-video/{task_id}")
async def render_lecture_videos(
    task_id: str,
    background_tasks: BackgroundTasks,
    request: VideoRequest = None,
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """Render narrated lecture videos for a completed generation task (runs in the background).

    Returns a new task id whose status/files can be polled with the usual
    /api/course/status and /api/course/results endpoints.
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    api_key = get_api_key(x_openai_api_key)
    request = request or VideoRequest()
    exp_name = tasks[task_id].get("exp_name", "default")
    exp_dir = f"./exp/{exp_name}/"
    if not os.path.exists(exp_dir):
        raise HTTPException(status_code=404, detail=f"Experiment directory not found: {exp_dir}")
    from src.video_media import ffmpeg_available
    if not ffmpeg_available():
        raise HTTPException(status_code=503, detail="ffmpeg/ffprobe not installed on the server")

    video_task_id = str(uuid.uuid4())
    tasks[video_task_id] = {
        "task_id": video_task_id,
        "status": "pending",
        "progress": 0,
        "current_stage": "Queued: lecture video rendering",
        "error": None,
        "created_at": datetime.now().isoformat(),
        "exp_name": exp_name,
        "course_name": tasks[task_id].get("course_name", ""),
        "parent_task_id": task_id,
        "kind": "video",
    }
    task_logs[video_task_id] = Queue()
    background_tasks.add_task(run_video_task, video_task_id, request, api_key)
    return {"task_id": video_task_id, "parent_task_id": task_id, "status": "started", "message": "Lecture video rendering started"}


async def run_video_task(task_id: str, request: VideoRequest, api_key: str):
    """Background job: render lecture videos for tasks[task_id]['exp_name']."""
    from src.video import VideoOptions, render_course_videos
    task = tasks[task_id]
    original_key = os.environ.get("OPENAI_API_KEY")
    try:
        os.environ["OPENAI_API_KEY"] = api_key
        task["status"] = "running"
        task["current_stage"] = "Rendering lecture videos"
        task["progress"] = 5
        log_queue = task_logs.get(task_id)

        def log(msg: str):
            print(msg)
            if log_queue is not None:
                log_queue.put(msg)

        options = VideoOptions(tts_model=request.tts_model, voice=request.voice, burn_subtitles=bool(request.burn_subtitles))
        results = await asyncio.to_thread(
            render_course_videos, f"./exp/{task['exp_name']}/",
            options=options, course_name=task.get("course_name", ""), chapters=request.chapters, log=log,
        )
        failed = [r for r in results if "error" in r]
        task["videos"] = results
        task["progress"] = 100
        if results and len(failed) == len(results):
            task["status"] = "failed"
            task["error"] = failed[0]["error"]
            task["current_stage"] = "Failed"
        else:
            task["status"] = "completed"
            task["current_stage"] = f"Completed ({len(results) - len(failed)}/{len(results)} chapter videos)"
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)
        task["current_stage"] = "Failed"
    finally:
        if original_key is not None:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]
        if task_id in task_logs:
            task_logs[task_id].put(None)


@app.post("/api/course/convert-pptx/{task_id}")
async def convert_to_pptx(task_id: str):
    """Convert existing .tex files to .pptx for a completed task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    exp_name = task.get("exp_name", "default")
    exp_dir = f"./exp/{exp_name}/"

    if not os.path.exists(exp_dir):
        raise HTTPException(status_code=404, detail=f"Experiment directory not found: {exp_dir}")

    from src.latex_to_pptx import LaTeXToPPTXConverter
    converter = LaTeXToPPTXConverter()
    results = converter.convert_directory(exp_dir)

    return {
        "task_id": task_id,
        "converted_files": len(results),
        "files": results
    }

@app.get("/api/course/status/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    Get the status of a course generation task
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return tasks[task_id]

@app.get("/api/course/results/{task_id}/files")
async def get_result_files(task_id: str):
    """
    Get list of generated files for a task (can be called during generation)
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    exp_name = task.get("exp_name", "default")
    exp_dir = Path(f"./exp/{exp_name}")
    
    if not exp_dir.exists():
        return {
            "task_id": task_id,
            "exp_name": exp_name,
            "files": [],
            "status": task["status"],
            "message": "Output directory not found"
        }
    
    # Collect all files (even if task is still running)
    files = []
    for file_path in exp_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith('.'):
            relative_path = file_path.relative_to(exp_dir)
            try:
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(relative_path),
                    "size": stat.st_size,
                    "type": file_path.suffix,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except Exception:
                # Skip files that can't be accessed
                continue
    
    # Sort by modification time (newest first)
    files.sort(key=lambda x: x.get("modified", ""), reverse=True)
    
    return {
        "task_id": task_id,
        "exp_name": exp_name,
        "files": files,
        "status": task["status"],
        "total_files": len(files)
    }

@app.get("/api/course/logs/{task_id}/test")
async def test_log_queue(task_id: str):
    """
    Test endpoint to check if log queue is working
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Add a test message to the queue
    if task_id not in task_logs:
        task_logs[task_id] = Queue()
    
    task_logs[task_id].put("🧪 Test log message from API")
    
    return {
        "task_id": task_id,
        "queue_size": task_logs[task_id].qsize(),
        "message": "Test message added to queue"
    }

@app.get("/api/course/logs/{task_id}/stream")
async def stream_task_logs(task_id: str):
    """
    Stream task logs using Server-Sent Events (SSE)
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    async def event_generator():
        # Create log queue if it doesn't exist
        if task_id not in task_logs:
            task_logs[task_id] = Queue()
        
        log_queue = task_logs[task_id]
        
        # Send initial connection message
        try:
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Log stream connected'})}\n\n"
        except Exception as e:
            print(f"Error sending connection message: {e}")
            return
        
        # Keep sending logs until task is completed or failed
        while True:
            try:
                # Check task status
                task = tasks.get(task_id)
                if task and task["status"] in ["completed", "failed"]:
                    # Send final message and close
                    yield f"data: {json.dumps({'type': 'complete', 'status': task['status']})}\n\n"
                    break
                
                # Try to get log from queue (non-blocking)
                # Process multiple logs if available
                logs_sent = False
                for _ in range(20):  # Process up to 20 logs at once
                    try:
                        log_message = log_queue.get_nowait()
                        # Ensure message is a string
                        if not isinstance(log_message, str):
                            log_message = str(log_message)
                        yield f"data: {json.dumps({'type': 'log', 'message': log_message, 'timestamp': datetime.now().isoformat()})}\n\n"
                        logs_sent = True
                    except Exception as e:
                        # Queue is empty or other error
                        break
                
                if not logs_sent:
                    # No log available, send heartbeat occasionally
                    await asyncio.sleep(0.3)
                else:
                    # If we sent logs, don't sleep (process more immediately)
                    await asyncio.sleep(0.01)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/course/results/{task_id}/download/{file_path:path}")
async def download_file(task_id: str, file_path: str):
    """
    Download a specific file from the results
    """
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task = tasks[task_id]
    exp_name = task.get("exp_name", "default")
    full_path = Path(f"./exp/{exp_name}/{file_path}")
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type='application/octet-stream'
    )

@app.post("/api/catalog/upload")
async def upload_catalog(
    file: UploadFile = File(...),
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """
    Upload a catalog JSON file
    """
    # Validate API key (for consistency, though not strictly needed for upload)
    get_api_key(x_openai_api_key)
    
    try:
        content = await file.read()
        catalog_data = json.loads(content.decode('utf-8'))
        
        # Save to catalog directory
        catalog_dir = Path("catalog")
        catalog_dir.mkdir(exist_ok=True)
        
        # Generate unique filename
        filename = f"uploaded_{uuid.uuid4().hex[:8]}_{file.filename}"
        file_path = catalog_dir / filename
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(catalog_data, f, indent=2, ensure_ascii=False)
        
        return {
            "success": True,
            "filename": filename,
            "message": "Catalog uploaded successfully"
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading catalog: {str(e)}")

@app.post("/api/textbook/catalog")
async def build_textbook_catalog(
    file: UploadFile = File(...),
    course_name: str = Form(default="")
):
    """
    Build catalog-compatible reference data from an uploaded textbook file.

    This proof-of-concept extracts a bounded amount of text from PDF/TXT/MD
    input and converts it into the existing catalog schema. It does not call
    an LLM, so it can be used before starting a paid generation task.
    """
    allowed_suffixes = {".pdf", ".txt", ".md"}
    original_name = file.filename or "textbook.pdf"
    suffix = Path(original_name).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and Markdown textbook files are supported")

    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Textbook file is too large (max 50 MB)")

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / original_name
            temp_path.write_bytes(content)

            builder = TextbookReferenceBuilder()
            catalog_data = builder.build_catalog(temp_path, course_name=course_name)

        catalog_dir = Path("catalog")
        catalog_dir.mkdir(exist_ok=True)
        catalog_name = f"textbook_{uuid.uuid4().hex[:8]}"
        catalog_filename = f"{catalog_name}.json"
        catalog_path = catalog_dir / catalog_filename
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog_data, f, indent=2, ensure_ascii=False)

        return {
            "catalog_name": catalog_name,
            "filename": catalog_filename,
            "saved_path": str(catalog_path),
            "catalog_data": catalog_data,
            "message": "Textbook reference catalog generated successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing textbook: {str(e)}")

@app.get("/api/tasks/list")
async def list_tasks():
    """
    List all tasks (for debugging and testing)
    """
    task_list = []
    for task_id, task_info in tasks.items():
        log_queue_size = task_logs.get(task_id, Queue()).qsize() if task_id in task_logs else 0
        task_list.append({
            "task_id": task_id,
            "status": task_info.get("status"),
            "course_name": task_info.get("course_name"),
            "exp_name": task_info.get("exp_name"),
            "created_at": task_info.get("created_at"),
            "updated_at": task_info.get("updated_at"),
            "progress": task_info.get("progress", 0),
            "log_queue_size": log_queue_size
        })
    
    # Sort by created_at (newest first)
    task_list.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "total": len(task_list),
        "tasks": task_list
    }

@app.get("/api/catalog/list")
async def list_catalogs():
    """
    List available catalog files
    """
    catalog_dir = Path("catalog")
    if not catalog_dir.exists():
        return {"catalogs": []}
    
    catalogs = []
    for file_path in catalog_dir.glob("*.json"):
        catalogs.append({
            "name": file_path.stem,
            "filename": file_path.name,
            "size": file_path.stat().st_size,
            "modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
        })
    
    return {"catalogs": catalogs}

# ==================== Optimize Mode Endpoints ====================

@app.post("/api/optimize/upload")
async def upload_optimize_files(
    files: List[UploadFile] = File(...),
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """
    Upload PDF files for optimization. Returns a storage_id for subsequent operations.
    """
    get_api_key(x_openai_api_key)

    try:
        temp_dir = tempfile.mkdtemp()

        pdf_files = []
        for file in files:
            if file.filename and file.filename.endswith('.pdf'):
                file_path = os.path.join(temp_dir, file.filename)
                with open(file_path, 'wb') as f:
                    content = await file.read()
                    f.write(content)
                pdf_files.append(Path(file_path))

        if not pdf_files:
            shutil.rmtree(temp_dir)
            raise HTTPException(status_code=400, detail="No PDF files uploaded")

        storage_id = f"storage_{uuid.uuid4().hex[:12]}"

        processor = PDFSlideProcessor()
        metadata = processor.store_pdf_files(pdf_files, storage_id)

        shutil.rmtree(temp_dir)

        return {
            "success": True,
            "storage_id": storage_id,
            "total_files": metadata["total_files"],
            "message": f"Successfully stored {metadata['total_files']} PDF files."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error storing PDFs: {str(e)}")


@app.post("/api/optimize/start")
async def start_optimization(
    request: OptimizeRequest,
    background_tasks: BackgroundTasks,
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """
    Start an optimization task (background). Returns task_id for status polling.
    Uses the same task tracking pattern as /api/course/generate.
    """
    api_key = get_api_key(x_openai_api_key)

    task_id = str(uuid.uuid4())

    # Initialize task
    tasks[task_id] = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "current_stage": "Initializing",
        "error": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "exp_name": request.exp_name,
        "course_name": f"Optimize: {request.storage_id}"
    }

    if task_id not in task_logs:
        task_logs[task_id] = Queue()

    tasks[task_id]["status"] = "starting"
    tasks[task_id]["current_stage"] = "Task queued, initializing..."
    tasks[task_id]["updated_at"] = datetime.now().isoformat()

    background_tasks.add_task(run_optimization_task, task_id, request, api_key)

    return {
        "task_id": task_id,
        "status": "started",
        "message": "Optimization started"
    }


@app.get("/api/optimize/status/{task_id}", response_model=TaskStatus)
async def get_optimize_status(task_id: str):
    """Get the status of an optimization task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/api/optimize/logs/{task_id}/stream")
async def stream_optimize_logs(task_id: str):
    """Stream optimization task logs using SSE. Same pattern as course generation."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        if task_id not in task_logs:
            task_logs[task_id] = Queue()
        log_queue = task_logs[task_id]

        try:
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Log stream connected'})}\n\n"
        except Exception:
            return

        while True:
            try:
                task = tasks.get(task_id)
                if task and task["status"] in ["completed", "failed"]:
                    yield f"data: {json.dumps({'type': 'complete', 'status': task['status']})}\n\n"
                    break

                logs_sent = False
                for _ in range(20):
                    try:
                        log_message = log_queue.get_nowait()
                        if not isinstance(log_message, str):
                            log_message = str(log_message)
                        yield f"data: {json.dumps({'type': 'log', 'message': log_message, 'timestamp': datetime.now().isoformat()})}\n\n"
                        logs_sent = True
                    except Exception:
                        break

                if not logs_sent:
                    await asyncio.sleep(0.3)
                else:
                    await asyncio.sleep(0.01)

            except asyncio.CancelledError:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/optimize/results/{task_id}/files")
async def get_optimize_result_files(task_id: str):
    """Get list of generated files for an optimization task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    exp_name = task.get("exp_name", "default")
    exp_dir = Path(f"./exp/{exp_name}")

    if not exp_dir.exists():
        return {
            "task_id": task_id,
            "exp_name": exp_name,
            "files": [],
            "status": task["status"],
            "message": "Output directory not found"
        }

    files = []
    for file_path in exp_dir.rglob("*"):
        if file_path.is_file() and not file_path.name.startswith('.'):
            relative_path = file_path.relative_to(exp_dir)
            try:
                stat = file_path.stat()
                files.append({
                    "name": file_path.name,
                    "path": str(relative_path),
                    "size": stat.st_size,
                    "type": file_path.suffix,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except Exception:
                continue

    files.sort(key=lambda x: x.get("modified", ""), reverse=True)

    return {
        "task_id": task_id,
        "exp_name": exp_name,
        "files": files,
        "status": task["status"],
        "total_files": len(files)
    }


@app.get("/api/optimize/results/{task_id}/download/{file_path:path}")
async def download_optimize_file(task_id: str, file_path: str):
    """Download a specific file from optimization results."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    exp_name = task.get("exp_name", "default")
    full_path = Path(f"./exp/{exp_name}/{file_path}")

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=str(full_path),
        filename=full_path.name,
        media_type='application/octet-stream'
    )


@app.get("/api/optimize/storage/{storage_id}")
async def get_optimize_storage_info(
    storage_id: str,
    x_openai_api_key: Opt[str] = Header(None, alias="X-OpenAI-API-Key")
):
    """Get stored PDF files metadata."""
    get_api_key(x_openai_api_key)

    processor = PDFSlideProcessor()
    storage_dir = processor.output_dir / "temp_storage" / storage_id

    if not storage_dir.exists():
        raise HTTPException(status_code=404, detail="Storage not found")

    metadata_file = storage_dir / "metadata.json"
    if not metadata_file.exists():
        raise HTTPException(status_code=404, detail="Storage metadata not found")

    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    return metadata

# Custom stdout wrapper to capture logs
class LogCapture:
    def __init__(self, task_id: str, original_stdout):
        self.task_id = task_id
        self.original_stdout = original_stdout
        if task_id not in task_logs:
            task_logs[task_id] = Queue()
        self.log_queue = task_logs[task_id]
        self.buffer = ""  # Buffer for incomplete lines
    
    def write(self, text):
        # Write to original stdout first (so it appears in docker logs)
        self.original_stdout.write(text)
        self.original_stdout.flush()
        
        # Buffer the text
        if text:
            self.buffer += text
            
            # Process complete lines
            while '\n' in self.buffer:
                line, self.buffer = self.buffer.split('\n', 1)
                line = line.rstrip()
                if line:  # Only log non-empty lines
                    try:
                        self.log_queue.put_nowait(line)
                    except Exception as e:
                        # Queue is full or other error, log to stderr
                        import sys
                        print(f"Warning: Failed to add log to queue: {e}", file=sys.stderr)
    
    def flush(self):
        # Flush any remaining buffer
        if self.buffer.strip():
            try:
                self.log_queue.put_nowait(self.buffer.rstrip())
                self.buffer = ""
            except:
                pass
        self.original_stdout.flush()

# Background task function
async def run_generation_task(task_id: str, request: CourseRequest, api_key: str):
    """
    Run the course generation in background
    """
    # Initialize variables for cleanup
    original_stdout = None
    log_capture = None
    original_key = None
    
    try:
        # Immediately update status to show task has started (before any other operations)
        if task_id in tasks:
            tasks[task_id]["status"] = "starting"
            tasks[task_id]["current_stage"] = "Initializing task..."
            tasks[task_id]["progress"] = 1
            tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Validate API key early
        if not api_key or not api_key.strip():
            raise ValueError("OpenAI API Key is required and cannot be empty")
        
        # Set API key for this task
        original_key = os.environ.get("OPENAI_API_KEY")
        
        # Ensure log queue exists
        if task_id not in task_logs:
            task_logs[task_id] = Queue()
        
        # Capture stdout for logging
        original_stdout = sys.stdout
        log_capture = LogCapture(task_id, original_stdout)
        sys.stdout = log_capture
        
        # Set API key in environment
        os.environ["OPENAI_API_KEY"] = api_key
        
        # Update status to running (after successful setup)
        if task_id in tasks:
            tasks[task_id]["status"] = "running"
            tasks[task_id]["progress"] = 5
            tasks[task_id]["current_stage"] = "Loading configuration"
            tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Send initial log (use print so it goes through LogCapture)
        # Force flush to ensure logs are captured
        print("🚀 Starting course generation...")
        sys.stdout.flush()
        print(f"📚 Course: {request.course_name}")
        sys.stdout.flush()
        print(f"🤖 Model: {request.model_name}")
        sys.stdout.flush()
        print(f"📁 Experiment: {request.exp_name}")
        sys.stdout.flush()
        print("=" * 60)
        sys.stdout.flush()
        
        # Handle catalog data
        catalog_source = request.catalog
        if request.catalog_data:
            # Save catalog data to temporary file
            temp_catalog_name = f"temp_{task_id}"
            catalog_dir = Path("catalog")
            catalog_dir.mkdir(exist_ok=True)
            temp_file = catalog_dir / f"{temp_catalog_name}.json"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(request.catalog_data, f, indent=2, ensure_ascii=False)
            catalog_source = temp_catalog_name
        
        # Update progress
        tasks[task_id]["progress"] = 10
        tasks[task_id]["current_stage"] = "Starting workflow"
        tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        if request.textbook_path:
            print(f"Textbook grounding enabled: {request.textbook_path}")
            sys.stdout.flush()

        # Run the generation (this is synchronous, but we're in a background task)
        # Note: For better progress tracking, you might want to modify ADDIE to accept callbacks
        run_instructional_design(
            course_name=request.course_name,
            copilot="default_copilot" if request.copilot else None,
            catalog=catalog_source,
            model_name=request.model_name,
            exp_name=request.exp_name,
            textbook_path=request.textbook_path,
        )
        
        # Generate PPTX if requested
        if request.generate_pptx:
            print("\n📊 Generating PPTX slides...")
            try:
                from src.latex_to_pptx import LaTeXToPPTXConverter
                converter = LaTeXToPPTXConverter()
                exp_dir = f"./exp/{request.exp_name}/"
                pptx_results = converter.convert_directory(exp_dir)
                print(f"✅ Generated {len(pptx_results)} PPTX files")
            except Exception as pptx_err:
                print(f"⚠️ PPTX generation failed: {pptx_err}")

        # Render lecture videos if requested (best-effort, like PPTX)
        if request.generate_video:
            print("\n🎬 Rendering lecture videos...")
            tasks[task_id]["current_stage"] = "Rendering lecture videos"
            tasks[task_id]["progress"] = 75
            try:
                from src.video import VideoOptions, render_course_videos
                video_results = render_course_videos(
                    f"./exp/{request.exp_name}/",
                    options=VideoOptions(tts_model=request.video_tts_model, voice=request.video_voice, burn_subtitles=bool(request.video_burn_subtitles)),
                    course_name=request.course_name,
                )
                tasks[task_id]["videos"] = video_results
                print(f"✅ Rendered {sum(1 for r in video_results if 'video' in r)} lecture videos")
            except Exception as video_err:
                print(f"⚠️ Lecture video rendering failed: {video_err}")

        # Post-processing (evaluation / refinement) is best-effort: the course
        # files already exist, so a failure here must not mark the task failed.
        if request.run_evaluation or request.run_refinement:
            print("\n🔍 Running evaluation...")
            tasks[task_id]["current_stage"] = "Running evaluation"
            tasks[task_id]["progress"] = 80
            try:
                run_evaluation(
                    model_name=request.model_name,
                    exp_name=request.exp_name,
                )
            except Exception as eval_err:
                print(f"⚠️ Evaluation failed: {eval_err}")
                request.run_refinement = False

        if request.run_refinement:
            print("\n🛠️ Running refinement...")
            tasks[task_id]["current_stage"] = "Running refinement"
            tasks[task_id]["progress"] = 90
            try:
                run_refinement(
                    model_name=request.model_name,
                    exp_name=request.exp_name,
                    threshold=request.refinement_threshold,
                    retries=request.refinement_retries,
                    route=request.refinement_route,
                )
            except Exception as refine_err:
                print(f"⚠️ Refinement failed: {refine_err}")

        # Mark as completed
        print("\n" + "=" * 60)
        print("✅ Course generation completed successfully!")
        print("=" * 60)
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["current_stage"] = "Completed"
        tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Restore original stdout and API key
        sys.stdout = original_stdout
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    except Exception as e:
        # Mark as failed
        error_msg = str(e)
        print(f"\n❌ Error: {error_msg}")
        import traceback
        traceback.print_exc()  # This will also go through LogCapture
        
        # Ensure task exists before updating
        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = error_msg
            tasks[task_id]["current_stage"] = f"Error: {error_msg}"
            tasks[task_id]["updated_at"] = datetime.now().isoformat()
        
        # Restore original stdout and API key
        if original_stdout:
            sys.stdout = original_stdout
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

# Background task function for optimization
async def run_optimization_task(task_id: str, request: OptimizeRequest, api_key: str):
    """
    Run optimization in background. Mirrors run_generation_task.
    """
    original_stdout = None
    log_capture = None
    original_key = None

    try:
        if task_id in tasks:
            tasks[task_id]["status"] = "starting"
            tasks[task_id]["current_stage"] = "Initializing optimization..."
            tasks[task_id]["progress"] = 1
            tasks[task_id]["updated_at"] = datetime.now().isoformat()

        if not api_key or not api_key.strip():
            raise ValueError("OpenAI API Key is required and cannot be empty")

        original_key = os.environ.get("OPENAI_API_KEY")

        if task_id not in task_logs:
            task_logs[task_id] = Queue()

        original_stdout = sys.stdout
        log_capture = LogCapture(task_id, original_stdout)
        sys.stdout = log_capture

        os.environ["OPENAI_API_KEY"] = api_key

        if task_id in tasks:
            tasks[task_id]["status"] = "running"
            tasks[task_id]["progress"] = 5
            tasks[task_id]["current_stage"] = "Loading PDF files"
            tasks[task_id]["updated_at"] = datetime.now().isoformat()

        print("Starting slide optimization...")
        sys.stdout.flush()
        print(f"Storage ID: {request.storage_id}")
        sys.stdout.flush()
        print(f"Model: {request.model_name}")
        sys.stdout.flush()
        print(f"Experiment: {request.exp_name}")
        sys.stdout.flush()
        print(f"Mode: {request.mode}")
        sys.stdout.flush()
        if request.chapter_name:
            print(f"Chapter: {request.chapter_name}")
            sys.stdout.flush()
        print("=" * 60)
        sys.stdout.flush()

        tasks[task_id]["progress"] = 10
        tasks[task_id]["current_stage"] = "Starting optimization workflow"
        tasks[task_id]["updated_at"] = datetime.now().isoformat()

        run_optimization(
            storage_id=request.storage_id,
            user_requirements=request.user_requirements,
            model_name=request.model_name,
            exp_name=request.exp_name,
            chapter_name=request.chapter_name,
            mode=request.mode,
        )

        print("\n" + "=" * 60)
        print("Optimization completed successfully!")
        print("=" * 60)
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["current_stage"] = "Completed"
        tasks[task_id]["updated_at"] = datetime.now().isoformat()

        sys.stdout = original_stdout
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

    except Exception as e:
        error_msg = str(e)
        print(f"\nError: {error_msg}")
        import traceback
        traceback.print_exc()

        if task_id in tasks:
            tasks[task_id]["status"] = "failed"
            tasks[task_id]["error"] = error_msg
            tasks[task_id]["current_stage"] = f"Error: {error_msg}"
            tasks[task_id]["updated_at"] = datetime.now().isoformat()

        if original_stdout:
            sys.stdout = original_stdout
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        elif "OPENAI_API_KEY" in os.environ:
            del os.environ["OPENAI_API_KEY"]

# Mount static files for results (optional, for direct file access)
results_dir = Path("./exp")
if results_dir.exists():
    app.mount("/results", StaticFiles(directory=str(results_dir)), name="results")

if __name__ == "__main__":
    # Load config if exists
    config_path = Path("config.json")
    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
            os.environ["OPENAI_API_KEY"] = config.get("OPENAI_API_KEY", "")
    
    # Run server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

