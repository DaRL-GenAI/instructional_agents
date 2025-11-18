<div align="right" style="margin-bottom: 20px; margin-top: 10px;">
  <button onclick="switchLanguage('en')" id="lang-en" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #e2e8f0; background: white; color: #64748b; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇺🇸 English</button>
  <button onclick="switchLanguage('zh')" id="lang-zh" style="padding: 8px 16px; margin: 0 4px; border: 2px solid #14b8a6; background: #14b8a6; color: white; border-radius: 6px; cursor: pointer; font-weight: 600; transition: all 0.3s ease;">🇨🇳 中文</button>
</div>

<script>
function switchLanguage(lang) {
    localStorage.setItem('preferredLanguage', lang);
    if (lang === 'en') {
        window.location.href = window.location.pathname.replace('.zh.md', '.md');
    } else {
        window.location.href = window.location.pathname.replace('.md', '.zh.md');
    }
}
document.addEventListener('DOMContentLoaded', function() {
    const savedLang = localStorage.getItem('preferredLanguage') || 'zh';
    if (savedLang === 'en' && window.location.pathname.includes('.zh.md')) {
        window.location.href = window.location.pathname.replace('.zh.md', '.md');
    }
});
</script>

<style>
button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}
</style>

# Instructional Agents API 文档

## 概述

Instructional Agents API 提供了基于 ADDIE 模型的自动化课程材料生成服务。系统通过 Docker 容器化部署，提供 RESTful API 接口和 Web 前端界面。

## 快速开始

### 1. 环境准备

确保已安装：
- Docker 和 Docker Compose
- 或 Python 3.11+（本地开发）

### 2. 配置环境变量

创建 `.env` 文件（参考 `.env.example`）：

```bash
OPENAI_API_KEY=your_openai_api_key_here
API_PORT=8000
```

### 3. 使用 Docker 启动（推荐）

```bash
# 构建并启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4. 本地开发模式

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 API 服务器
python api_server.py

# 或使用 uvicorn
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
```

### 5. 访问前端

打开浏览器访问：`http://localhost:8000`（如果配置了前端服务）

或直接打开 `frontend/index.html` 文件（需要配置 CORS）

## API 端点

### 健康检查

```http
GET /health
```

**响应：**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-01T00:00:00"
}
```

### 生成课程

```http
POST /api/course/generate
Content-Type: application/json

{
  "course_name": "机器学习导论",
  "model_name": "gpt-4o-mini",
  "exp_name": "ml_intro_v1",
  "copilot": false,
  "catalog": "default_catalog",
  "catalog_data": {...}
}
```

**响应：**
```json
{
  "task_id": "uuid-string",
  "status": "started",
  "message": "Course generation started"
}
```

### 查询任务状态

```http
GET /api/course/status/{task_id}
```

**响应：**
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

**状态值：**
- `pending`: 等待中
- `running`: 运行中
- `completed`: 已完成
- `failed`: 失败

### 获取结果文件列表

```http
GET /api/course/results/{task_id}/files
```

**响应：**
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

### 下载文件

```http
GET /api/course/results/{task_id}/download/{file_path}
```

直接下载生成的文件。

### 上传 Catalog

```http
POST /api/catalog/upload
Content-Type: multipart/form-data

file: <catalog.json>
```

**响应：**
```json
{
  "success": true,
  "filename": "uploaded_abc123_catalog.json",
  "message": "Catalog uploaded successfully"
}
```

### 列出 Catalog

```http
GET /api/catalog/list
```

**响应：**
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

## 请求参数说明

### CourseRequest

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| course_name | string | 是 | 课程名称 |
| model_name | string | 否 | OpenAI 模型（默认：gpt-4o-mini） |
| exp_name | string | 否 | 实验名称（默认：default） |
| copilot | boolean | 否 | 是否启用 Copilot 模式 |
| catalog | string | 否 | Catalog 文件名（不含 .json） |
| catalog_data | object | 否 | Catalog 数据（JSON 对象） |

## 工作流程

1. **提交任务**：调用 `/api/course/generate` 创建生成任务
2. **轮询状态**：定期调用 `/api/course/status/{task_id}` 检查进度
3. **获取结果**：任务完成后调用 `/api/course/results/{task_id}/files` 获取文件列表
4. **下载文件**：使用 `/api/course/results/{task_id}/download/{file_path}` 下载文件

## Catalog 格式

Catalog JSON 文件应包含以下结构：

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

## 输出结构

生成的文件保存在 `exp/{exp_name}/` 目录下：

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

## 错误处理

API 使用标准 HTTP 状态码：

- `200`: 成功
- `400`: 请求错误（如无效的 JSON）
- `404`: 资源未找到（如任务不存在）
- `500`: 服务器错误

错误响应格式：

```json
{
  "detail": "Error message here"
}
```

## 性能考虑

- 课程生成可能需要 **10-60 分钟**，取决于章节数量和模型选择
- 建议使用 **WebSocket** 或 **Server-Sent Events** 进行实时进度更新（当前版本使用轮询）
- 大文件下载建议使用流式传输

## 安全建议

1. **生产环境**：
   - 限制 CORS 来源
   - 使用 HTTPS
   - 添加身份验证
   - 限制 API 密钥访问

2. **API 密钥管理**：
   - 使用环境变量，不要硬编码
   - 使用密钥管理服务（如 AWS Secrets Manager）

3. **资源限制**：
   - 设置 Docker 资源限制
   - 限制并发任务数
   - 设置请求超时

## 故障排查

### 常见问题

1. **Docker 构建失败**
   - 检查网络连接（需要下载 LaTeX 包）
   - 确保有足够的磁盘空间（LaTeX 包较大）

2. **API 服务无法启动**
   - 检查 `OPENAI_API_KEY` 是否设置
   - 检查端口是否被占用

3. **任务一直处于 pending 状态**
   - 检查容器日志：`docker-compose logs api`
   - 检查是否有足够的资源

4. **LaTeX 编译失败**
   - 检查生成的 `.tex` 文件语法
   - 查看编译日志：`exp/{exp_name}/.cache/`

## 开发指南

### 添加新端点

1. 在 `api_server.py` 中添加路由函数
2. 定义请求/响应模型（使用 Pydantic）
3. 更新本文档

### 修改工作流

主要逻辑在 `ADDIE.py` 和 `run.py` 中，修改后需要重启 API 服务。

## 许可证

MIT License

