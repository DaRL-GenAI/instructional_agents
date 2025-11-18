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

### Using Docker One-Click Launch (with Web Interface)

```bash
# 1. Create environment variables file
cp .env.example .env
# Edit .env file and add your OPENAI_API_KEY

# 2. Start the service
./start.sh

# Or start manually
docker-compose up -d

# 3. Access the service
# API Documentation: http://localhost:8000/docs
# Web Interface: Open frontend/index.html (need to configure API address)
```

For detailed instructions, see:
- [Docker Deployment Guide](README_DOCKER.md)
- [API Documentation](API_DOCUMENTATION.md)
- [Generated Files Guide](FILES_GENERATED.md)

---

## 🔧 Local Development

### 1. Setup Configuration

Create or edit `config.json`:
```json
{
  "OPENAI_API_KEY": "your_openai_api_key_here"
}
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🌐 Web Interface Usage

The project now includes a modern web interface located in the `frontend/` directory:

1. **Start API Service** (Docker or local)
2. **Open Frontend Interface**: Open `frontend/index.html` in your browser
3. **Configure API Address**: If the API is not at `localhost:8000`, modify `API_BASE_URL` in `frontend/app.js`

Frontend Features:
- 📝 Visual course configuration form
- 📊 Real-time progress monitoring
- 📁 Result file browsing and download
- 📤 Catalog file upload and management

---

## 🚀 Usage Examples

### 🔹 Web API Method (Recommended)

**API Server**: `api_server.py` – RESTful API service

```bash
# Start API server
python api_server.py
# Or use Docker
docker-compose up -d

# Use frontend interface or call API directly
curl -X POST http://localhost:8000/api/course/generate \
  -H "Content-Type: application/json" \
  -d '{"course_name": "Introduction to Machine Learning"}'
```

### 🔹 Command Line Method

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
```

---

### 🔹 Use Catalog Mode

You can now specify a catalog name using `--catalog [name]`. If only `--catalog` is given without a name, a default value will be used (`default_catalog.json`).

```bash
# Use default catalog
python run.py "Software Engineering" --catalog

# Use a specific catalog file (e.g., catalog/ai_catalog.json)
python run.py "AI Fundamentals" --catalog ai_catalog

# Combine catalog mode and copilot
python run.py "Educational Psychology" --copilot --catalog edu_psy
```

---

### 🔹 Command Line Arguments

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

---

## ✅ Automatic Evaluation

**Entry Point**: `evaluate.py` – Automatic assessment and scoring

```bash
# Evaluate a specific experiment
python evaluate.py --exp web_dev_v1
```

---

## 🧵 Background Execution with Logging

### Using `nohup` for Long-Running Tasks

```bash
# Run in background with log file
nohup python run.py "Advanced Machine Learning" --exp ml_advanced > logs/ml_course.log 2>&1 &

# Monitor progress
tail -f logs/ml_course.log
```

---

## 📚 Example Workflows

### 🔸 Complete Course Design

```bash
# Step 1: Generate course using catalog
python run.py "Python Fundamentals" \
  --catalog python_catalog \
  --model gpt-4o \
  --exp py_course_v1

# Step 2: Evaluate results
python evaluate.py --exp py_course_v1
```

### 🔸 Interactive Development (Copilot)

```bash
python run.py "Advanced Algorithms" --copilot --exp algo_course_v2

# You'll be prompted for feedback after each phase:
# - Analysis → feedback
# - Design → feedback
# - Development → feedback
```

---

## 📁 View Results

```bash
# List output files
tree exp/your_experiment_name/

# View evaluation summary
cat eval/your_experiment_name/evaluation_results/evaluation_summary.md

# View detailed validation reports
ls eval/your_experiment_name/validation_reports/
```

---

## 📌 Notes

* If you specify `--catalog` without a value, the system defaults to `default_catalog.json` inside the `catalog/` folder.
* If you provide a name (e.g., `--catalog mydata`), the system expects `catalog/mydata.json`.

---

## 📜 License

MIT License

