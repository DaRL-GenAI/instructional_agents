# Instructional Agents API Documentation

**Language / 语言**: [English](API_DOCUMENTATION.md) | [中文](API_DOCUMENTATION.zh.md)

## Overview

Instructional Agents API provides automated course material generation services based on the ADDIE model. The system is deployed via Docker containers and provides RESTful API interfaces and a web frontend.

## Quick Start

### 1. Environment Setup

Ensure you have installed:
- Docker and Docker Compose
- Or Python 3.11+ (for local development)

### 2. Configure Environment Variables

Create `.env` file (refer to `.env.example`):

```bash
OPENAI_API_KEY=your_openai_api_key_here
API_PORT=8000
```

### 3. Start with Docker (Recommended)

```bash
# Build and start service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop service
docker-compose down
```

### 4. Local Development Mode

```bash
# Install dependencies
pip install -r requirements.txt

# Start API server
python api_server.py

# Or use uvicorn
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Access Frontend

Open browser and visit: `http://localhost:8000` (if frontend service is configured)

Or directly open `frontend/index.html` file (need to configure CORS)

## API Endpoints

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00"
}
```

### Generate Course

```http
POST /api/course/generate
Content-Type: application/json

{
  "course_name": "Introduction to Machine Learning",
  "model_name": "gpt-4o-mini",
  "exp_name": "ml_intro_v1",
  "copilot": false,
  "catalog": "default_catalog",
  "catalog_data": {...}
}
```

**Response:**
```json
{
  "task_id": "uuid-string",
  "status": "started",
  "message": "Course generation started"
}
```

### Query Task Status

```http
GET /api/course/status/{task_id}
```

**Response:**
```json
{
  "task_id": "uuid-string",
  "status": "running",
  "progress": 45,
  "current_stage": "Generating slides",
  "error": null,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:05:00",
  "exp_name": "ml_intro_v1"
}
```

**Status Values:**
- `pending`: Waiting
- `running`: Running
- `completed`: Completed
- `failed`: Failed

### Get Result File List

```http
GET /api/course/results/{task_id}/files
```

**Response:**
```json
{
  "task_id": "uuid-string",
  "exp_name": "ml_intro_v1",
  "files": [
    {
      "name": "slides.tex",
      "path": "chapter_1/slides.tex",
      "size": 12345,
      "type": ".tex"
    }
  ]
}
```

### Download File

```http
GET /api/course/results/{task_id}/download/{file_path}
```

Directly download generated files.

### Upload Catalog

```http
POST /api/catalog/upload
Content-Type: multipart/form-data

file: <catalog.json>
```

**Response:**
```json
{
  "success": true,
  "filename": "uploaded_abc123_catalog.json",
  "message": "Catalog uploaded successfully"
}
```

### List Catalogs

```http
GET /api/catalog/list
```

**Response:**
```json
{
  "catalogs": [
    {
      "name": "default_catalog",
      "filename": "default_catalog.json",
      "size": 1234,
      "modified": "2024-01-01T00:00:00"
    }
  ]
}
```

## Request Parameters

### CourseRequest

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| course_name | string | Yes | Course name |
| model_name | string | No | OpenAI model (default: gpt-4o-mini) |
| exp_name | string | No | Experiment name (default: default) |
| copilot | boolean | No | Enable Copilot mode |
| catalog | string | No | Catalog filename (without .json) |
| catalog_data | object | No | Catalog data (JSON object) |

## Workflow

1. **Submit Task**: Call `/api/course/generate` to create generation task
2. **Poll Status**: Regularly call `/api/course/status/{task_id}` to check progress
3. **Get Results**: After task completion, call `/api/course/results/{task_id}/files` to get file list
4. **Download Files**: Use `/api/course/results/{task_id}/download/{file_path}` to download files

## Catalog Format

Catalog JSON file should contain the following structure:

```json
{
  "student_profile": {
    "student_background": "...",
    "aggregate_academic_performance": "...",
    "anticipated_learner_needs_and_barriers": "..."
  },
  "instructor_preferences": {
    "instructor_emphasis_intent": "...",
    "instructor_style_preferences": "...",
    "instructor_focus_for_assessment": "..."
  },
  "course_structure": {
    "course_learning_outcomes": "...",
    "total_number_of_weeks": "...",
    "weekly_schedule_outline": "..."
  },
  "assessment_design": {
    "assessment_format_preferences": "...",
    "assessment_delivery_constraints": "..."
  },
  "teaching_constraints": {
    "platform_policy_constraints": "...",
    "ta_support_availability": "...",
    "instructional_delivery_context": "...",
    "max_slide_count": "50"
  },
  "institutional_requirements": {
    "program_learning_outcomes": "...",
    "academic_policies_and_institutional_standards": "...",
    "department_syllabus_requirements": "..."
  },
  "prior_feedback": {
    "historical_course_evaluation_results": "..."
  }
}
```

## Output Structure

Generated files are saved in `exp/{exp_name}/` directory:

```
exp/{exp_name}/
├── result_instructional_goals.md
├── result_resource_assessment.md
├── result_target_audience.md
├── result_syllabus_design.md
├── result_assessment_planning.md
├── result_final_exam_project.md
├── processed_chapters.json
├── statistics.json
├── chapter_1/
│   ├── slides.tex
│   ├── slides.pdf
│   ├── script.md
│   └── assessment.md
└── chapter_2/
    └── ...
```

## Error Handling

API uses standard HTTP status codes:

- `200`: Success
- `400`: Bad Request (e.g., invalid JSON)
- `404`: Not Found (e.g., task does not exist)
- `500`: Server Error

Error response format:

```json
{
  "detail": "Error message here"
}
```

## Performance Considerations

- Course generation may take **10-60 minutes**, depending on number of chapters and model selection
- Recommend using **WebSocket** or **Server-Sent Events** for real-time progress updates (current version uses polling)
- Large file downloads should use streaming

## Security Recommendations

1. **Production Environment**:
   - Restrict CORS origins
   - Use HTTPS
   - Add authentication
   - Limit API key access

2. **API Key Management**:
   - Use environment variables, don't hardcode
   - Use key management services (e.g., AWS Secrets Manager)

3. **Resource Limits**:
   - Set Docker resource limits
   - Limit concurrent tasks
   - Set request timeout

## Troubleshooting

### Common Issues

1. **Docker Build Failed**
   - Check network connection (need to download LaTeX packages)
   - Ensure sufficient disk space (LaTeX packages are large)

2. **API Service Cannot Start**
   - Check if `OPENAI_API_KEY` is set
   - Check if port is occupied

3. **Task Stuck in Pending State**
   - Check container logs: `docker-compose logs api`
   - Check if there are sufficient resources

4. **LaTeX Compilation Failed**
   - Check generated `.tex` file syntax
   - View compilation logs: `exp/{exp_name}/.cache/`

## Development Guide

### Add New Endpoint

1. Add route function in `api_server.py`
2. Define request/response models (using Pydantic)
3. Update this documentation

### Modify Workflow

Main logic is in `ADDIE.py` and `run.py`, need to restart API service after modification.

## License

MIT License

