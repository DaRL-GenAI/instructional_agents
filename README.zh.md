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

## 🚀 快速开始（Docker 方式 - 推荐）

本指南将带您完成从配置到查看结果的完整流程。

### 第一步：环境配置

#### 1.1 前置要求

- **Docker** 和 **Docker Compose** 已安装
  - 检查安装：`docker --version` 和 `docker-compose --version`
  - 安装：访问 [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **OpenAI API Key**
  - 获取地址：https://platform.openai.com/api-keys

#### 1.2 配置

```bash
# 克隆仓库（如果还没有）
git clone <repository-url>
cd instructional_agents

# 创建环境变量文件
cp .env.example .env

# 编辑 .env 文件，添加你的 OPENAI_API_KEY
# OPENAI_API_KEY=your_api_key_here
# API_PORT=8000
```

> **提示**：您也可以直接在 Web 界面中配置 API Key（见第二步）。如果跳过在 `.env` 中设置，需要在前端界面中输入。

#### 1.3 启动 Docker 服务

```bash
# 方式1：使用启动脚本（推荐）
./start.sh

# 方式2：手动启动
docker-compose up -d

# 验证服务是否运行
curl http://localhost:8000/health
# 应该返回: {"status":"healthy","version":"1.0.0",...}
```

> **提示**：如果端口 8000 已被占用，请在 `.env` 文件中修改 `API_PORT`。

---

### 第二步：访问 Web 界面

#### 2.1 打开前端界面

**方式 A：直接打开文件**（最简单）
```bash
# 直接在浏览器中打开 frontend/index.html
open frontend/index.html  # macOS
# 或在文件管理器中双击 frontend/index.html
```

**方式 B：本地服务器**（推荐，CORS 支持更好）
```bash
# 使用 Python
cd frontend
python -m http.server 8080
# 然后在浏览器中打开 http://localhost:8080/index.html
```

#### 2.2 配置 API Key

1. 在 Web 界面顶部找到 **"API 配置"** 区域
2. 在输入框中输入您的 OpenAI API Key
3. 点击 **"保存 API Key"** 保存（仅保存在浏览器本地）
4. 状态指示器会显示 "✅ API Key 已配置" 表示成功

> **注意**：您的 API Key 仅保存在浏览器本地存储中，除了在生成课程时发送给 OpenAI，不会发送给任何其他服务器。

#### 2.3 提交课程生成任务

1. **填写课程配置表单**：
   - **课程名称**（必填）：例如"机器学习导论"
   - **模型选择**：选择 GPT-4o Mini（推荐）、GPT-4o 或 GPT-4 Turbo
   - **实验名称**：保留为 "default" 或指定自定义名称
   - **Copilot 模式**：启用后可在生成过程中进行交互式反馈（可选）
   - **Catalog 模式**：
     - 选择"不使用"进行基础生成
     - 选择"上传 Catalog 文件"上传自定义 catalog JSON
     - 选择"使用默认 Catalog"使用默认 catalog

2. **点击 "开始生成课程"** 开始任务

3. 想要查看生成进度, 请看第三、四步：
   - 显示完成百分比的进度条
   - 当前阶段信息
   - 实时日志流

---

### 第三步：监控进度和日志

#### 3.1 通过 Web 界面（推荐）

提交任务后，进度区域会显示：

- **📊 进度条**：整体完成情况的可视化指示器（0-100%）
- **📝 当前阶段**：显示当前处理阶段，例如：
  - "加载配置中"
  - "生成学习目标"
  - "创建课程大纲"
  - "生成第1章幻灯片"
  - 等等
- **📋 实时日志**：自动流式传输详细日志，包括：
  - 任务初始化消息
  - 智能体审议和讨论
  - 文件生成进度
  - 完成状态
  - 错误消息（如有）

日志会随着任务进度实时更新。您可以：
- 滚动查看日志历史
- 使用 **"🗑️ 清空日志"** 按钮清空显示（日志会继续流式传输）

#### 3.2 通过 Docker 日志（备选）

如果您需要在 Web 界面外查看日志：

```bash
# 实时查看容器日志
docker-compose logs -f api

# 查看最后 100 行
docker-compose logs --tail=100 api

# 查看特定时间范围的日志
docker-compose logs --since 30m api
```

#### 3.3 通过 API 检查任务状态

```bash
# 将 {task_id} 替换为 Web 界面中的实际任务 ID
curl http://localhost:8000/api/course/status/{task_id}
```

---

### 第四步：查看生成结果

#### 4.1 通过 Web 界面（推荐）

生成开始后，**"生成结果"** 区域会显示：

1. **文件位置**：
   - 显示文件保存的本地路径
   - 示例：`/Users/your_username/PycharmProjects/instructional_agents/exp/your_experiment_name/`
   - 快捷操作：
     - **📋 复制路径**：将路径复制到剪贴板
     - **📂 打开文件夹**：在 Finder/资源管理器中打开目录

2. **文件列表**（增量更新）：
   - 文件生成后立即显示（无需等待全部完成）
   - 每个文件显示：
     - 基于文件类型的图标（📝 .md、📄 .tex、📕 .pdf、📋 .json）
     - 文件名和大小
     - **🆕 新** 标记用于新生成的文件
     - **📥 下载** 按钮用于立即下载

3. **文件组织**：
   - 文件按目录分组
   - 基础文件（大纲、目标等）在根目录
   - 章节材料在 `chapter_1/`、`chapter_2/` 等目录中

#### 4.2 通过文件系统

生成的文件保存在项目文件夹的 `exp/` 目录中：

```bash
# 列出所有实验
ls exp/

# 查看特定实验的结构
ls -R exp/your_experiment_name/

# 在 Finder 中打开（macOS）
open exp/your_experiment_name/

# 在资源管理器中打开（Windows）
explorer exp\\your_experiment_name\\

# 查看课程大纲
cat exp/your_experiment_name/result_syllabus_design.md

# 查看生成的幻灯片 PDF
open exp/your_experiment_name/chapter_1/slides.pdf
```

**文件结构**：
```
exp/{experiment_name}/
├── result_instructional_goals.md          # 学习目标
├── result_resource_assessment.md          # 资源评估
├── result_target_audience.md              # 目标受众分析
├── result_syllabus_design.md              # 课程大纲（⭐ 重要）
├── result_assessment_planning.md          # 评估规划
├── result_final_exam_project.md           # 期末项目设计
├── processed_chapters.json                # 章节元数据
├── statistics.json                        # 生成统计信息
│
├── chapter_1/                             # 第1章材料
│   ├── slides.tex                         # LaTeX 源文件
│   ├── slides.pdf                         # 编译后的 PDF 幻灯片（⭐ 可直接使用）
│   ├── script.md                          # 演讲脚本
│   ├── assessment.md                      # 评估材料
│   └── statistics_slides_chapter_1.json   # 章节统计
│
├── chapter_2/                             # 第2章材料
│   └── ...
└── ...
```

> **提示**：文件是增量生成的。文件一出现就可以下载或查看，无需等待整个生成完成。

详细文件说明请查看 [生成文件说明](FILES_GENERATED.zh.md)。

---

### 第五步：后续步骤

- **详细 Docker 配置**：[Docker 部署指南](README_DOCKER.zh.md)
- **API 参考**：[API 文档](API_DOCUMENTATION.zh.md)
- **理解生成文件**：[生成文件说明](FILES_GENERATED.zh.md)
- **高级用法**：见下方章节

---

## 🔧 本地开发配置

适用于想在本地运行系统而不使用 Docker 的开发者：

### 1. 前置要求

- Python 3.11+
- pip
- LaTeX（用于 PDF 生成）
  - macOS: `brew install --cask mactex`
  - Ubuntu: `sudo apt-get install texlive-full`
  - Windows: 安装 [MiKTeX](https://miktex.org/)

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

**方式 A：使用 config.json**
```json
{
  "OPENAI_API_KEY": "your_openai_api_key_here"
}
```

**方式 B：使用环境变量**
```bash
export OPENAI_API_KEY=your_api_key_here
```

### 4. 启动 API 服务器

```bash
# 启动 API 服务器
python api_server.py

# 或直接使用 uvicorn（带自动重载）
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

API 将在 `http://localhost:8000` 可用：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

---

## 🚀 使用方式

### 方式 1：Web 界面（推荐）

使用系统最简单的方式。详细说明见上面的第二步。

**功能**：
- 📝 可视化课程配置表单
- 📊 实时进度监控
- 📁 结果文件浏览和下载
- 📤 Catalog 文件上传和管理
- 🔄 实时日志流式传输

### 方式 2：命令行

**入口点**：`run.py` – 主工作流入口点

```bash
# 简单课程生成
python run.py "机器学习导论"

# 指定模型
python run.py "数据结构" --model gpt-4o-mini

# 指定实验名称
python run.py "Web 开发" --exp web_dev_v1

# 交互式 Copilot 模式
python run.py "数据库系统" --copilot

# 使用 Catalog 模式
python run.py "软件工程" --catalog

# 使用特定 Catalog 文件
python run.py "AI 基础" --catalog ai_catalog

# 组合使用 Catalog 和 Copilot
python run.py "教育心理学" --copilot --catalog edu_psy
```

**命令行参数**：
```bash
python run.py <course_name> [OPTIONS]

必填参数:
  course_name              要设计的课程名称

可选参数:
  --copilot                启用交互式 Copilot 模式
  --catalog [name]         使用 catalog/ 目录中的结构化数据
                           （可选：指定 catalog 名称，不含 '.json'）
  --model MODEL            使用的 OpenAI 模型（默认：gpt-4o-mini）
  --exp EXP_NAME           保存输出的实验名称（默认：exp1）
```

### 方式 3：直接 API 调用

**API 服务器**：`api_server.py` – RESTful API 服务

```bash
# 先启动 API 服务器（如果不使用 Docker）
python api_server.py

# 生成课程
curl -X POST http://localhost:8000/api/course/generate \
  -H "Content-Type: application/json" \
  -H "X-OpenAI-API-Key: your_api_key_here" \
  -d '{
    "course_name": "机器学习导论",
    "model_name": "gpt-4o-mini",
    "exp_name": "ml_intro_v1"
  }'

# 检查任务状态
curl http://localhost:8000/api/course/status/{task_id}

# 获取结果文件
curl http://localhost:8000/api/course/results/{task_id}/files

# 下载文件
curl http://localhost:8000/api/course/results/{task_id}/download/chapter_1/slides.pdf \
  --output slides.pdf
```

完整 API 文档请查看 [API 文档](API_DOCUMENTATION.zh.md)。

---

## 📚 高级用法

### Catalog 模式

Catalog 文件提供结构化输入数据来指导课程生成过程。包括：
- 学生画像和背景
- 教师偏好和风格
- 课程结构要求
- 评估设计偏好
- 教学约束
- 机构要求

**使用 Catalog**：
```bash
# 使用默认 Catalog
python run.py "软件工程" --catalog

# 使用特定 Catalog 文件（不含 .json 扩展名）
python run.py "AI 基础" --catalog ai_catalog
# 系统会查找：catalog/ai_catalog.json

# 通过 Web 界面上传 Catalog
# 在 Web 界面中，选择"上传 Catalog 文件"并上传您的 JSON 文件
```

Catalog 格式详情请查看 [API 文档](API_DOCUMENTATION.zh.md#catalog-格式)。

### Copilot 模式

交互模式，在 ADDIE 工作流的每个阶段后提示反馈：
- **Analysis（分析）** 阶段：审查并反馈学习目标、资源评估、目标受众
- **Design（设计）** 阶段：审查并完善课程大纲、评估规划、期末项目
- **Development（开发）** 阶段：审查并调整生成的章节材料

```bash
python run.py "高级算法" --copilot --exp algo_course_v2
```

### 自动评估

**入口点**：`evaluate.py` – 自动评估和评分

```bash
# 评估特定实验
python evaluate.py --exp web_dev_v1
```

评估结果保存在 `eval/{experiment_name}/` 目录中。

### 后台执行与日志

对于长时间运行的任务，可以在后台运行：

```bash
# 在后台运行，输出到日志文件
nohup python run.py "高级机器学习" --exp ml_advanced > logs/ml_course.log 2>&1 &

# 监控进度
tail -f logs/ml_course.log

# 检查进程状态
ps aux | grep "python run.py"
```

---

## 📚 示例工作流

### 完整课程设计

```bash
# 步骤1：使用 Catalog 生成课程
python run.py "Python 基础" \
  --catalog python_catalog \
  --model gpt-4o \
  --exp py_course_v1

# 步骤2：评估结果
python evaluate.py --exp py_course_v1

# 步骤3：查看生成的材料
open exp/py_course_v1/result_syllabus_design.md
open exp/py_course_v1/chapter_1/slides.pdf
```

### 交互式开发（Copilot）

```bash
python run.py "高级算法" --copilot --exp algo_course_v2

# 系统会在每个阶段后提示反馈：
# - Analysis（分析）→ 反馈目标、资源、受众
# - Design（设计）→ 反馈大纲、评估
# - Development（开发）→ 反馈章节材料
```

---

## 📌 注意事项

* 如果您指定 `--catalog` 但不提供值，系统默认使用 `catalog/` 文件夹中的 `default_catalog.json`。
* 如果您提供名称（例如 `--catalog mydata`），系统期望找到 `catalog/mydata.json`。
* 生成的文件是增量保存的。文件一出现就可以下载，无需等待完成。
* Web 界面需要 API 正在运行（Docker 或本地）。确保 API 在配置的地址可访问。

---

## 📜 许可证

MIT License
