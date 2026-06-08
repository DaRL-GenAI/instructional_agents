<div align="center">

# Instructional Agents: Reducing Teaching Faculty Workload through Multi-Agent Instructional Design

[![PyPI](https://img.shields.io/pypi/v/instructional-agents?style=flat-square&logo=pypi&logoColor=white)](https://pypi.org/project/instructional-agents/)
[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat-square)](LICENSE)

<p align="center">
  <a href="https://darl-genai.github.io/instructional_agents_homepage/"><img src="https://img.shields.io/website?url=https%3A%2F%2Fdarl-genai.github.io%2Finstructional_agents_homepage%2F&up_message=Website&style=for-the-badge&logo=github&logoColor=white" alt="Website"></a>
  &nbsp;&nbsp;
  <a href="https://github.com/DaRL-GenAI/instructional_agents"><img src="https://img.shields.io/github/stars/DaRL-GenAI/instructional_agents?style=for-the-badge&logo=github&logoColor=white&color=red" alt="GitHub Stars"></a>
</p>

[**Claude Code**](#use-via-claude-code) · [**Quick Start**](#-quick-start-docker---recommended) · [**Core Modules**](#-core-modules) · [**FAQ**](#-faq)

[🇨🇳 中文](README.zh.md) · [🇬🇧 English](README.md)

![visitors](https://visitor-badge.laobi.icu/badge?page_id=DaRL-GenAI.instructional_agents&style=flat)

</div>

An AI-powered instructional design system based on the ADDIE model for automated course creation and evaluation.

```
@misc{yao2025instructionalagentsllmagents,
  title={Instructional Agents: Reducing Teaching Faculty Workload through Multi-Agent Instructional Design},
  author={Yao, Huaiyuan and Xu, Wanpeng and Turnau, Justin and Kellam, Nadia and Wei, Hua},
  year={2025},
  eprint={2508.19611},
  archivePrefix={arXiv},
  primaryClass={cs.AI},
  url={https://arxiv.org/abs/2508.19611},
}
```

---

### 📰 News

> **[2026.1.6]** Instructional Agents is accepted by EACL 2026 Main Conference!

### 📦 Releases

> **[2026.4.15]** Released [Claude Code Skills](https://github.com/DaRL-GenAI/instructional_agents-skills) - invoke the pipeline directly from Claude Code: `/plugin install DaRL-GenAI/instructional_agents-skills`
>
> **[2026.4.13]** Release [v1.1.0](https://github.com/DaRL-GenAI/instructional_agents/releases) - Added [LaTeX-to-PPTX conversion](#latex-to-pptx-conversion) with pptxgenjs, Slide Masters, react-icons, and shadow effects
>
> **[2026.3.26]** Published on [PyPI](https://pypi.org/project/instructional-agents/) - `pip install instructional-agents`

<details>
<summary>History releases</summary>

> **[2026.1.6]** [v1.0.0](https://github.com/DaRL-GenAI/instructional_agents/releases) - Initial release with core features - Thanks to all the contributors! ❤️
>
> **[2026.1.4]** [v0.1.0](https://github.com/DaRL-GenAI/instructional_agents/releases) - Docker deployment and web interface support

</details>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **Multi-Agent Collaboration** | Multiple specialized LLM agents working together based on ADDIE instructional design model |
| 📚 **Automated Course Generation** | Generate complete course materials including syllabus, slides, scripts, and assessments |
| 🎯 **Catalog Mode** | Use structured catalog files to guide course generation with student profiles and institutional requirements |
| 🤝 **Copilot Mode** | Interactive mode for providing feedback during generation at each ADDIE phase |
| 📊 **Real-time Progress** | Monitor generation progress with real-time logs, progress bars, and file updates |
| 🌐 **Web Interface** | User-friendly web interface for course generation, progress monitoring, and file management |
| 📁 **Multiple Usage Methods** | Support for web interface, command-line, and RESTful API |
| 📄 **LaTeX/PDF Output** | Generate professional LaTeX slides and compile to PDF format |
| 🎨 **PowerPoint (PPTX) Export** | Convert LaTeX Beamer slides to visually rich PPTX using pptxgenjs with icons, shadows, and Slide Masters |
| ✅ **Automatic Evaluation** | Built-in evaluation system for assessing generated course materials |
| 📖 **Textbook Grounding** | *(opt-in)* Ground course content in a PDF or markdown textbook; inline citation tokens are inserted in slides, scripts, and assessments. Built-in verifier checks each citation's faithfulness. Available on CLI, API, and Web UI. |

### 🎬 How It Works

<p align="center">
  <img src="docs/process-video.gif" alt="ADDIE Pipeline: Multi-Agent Collaboration Process" width="720">
</p>

---

<a id="use-via-claude-code"></a>

## 🤖 Use via Claude Code

Invoke the full ADDIE pipeline and related tools directly from [Claude Code](https://claude.com/claude-code) — no Python boilerplate.

```bash
pip install instructional-agents
/plugin install DaRL-GenAI/instructional_agents-skills
```

Then ask Claude in natural language: *"Generate a course on Reinforcement Learning"*, *"Convert this Beamer .tex to an editable .pptx"*, *"Evaluate these slides as a Program Chair"*. See the [skills repo](https://github.com/DaRL-GenAI/instructional_agents-skills) for all available commands.

---

## 🚀 Quick Start (Docker - Recommended)

This guide will walk you through the complete workflow from setup to viewing results.

<details>
<summary><b>Step 1: Environment Setup</b></summary>

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

</details>

---

<details>
<summary><b>Step 2: Access Web Interface</b></summary>

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

1. In the web interface, locate the **"API Configuration"** section at the top
2. Enter your OpenAI API Key in the input field
3. Click **"Save API Key"** to save it (stored locally in your browser)
4. The status indicator will show "✅ API Key Configured" when successful

> **Note**: Your API key is only stored in your browser's local storage and never sent to any server except OpenAI during course generation.

#### 2.3 Submit a Course Generation Task

1. **Fill in the course configuration form**:
   - **Course Name** (required): e.g., "Introduction to Machine Learning"
   - **Model Selection**: Choose from GPT-4o Mini (recommended), GPT-4o, or GPT-4 Turbo
   - **Experiment Name**: Leave as "default" or specify a custom name
   - **Copilot Mode**: Enable for interactive feedback during generation (optional)
   - **Catalog Mode**: 
     - Select "Not Use" for basic generation
     - Select "Upload Catalog File" to upload a custom catalog JSON
     - Select "Use Default Catalog" to use the default catalog
   - **Textbook grounding** *(optional)*: upload one or more PDF/markdown files via the picker labelled "Textbook grounding (optional)". Leave empty to skip.

2. **Click "Generate Course"** to start the task

3. To look at the Generation Procedure on the following, please go to Step 3 and 4:
   - Progress bar showing completion percentage
   - Current stage information
   - Real-time logs stream

</details>

---

<details>
<summary><b>Step 3: Monitor Progress and Logs</b></summary>

If you need to view logs outside the web interface:

```bash
# View container logs in real-time
docker-compose logs -f api

# View last 100 lines
docker-compose logs --tail=100 api

# View logs for a specific time range
docker-compose logs --since 30m api
```

</details>

---

<details>
<summary><b>Step 4: View Generated Results</b></summary>

#### 4.1 Via Web Interface (Recommended)

Once generation starts, the **"Generation Results"** section will appear showing:

1. **File Location**:
   - Displays the local path where files are saved
   - Example: `/Users/your_username/PycharmProjects/instructional_agents/exp/your_experiment_name/`
   - Quick actions:
     - **📋 Copy Path**: Copy the path to clipboard
     - **📂 Open Directory**: Open the directory in Finder/Explorer

2. **File List** (updates incrementally):
   - Files appear as they are generated (no need to wait for completion)
   - Each file shows:
     - File icon based on type (📝 .md, 📄 .tex, 📕 .pdf, 📋 .json)
     - File name and size
     - **🆕 New** badge for newly generated files
     - **📥 Download** button for immediate download

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
│   ├── slides.pptx                        # PowerPoint slides (⭐ editable)
│   ├── script.md                          # Presentation script
│   ├── assessment.md                      # Assessment materials
│   └── statistics_slides_chapter_1.json   # Chapter statistics
│
├── chapter_2/                             # Chapter 2 materials
│   └── ...
└── ...
```

> **Tip**: Files are generated incrementally. You can download or view them as soon as they appear, without waiting for the entire generation to complete.

For detailed file descriptions, see [Generated Files Guide](docs/FILES_GENERATED.md).

</details>

---

<details>
<summary><b>Step 5: Next Steps</b></summary>

See [Documentation](#-documentation) section below for detailed guides and references.

</details>

---

## 📦 Install via PyPI

```bash
pip install instructional-agents
```

After installation, you can run the CLI directly:

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=your_api_key_here

# Generate a course
instructional-agents "Introduction to Machine Learning"
```

---

## 🔧 Local Development Setup

For developers who want to run the system locally from source:

### 1. Prerequisites

- Python 3.11+
- pip
- LaTeX (for PDF generation)
  - macOS: `brew install --cask mactex`
  - Ubuntu: `sudo apt-get install texlive-full`
  - Windows: Install [MiKTeX](https://miktex.org/)
- Node.js 18+ (for PPTX generation)
  - macOS: `brew install node`
  - Ubuntu: `sudo apt-get install nodejs npm`
  - Windows: Install from [nodejs.org](https://nodejs.org/)

### 2. Install Dependencies

```bash
# Vanilla install — minimal footprint, supports the standard
# course-writing pipeline (no textbook grounding).
pip install -e .

# Light install + textbook grounding (`--use-textbook PATH`).
# Adds pymupdf, markdown-it-py, rank-bm25, fastembed (ONNX-based
# bi-encoder and cross-encoder via onnxruntime; no torch dep).
# ~100 MB total on top of the base install.
pip install -e ".[grounding]"

# All-in-one (also installs the optional chromadb extras and any
# grounding deps): keeps the prior `requirements.txt`-based workflow
# working unchanged.
pip install -r requirements.txt

# Node.js dependencies (for PPTX generation)
npm install -g pptxgenjs

# Optional: install react-icons for slide icons (recommended)
npm install -g react-icons react react-dom sharp
```

> **Note**: `pptxgenjs` is required for LaTeX-to-PPTX conversion. The `react-icons` + `sharp` packages are optional but recommended — they add topic-specific icons to each slide (e.g., 🤖 for agent topics, 🧠 for AI topics). Without them, slides will use simple geometric shapes instead.

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

# Ground the course in a textbook (PDF/markdown file or directory)
python run.py "Data Mining" --catalog mwe_catalog \
    --use-textbook data/textbooks/han_data_mining_3e
```

**Minimal Working Example** (generates a small 3-week course in ~5 min):
```bash
python run.py "Intro to Python" --catalog mwe_catalog --exp mwe_test --seed 42
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
  --seed SEED              Random seed for reproducibility
  --temperature TEMP       Sampling temperature for LLM
  --use-textbook PATH      Ground course generation in a textbook (PDF or
                           markdown file, or a directory of either). When
                           omitted, generation runs identically to a vanilla
                           run — no citations are emitted.
  --optimize STORAGE_ID    Optimize mode: provide storage_id of uploaded PDFs
  --requirements TEXT      User requirements for optimization (with --optimize)
  --chapter NAME           Specific chapter to optimize (with --optimize)
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

# Textbook grounding (optional) — upload a textbook, then pass its
# returned `path` as `textbook_path` in /api/course/generate above
curl -X POST http://localhost:8000/api/textbooks/upload \
  -F "files=@chapter_1.pdf" -F "files=@chapter_2.pdf"
curl http://localhost:8000/api/textbooks/list
```

For complete API documentation, see [API Documentation](docs/API_DOCUMENTATION.md).

---

## 🔧 Core Modules

| Module | Description | Usage |
|--------|-------------|-------|
| **Course Generation** | Generate complete course materials based on ADDIE model | Web interface, CLI (`run.py`), or RESTful API |
| **Catalog Mode** | Use structured catalog files for guided generation | `--catalog` flag or upload in web interface |
| **Copilot Mode** | Interactive feedback during generation | `--copilot` flag in CLI or enable in web interface |
| **Textbook Grounding** | Ground content in a PDF/markdown textbook with inline citations | `--use-textbook PATH` flag in CLI, `textbook_path` in API, file picker in web interface |
| **Evaluation** | Automatic assessment of generated materials, with optional citation verification | `python evaluate.py --exp <exp_name> [--use-textbook PATH]` |
| **Web Interface** | Visual interface for course generation | Open `frontend/index.html` in browser |
| **API Server** | RESTful API for programmatic access | `python api_server.py` or Docker |

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

See [API Documentation](docs/API_DOCUMENTATION.md#catalog-format) for catalog format details.

### Copilot Mode

Interactive mode that prompts for feedback after each phase of the ADDIE workflow:
- **Analysis** phase: Review and provide feedback on learning goals, resource assessment, target audience
- **Design** phase: Review and refine syllabus design, assessment planning, final project
- **Development** phase: Review and adjust chapter materials as they're generated

```bash
python run.py "Advanced Algorithms" --copilot --exp algo_course_v2
```

### Textbook Grounding

Opt-in. Pass `--use-textbook PATH` (a PDF, markdown file, or directory of either) and the system retrieves relevant textbook passages per chapter and inserts inline citation tokens like `[han_data_mining_3e:ch6.s3:p15]` (textbook id, section, page) in slides, scripts, and assessments. Without the flag, vanilla output is unchanged.

```bash
python run.py "Data Mining" --catalog mwe_catalog --exp dm_grounded \
    --use-textbook data/textbooks/han_data_mining_3e
```

Embeddings are cached on disk after the first ingest (`~5-10s` one-time per textbook). Per-chapter generation is ~10-25% slower than vanilla because prompts carry retrieved excerpts. Verify each emitted citation with the evaluation step below.

**How the grounding works under the hood:**
- Each chapter is decomposed into 3 subtopics by the LLM; each subtopic is HyDE-expanded into a hypothetical textbook paragraph and used as a retrieval query (multi-query retrieval).
- Per-section rankings across queries are fused via Reciprocal Rank Fusion (RRF, k=60). The contract binds each chapter to the top sections.
- Coverage gating: if no textbook section scores above a threshold for a chapter, that chapter is marked "off-textbook" and writes without citations (rather than fabricate them against weak retrieval).
- Writing prompts carry a five-rule mandatory grounding directive: cite-every-sourced-claim, anchor-to-source-wording, abstain-if-unsupported, exact-tokens-only, cite-correct-excerpt. Scripts (spoken narration) get a softer variant that allows natural paraphrase and once-per-concept citation. A worked example uses a real snippet from the top retrieved chunk so the model has a literal pattern to imitate.

### Automatic Evaluation

**Entry Point**: `evaluate.py` – Automatic assessment and scoring

```bash
# Rubric scoring + Program-Chair / Test-Student validation
python evaluate.py --exp web_dev_v1

# Add textbook-citation verification (only meaningful on grounded runs)
python evaluate.py --exp dm_grounded --use-textbook data/textbooks/han_data_mining_3e
```

Evaluation results are saved in `eval/{experiment_name}/` directory. With `--use-textbook`, a `grounding_results/` subdirectory is added containing per-citation faithfulness scores (1–5), citation precision, malformed-token counts, and a **failure-mode breakdown** (`good` / `loose_paraphrase` / `hallucination` / `retrieval_bad` / `wrong_chunk_cited` / `judge_uncertain`) that pinpoints which lever to pull when precision is below target.

### LaTeX-to-PPTX Conversion

Convert generated LaTeX Beamer slides to editable PowerPoint presentations with professional design:

```bash
# Convert a single chapter
python -c "
from src.latex_to_pptx import LaTeXToPPTXConverter
converter = LaTeXToPPTXConverter()
converter.convert('exp/my_course/chapter_1/slides.tex', 'exp/my_course/chapter_1/slides.pptx')
"

# Convert all chapters in a course
python -c "
from src.latex_to_pptx import LaTeXToPPTXConverter
converter = LaTeXToPPTXConverter()
converter.convert_directory('exp/my_course/')
"
```

**PPTX Design Features:**
- 🎨 **Midnight Executive palette** — navy/ice-blue/orange color scheme with Georgia/Calibri fonts
- 📐 **Slide Masters** — consistent layouts via `CONTENT_MASTER`, `CONTENT_CODE`, and `DARK_MASTER`
- 🌓 **Dark/light sandwich** — dark slides for title/conclusion, light for content
- 🔤 **Smart icons** — topic-aware icons from react-icons (robot, brain, code, etc.) in colored circles
- 🎭 **Varied layouts** — auto-detected: single-text, list-only, blocks, code, columns, mixed
- 💫 **Visual polish** — shadows on blocks/code, sidebar accent motif, decorative circles
- 📏 **Typography** — 36pt+ titles, 14-16pt body, auto-scaling for long titles

**Architecture**: `LaTeX .tex → [Python LaTeXParser] → JSON → [Node.js pptxgenjs] → .pptx`

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

### Textbook-Grounded Course

```bash
# Step 1: Generate course grounded in a textbook
python run.py "Data Mining" --catalog mwe_catalog --exp dm_grounded \
  --use-textbook data/textbooks/han_data_mining_3e

# Step 2: Evaluate + verify every citation
python evaluate.py --exp dm_grounded \
  --use-textbook data/textbooks/han_data_mining_3e

# Step 3: Review the citation report
open eval/gpt-4o-mini-Evaluation_dm_grounded/grounding_results/grounding_summary.md
```

---

## 📖 Documentation

| [API Documentation](docs/API_DOCUMENTATION.md) | [Docker Deployment](docs/README_DOCKER.md) | [Generated Files Guide](docs/FILES_GENERATED.md) |
|------------------------------------------------|---------------------------------------------|---------------------------------------------------|
| Complete API reference and endpoints           | Docker setup and deployment guide           | Detailed description of generated files          |

| [Workflow Documentation](docs/WORKFLOW_DOCUMENTATION.md) | [Development Guide](docs/README.md) | |
|----------------------------------------------------------|--------------------------------------|--|
| System workflow and agent collaboration details          | Development and debugging documentation | |

---

## ❓ FAQ

<details>
<summary><b>How to configure API key?</b></summary>

**Checklist**
- Get OpenAI API key from https://platform.openai.com/api-keys
- Configure in `.env` file or web interface

**Solutions**
- **Option 1**: Set in `.env` file: `OPENAI_API_KEY=your_key_here`
- **Option 2**: Configure in web interface (stored in browser local storage only)

</details>

<details>
<summary><b>Port 8000 already in use?</b></summary>

**Problem**

Starting the service shows "port already in use" error.

**Solution**

```bash
# macOS/Linux: Find and kill the process
lsof -i :8000
kill -9 <PID>

# Or change port in .env file
API_PORT=8001
```

</details>

<details>
<summary><b>How to use catalog files?</b></summary>

**Checklist**
- Catalog files should be in JSON format
- Place catalog files in `catalog/` directory

**Solutions**
- **Default catalog**: Use `--catalog` without value to use `catalog/default_catalog.json`
- **Custom catalog**: Use `--catalog my_catalog` to use `catalog/my_catalog.json`
- **Web interface**: Upload catalog file directly in the web interface

</details>

<details>
<summary><b>Where are generated files saved?</b></summary>

**Answer**

Generated files are saved in `exp/{experiment_name}/` directory:
- Foundation files (syllabus, goals, etc.) in the root
- Chapter materials in `chapter_1/`, `chapter_2/`, etc.
- Files are generated incrementally and can be downloaded as soon as they appear

</details>

<details>
<summary><b>Web interface cannot connect to backend?</b></summary>

**Checklist**
- Confirm backend is running (visit http://localhost:8000/docs or http://localhost:8000/health)
- Check browser console for error messages
- Verify API address configuration

**Solution**

- **Docker**: Ensure Docker container is running: `docker-compose ps`
- **Local**: Ensure API server is running: `python api_server.py`
- Check that the port matches (default: 8000)

</details>

<details>
<summary><b>What models are supported?</b></summary>

**Answer**

Currently supports OpenAI models:
- GPT-4o Mini (recommended, cost-effective)
- GPT-4o
- GPT-4 Turbo

Configure via model selection in web interface or `--model` flag in CLI.

</details>

---

## 📜 License

MIT License
