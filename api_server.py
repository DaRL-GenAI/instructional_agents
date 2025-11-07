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
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from queue import Queue
from threading import Thread

from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional as Opt
import uvicorn

from run import run_instructional_design

# Initialize FastAPI app
app = FastAPI(
    title="Instructional Agents API",
    description="API for automated course material generation",
    version="1.0.0"
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
        "version": "1.0.0",
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
        
        # Run the generation (this is synchronous, but we're in a background task)
        # Note: For better progress tracking, you might want to modify ADDIE to accept callbacks
        run_instructional_design(
            course_name=request.course_name,
            copilot="default_copilot" if request.copilot else None,
            catalog=catalog_source,
            model_name=request.model_name,
            exp_name=request.exp_name
        )
        
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

