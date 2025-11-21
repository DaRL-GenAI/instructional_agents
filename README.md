# INSTRUCTIONAL AGENTS: LLM Agents on Automated Course Material Generation for Teaching Faculties

**Language / 语言**: [English](README.md) | [中文](README.zh.md)

![visitors](https://visitor-badge.laobi.icu/badge?page_id=wingsweihua.instructional_agents&style=flat)
[![Website](https://img.shields.io/website?url=https%3A%2F%2Fhyan-yao.github.io%2Finstructional_agents_homepage%2F&up_message=Instructional%20Agents&style=flat)](https://hyan-yao.github.io/instructional_agents_homepage/)
![GitHub Repo stars](https://img.shields.io/github/stars/Hyan-Yao/instructional_agents?style=flat&color=red)

An AI-powered instructional design system based on the ADDIE model for automated course creation and evaluation.

```
@misc{yao2025instructionalagentsllmagents,
  title={Instructional Agents: LLM Agents on Automated Course Material Generation for Teaching Faculties},
  author={Yao, Huaiyuan and Xu, Wanpeng and Turnau, Justin and Kellam, Nadia and Wei, Hua},
  year={2025},
  eprint={2508.19611},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2508.19611},
}
```

---

## 🚀 Quick Start (Docker - Recommended)

This guide will walk you through the complete workflow from setup to viewing results.

### Step 1: Environment Setup

#### 1.1 Prerequisites

- **Docker** and **Docker Compose** installed
  - Check installation: `docker --version` and `docker-compose --version`
  - Install: [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **OpenAI API Key**
  - Get one from: https://platform.openai.com/api-keys

#### 1.2 Configuration

```bash
# Clone the repository (if not already done)
git clone <repository-url>
cd instructional_agents

# Create environment variables file
cp .env.example .env

# Edit .env file and add your OPENAI_API_KEY
# OPENAI_API_KEY=your_api_key_here
# API_PORT=8000
```

> **Note**: You can also configure the API key directly in the web interface (see Step 2.2). If you skip setting it in `.env`, you'll need to enter it in the frontend.

#### 1.3 Start Docker Service

```bash
# Option 1: Use the start script (recommended)
./start.sh

# Option 2: Start manually
docker-compose up -d

# Verify service is running
curl http://localhost:8000/health
# Should return: {"status":"healthy","version":"1.0.0",...}
```

> **Tip**: If port 8000 is already in use, modify `API_PORT` in your `.env` file.

---

### Step 2: Access Web Interface

#### 2.1 Open the Frontend

**Option A: Direct file access** (simplest)
```bash
# Open frontend/index.html directly in your browser
open frontend/index.html  # macOS
# or double-click frontend/index.html in your file manager
```

**Option B: Local server** (recommended for better CORS support)
```bash
# Using Python
cd frontend
python -m http.server 8080
# Then open http://localhost:8080/index.html in your browser
```

#### 2.2 Configure API Key

1. In the web interface, locate the **"API 配置"** section at the top
2. Enter your OpenAI API Key in the input field
3. Click **"保存 API Key"** to save it (stored locally in your browser)
4. The status indicator will show "✅ API Key 已配置" when successful

> **Note**: Your API key is only stored in your browser's local storage and never sent to any server except OpenAI during course generation.

#### 2.3 Submit a Course Generation Task

1. **Fill in the course configuration form**:
   - **Course Name** (required): e.g., "Introduction to Machine Learning"
   - **Model Selection**: Choose from GPT-4o Mini (recommended), GPT-4o, or GPT-4 Turbo
   - **Experiment Name**: Leave as "default" or specify a custom name
   - **Copilot Mode**: Enable for interactive feedback during generation (optional)
   - **Catalog Mode**: 
     - Select "不使用" for basic generation
     - Select "上传 Catalog 文件" to upload a custom catalog JSON
     - Select "使用默认 Catalog" to use the default catalog

2. **Click "Generate Course"** to start the task

3. To look at the Generation Procedure on the following, please go to Step 3 and 4:
   - Progress bar showing completion percentage
   - Current stage information
   - Real-time logs stream

---

### Step 3: Monitor Progress and Logs

#### 3.1 Via Web Interface (Recommended)

After submitting a task, the progress section shows:

- **📊 Progress Bar**: Visual indicator of overall completion (0-100%)
- **📝 Current Stage**: Displays the current processing stage, such as:
  - "Loading configuration"
  - "Generating instructional goals"
  - "Creating syllabus design"
  - "Generating slides for chapter 1"
  - etc.
- **📋 Real-time Logs**: Automatically streams detailed logs including:
  - Task initialization messages
  - Agent deliberations and discussions
  - File generation progress
  - Completion status
  - Error messages (if any)

The logs update in real-time as the task progresses. You can:
- Scroll through the log history
- Use the **"🗑️ 清空日志"** button to clear the display (logs continue streaming)

#### 3.2 Via Docker Logs (Alternative)

If you need to view logs outside the web interface:

```bash
# View container logs in real-time
docker-compose logs -f api

# View last 100 lines
docker-compose logs --tail=100 api

# View logs for a specific time range
docker-compose logs --since 30m api
```

#### 3.3 Check Task Status via API

```bash
# Replace {task_id} with your actual task ID from the web interface
curl http://localhost:8000/api/course/status/{task_id}
```

---

### Step 4: View Generated Results

#### 4.1 Via Web Interface (Recommended)

Once generation starts, the **"生成结果"** section will appear showing:

1. **File Location**:
   - Displays the local path where files are saved
   - Example: `/Users/your_username/PycharmProjects/instructional_agents/exp/your_experiment_name/`
   - Quick actions:
     - **📋 复制路径**: Copy the path to clipboard
     - **📂 打开文件夹**: Open the directory in Finder/Explorer

2. **File List** (updates incrementally):
   - Files appear as they are generated (no need to wait for completion)
   - Each file shows:
     - File icon based on type (📝 .md, 📄 .tex, 📕 .pdf, 📋 .json)
     - File name and size
     - **🆕 新** badge for newly generated files
     - **📥 下载** button for immediate download

3. **File Organization**:
   - Files are grouped by directory
   - Foundation files (syllabus, goals, etc.) in the root
   - Chapter materials in `chapter_1/`, `chapter_2/`, etc.

#### 4.2 Via File System

Generated files are saved in the `exp/` directory in your project folder:

```bash
# List all experiments
ls exp/

# View a specific experiment's structure
ls -R exp/your_experiment_name/

# Open in Finder (macOS)
open exp/your_experiment_name/

# Open in Explorer (Windows)
explorer exp\\your_experiment_name\\

# View course syllabus
cat exp/your_experiment_name/result_syllabus_design.md

# View generated slides PDF
open exp/your_experiment_name/chapter_1/slides.pdf
```

**File Structure**:
```
exp/{experiment_name}/
├── result_instructional_goals.md          # Learning objectives
├── result_resource_assessment.md          # Resource assessment
├── result_target_audience.md              # Target audience analysis
├── result_syllabus_design.md              # Course syllabus (⭐ important)
├── result_assessment_planning.md          # Assessment planning
├── result_final_exam_project.md           # Final project design
├── processed_chapters.json                # Chapter metadata
├── statistics.json                        # Generation statistics
│
├── chapter_1/                             # Chapter 1 materials
│   ├── slides.tex                         # LaTeX source
│   ├── slides.pdf                         # Compiled PDF slides (⭐ ready to use)
│   ├── script.md                          # Presentation script
│   ├── assessment.md                      # Assessment materials
│   └── statistics_slides_chapter_1.json   # Chapter statistics
│
├── chapter_2/                             # Chapter 2 materials
│   └── ...
└── ...
```

> **Tip**: Files are generated incrementally. You can download or view them as soon as they appear, without waiting for the entire generation to complete.

For detailed file descriptions, see [Generated Files Guide](FILES_GENERATED.md).

---

### Step 5: Next Steps

- **Detailed Docker Setup**: [Docker Deployment Guide](README_DOCKER.md)
- **API Reference**: [API Documentation](API_DOCUMENTATION.md)
- **Understanding Generated Files**: [Generated Files Guide](FILES_GENERATED.md)
- **Advanced Usage**: See sections below

---

## 🔧 Local Development Setup

For developers who want to run the system locally without Docker:

### 1. Prerequisites

- Python 3.11+
- pip
- LaTeX (for PDF generation)
  - macOS: `brew install --cask mactex`
  - Ubuntu: `sudo apt-get install texlive-full`
  - Windows: Install [MiKTeX](https://miktex.org/)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

**Option A: Using config.json**
```json
{
  "OPENAI_API_KEY": "your_openai_api_key_here"
}
```

**Option B: Using environment variable**
```bash
export OPENAI_API_KEY=your_api_key_here
```

### 4. Start API Server

```bash
# Start the API server
python api_server.py

# Or use uvicorn directly with auto-reload
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

---

## 🚀 Usage Methods

### Method 1: Web Interface (Recommended)

The easiest way to use the system. See Step 2 above for detailed instructions.

**Features**:
- 📝 Visual course configuration form
- 📊 Real-time progress monitoring
- 📁 Result file browsing and download
- 📤 Catalog file upload and management
- 🔄 Real-time log streaming

### Method 2: Command Line

**Entry Point**: `run.py` – Main workflow entry point

```bash
# Simple course generation
python run.py "Introduction to Machine Learning"

# With specific model
python run.py "Data Structures" --model gpt-4o-mini

# With experiment name
python run.py "Web Development" --exp web_dev_v1

# Interactive copilot mode
python run.py "Database Systems" --copilot

# Use catalog mode
python run.py "Software Engineering" --catalog

# Use specific catalog file
python run.py "AI Fundamentals" --catalog ai_catalog

# Combine catalog and copilot
python run.py "Educational Psychology" --copilot --catalog edu_psy
```

**Command Line Arguments**:
```bash
python run.py <course_name> [OPTIONS]

Required:
  course_name              Name of the course to design

Options:
  --copilot                Enable interactive copilot mode
  --catalog [name]         Use structured data from catalog/ directory
                           (optional: specify catalog name without '.json')
  --model MODEL            OpenAI model to use (default: gpt-4o-mini)
  --exp EXP_NAME           Experiment name for saving output (default: exp1)
```

### Method 3: Direct API Calls

**API Server**: `api_server.py` – RESTful API service

```bash
# Start API server first (if not using Docker)
python api_server.py

# Generate a course
curl -X POST http://localhost:8000/api/course/generate \
  -H "Content-Type: application/json" \
  -H "X-OpenAI-API-Key: your_api_key_here" \
  -d '{
    "course_name": "Introduction to Machine Learning",
    "model_name": "gpt-4o-mini",
    "exp_name": "ml_intro_v1"
  }'

# Check task status
curl http://localhost:8000/api/course/status/{task_id}

# Get result files
curl http://localhost:8000/api/course/results/{task_id}/files

# Download a file
curl http://localhost:8000/api/course/results/{task_id}/download/chapter_1/slides.pdf \
  --output slides.pdf
```

For complete API documentation, see [API Documentation](API_DOCUMENTATION.md).

---

## 📚 Advanced Usage

### Catalog Mode

Catalog files provide structured input data to guide the course generation process. They include:
- Student profiles and backgrounds
- Instructor preferences and style
- Course structure requirements
- Assessment design preferences
- Teaching constraints
- Institutional requirements

**Using Catalogs**:
```bash
# Use default catalog
python run.py "Software Engineering" --catalog

# Use a specific catalog file (without .json extension)
python run.py "AI Fundamentals" --catalog ai_catalog
# System looks for: catalog/ai_catalog.json

# Upload catalog via web interface
# In the web interface, select "上传 Catalog 文件" and upload your JSON file
```

See [API Documentation](API_DOCUMENTATION.md#catalog-format) for catalog format details.

### Copilot Mode

Interactive mode that prompts for feedback after each phase of the ADDIE workflow:
- **Analysis** phase: Review and provide feedback on learning goals, resource assessment, target audience
- **Design** phase: Review and refine syllabus design, assessment planning, final project
- **Development** phase: Review and adjust chapter materials as they're generated

```bash
python run.py "Advanced Algorithms" --copilot --exp algo_course_v2
```

### Automatic Evaluation

**Entry Point**: `evaluate.py` – Automatic assessment and scoring

```bash
# Evaluate a specific experiment
python evaluate.py --exp web_dev_v1
```

Evaluation results are saved in `eval/{experiment_name}/` directory.

### Background Execution with Logging

For long-running tasks, run in the background:

```bash
# Run in background with log file
nohup python run.py "Advanced Machine Learning" --exp ml_advanced > logs/ml_course.log 2>&1 &

# Monitor progress
tail -f logs/ml_course.log

# Check process status
ps aux | grep "python run.py"
```

---

## 📚 Example Workflows

### Complete Course Design

```bash
# Step 1: Generate course using catalog
python run.py "Python Fundamentals" \
  --catalog python_catalog \
  --model gpt-4o \
  --exp py_course_v1

# Step 2: Evaluate results
python evaluate.py --exp py_course_v1

# Step 3: Review generated materials
open exp/py_course_v1/result_syllabus_design.md
open exp/py_course_v1/chapter_1/slides.pdf
```

### Interactive Development (Copilot)

```bash
python run.py "Advanced Algorithms" --copilot --exp algo_course_v2

# You'll be prompted for feedback after each phase:
# - Analysis → feedback on goals, resources, audience
# - Design → feedback on syllabus, assessments
# - Development → feedback on chapter materials
```

---

## 📌 Notes

* If you specify `--catalog` without a value, the system defaults to `default_catalog.json` inside the `catalog/` folder.
* If you provide a name (e.g., `--catalog mydata`), the system expects `catalog/mydata.json`.
* Generated files are saved incrementally. You can download them as soon as they appear without waiting for completion.
* The web interface requires the API to be running (Docker or local). Make sure the API is accessible at the configured address.

---

## 📜 License

MIT License
