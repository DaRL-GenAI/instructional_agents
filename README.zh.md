# INSTRUCTIONAL AGENTS: LLM Agents on Automated Course Material Generation for Teaching Faculties


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

<div align="right" style="margin-bottom: 20px; margin-top: 10px;">
  <button onclick="switchLanguage('en')" id="lang-en" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #e2e8f0; background: white; color: #64748b; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇺🇸 English</button>
  <button onclick="switchLanguage('zh')" id="lang-zh" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #14b8a6; background: #14b8a6; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇨🇳 中文</button>
</div>

<script>
// Language switching functionality
function switchLanguage(lang) {
    // Save language preference
    localStorage.setItem('preferredLanguage', lang);
    
    // Update button styles
    const enBtn = document.getElementById('lang-en');
    const zhBtn = document.getElementById('lang-zh');
    
    if (lang === 'en') {
        enBtn.style.background = '#14b8a6';
        enBtn.style.color = 'white';
        enBtn.style.borderColor = '#14b8a6';
        zhBtn.style.background = 'white';
        zhBtn.style.color = '#64748b';
        zhBtn.style.borderColor = '#e2e8f0';
        
        // Redirect to English version
        if (window.location.pathname.includes('.zh.md')) {
            window.location.href = window.location.pathname.replace('.zh.md', '.md');
        }
    } else {
        zhBtn.style.background = '#14b8a6';
        zhBtn.style.color = 'white';
        zhBtn.style.borderColor = '#14b8a6';
        enBtn.style.background = 'white';
        enBtn.style.color = '#64748b';
        enBtn.style.borderColor = '#e2e8f0';
        
        // Redirect to Chinese version
        if (!window.location.pathname.includes('.zh.md')) {
            window.location.href = window.location.pathname.replace('.md', '.zh.md');
        }
    }
    
    // Update all document links
    updateDocumentLinks(lang);
}

function updateDocumentLinks(lang) {
    const linkMap = {
        'README_DOCKER.md': lang === 'zh' ? 'README_DOCKER.zh.md' : 'README_DOCKER.md',
        'API_DOCUMENTATION.md': lang === 'zh' ? 'API_DOCUMENTATION.zh.md' : 'API_DOCUMENTATION.md',
        'FILES_GENERATED.md': lang === 'zh' ? 'FILES_GENERATED.zh.md' : 'FILES_GENERATED.md'
    };
    
    // Update links in the document
    document.querySelectorAll('a[href]').forEach(link => {
        const href = link.getAttribute('href');
        if (linkMap[href]) {
            link.href = linkMap[href];
        }
    });
}

// Apply saved language preference on page load
document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferredLanguage') || 'zh';
    if (savedLang === 'en' && window.location.pathname.includes('.zh.md')) {
        // Auto-redirect to English version if preferred
        // window.location.href = window.location.pathname.replace('.zh.md', '.md');
    } else {
        switchLanguage(savedLang);
    }
});
</script>

<style>
button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>

---

## 🚀 快速开始（Docker 方式 - 推荐）

### 使用 Docker 一键启动（包含 Web 界面）

```bash
# 1. 创建环境变量文件
cp .env.example .env
# 编辑 .env 文件，添加你的 OPENAI_API_KEY

# 2. 启动服务
./start.sh

# 或者手动启动
docker-compose up -d

# 3. 访问服务
# API 文档: http://localhost:8000/docs
# Web 界面: 打开 frontend/index.html（需要配置 API 地址）
```

详细说明请查看：
- [Docker 部署指南](README_DOCKER.zh.md)
- [API 文档](API_DOCUMENTATION.zh.md)
- [生成文件说明](FILES_GENERATED.zh.md)

---

## 🔧 本地开发方式

### 1. Setup Configuration

Create or edit `config.json`:
```json
{
  "OPENAI_API_KEY": "your_openai_api_key_here"
}
````

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 🌐 Web 界面使用

项目现在包含一个现代化的 Web 界面，位于 `frontend/` 目录：

1. **启动 API 服务**（Docker 或本地）
2. **打开前端界面**：在浏览器中打开 `frontend/index.html`
3. **配置 API 地址**：如果 API 不在 `localhost:8000`，需要修改 `frontend/app.js` 中的 `API_BASE_URL`

前端功能：
- 📝 可视化课程配置表单
- 📊 实时进度监控
- 📁 结果文件浏览和下载
- 📤 Catalog 文件上传和管理

---

## 🚀 Usage Examples

### 🔹 Web API 方式（推荐）

**API 服务器**: `api_server.py` – RESTful API 服务

```bash
# 启动 API 服务器
python api_server.py
# 或使用 Docker
docker-compose up -d

# 使用前端界面或直接调用 API
curl -X POST http://localhost:8000/api/course/generate \
  -H "Content-Type: application/json" \
  -d '{"course_name": "Introduction to Machine Learning"}'
```

### 🔹 命令行方式

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
