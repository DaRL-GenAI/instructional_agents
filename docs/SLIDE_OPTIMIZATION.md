# 幻灯片优化功能使用指南

## 概述

幻灯片优化功能允许用户上传已有的PDF格式幻灯片，系统会分析内容并提供改进建议。这是一个增强版的catalog模式，支持：

1. 上传PDF文件夹并暂存
2. 根据用户需求按需提取相关内容
3. 分析现有内容并提供改进建议
4. 支持单章节或全课程优化

## 功能流程

```
1. 上传PDF文件夹 → 暂存（返回storage_id）
2. 用户描述需求 → 指定要优化的章节
3. 系统按需提取 → 只处理相关PDF内容
4. 创建知识库 → 存储提取的内容
5. 分析并建议 → 提供改进建议
```

## API端点

### 1. 上传PDF文件夹

```http
POST /api/slides/upload-folder
Content-Type: multipart/form-data

files: <PDF文件1>, <PDF文件2>, ...
```

**响应：**
```json
{
  "success": true,
  "storage_id": "storage_abc123",
  "total_files": 10,
  "message": "Successfully stored 10 PDF files. Use storage_id for analysis."
}
```

### 2. 优化指定章节

```http
POST /api/slides/optimize-chapter
Content-Type: application/json

{
  "storage_id": "storage_abc123",
  "chapter_name": "Chapter 3",
  "user_requirements": "I want to add more examples and improve explanations"
}
```

**响应：**
```json
{
  "success": true,
  "chapter": "Chapter 3",
  "knowledge_base_name": "storage_abc123_chapter_Ch3",
  "extracted_slides": 5,
  "analysis": {
    "analysis": "...",
    "analyzer": "Content Analyst"
  },
  "recommendations": {
    "recommendations": "...",
    "advisor": "Improvement Advisor"
  },
  "relevant_content": [...]
}
```

### 3. 优化全部课程

```http
POST /api/slides/optimize-all
Content-Type: application/json

{
  "storage_id": "storage_abc123",
  "user_requirements": "I want to improve all slides with more examples"
}
```

**响应：**
```json
{
  "success": true,
  "total_chapters": 5,
  "chapters": [
    {
      "success": true,
      "chapter": "Chapter 1",
      "knowledge_base_name": "...",
      "analysis": {...},
      "recommendations": {...}
    },
    ...
  ],
  "overall_summary": {
    "total_chapters": 5,
    "successful": 5,
    "failed": 0,
    "overall_recommendations": "..."
  }
}
```

### 4. 获取存储信息

```http
GET /api/slides/storage/{storage_id}
```

### 5. 列出知识库

```http
GET /api/slides/knowledge-bases
```

## 使用示例

### Python示例

```python
import requests

# 1. 上传PDF文件
files = [
    ('files', open('chapter1.pdf', 'rb')),
    ('files', open('chapter2.pdf', 'rb')),
]
response = requests.post(
    'http://localhost:8000/api/slides/upload-folder',
    files=files,
    headers={'X-OpenAI-API-Key': 'your-api-key'}
)
storage_id = response.json()['storage_id']

# 2. 优化指定章节
response = requests.post(
    'http://localhost:8000/api/slides/optimize-chapter',
    json={
        'storage_id': storage_id,
        'chapter_name': 'Chapter 1',
        'user_requirements': '添加更多实际案例和代码示例'
    },
    headers={'X-OpenAI-API-Key': 'your-api-key'}
)
result = response.json()
print(result['recommendations']['recommendations'])

# 3. 优化全部课程
response = requests.post(
    'http://localhost:8000/api/slides/optimize-all',
    json={
        'storage_id': storage_id,
        'user_requirements': '优化所有幻灯片，添加更多实例'
    },
    headers={'X-OpenAI-API-Key': 'your-api-key'}
)
all_results = response.json()
```

### JavaScript/前端示例

```javascript
// 1. 上传PDF文件
const formData = new FormData();
pdfFiles.forEach(file => {
    formData.append('files', file);
});

const uploadResponse = await fetch('/api/slides/upload-folder', {
    method: 'POST',
    headers: {
        'X-OpenAI-API-Key': apiKey
    },
    body: formData
});
const { storage_id } = await uploadResponse.json();

// 2. 优化指定章节
const optimizeResponse = await fetch('/api/slides/optimize-chapter', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-OpenAI-API-Key': apiKey
    },
    body: JSON.stringify({
        storage_id: storage_id,
        chapter_name: 'Chapter 3',
        user_requirements: '添加更多例子和改进解释'
    })
});
const result = await optimizeResponse.json();
console.log(result.recommendations.recommendations);
```

## 章节命名约定

系统支持多种章节命名格式：

- `Chapter 1`, `Chapter1`, `Ch1`
- `第1章`, `第 1 章`
- 文件名中包含章节信息也会被识别

## 存储位置

- PDF文件存储在：`knowledge_base/temp_storage/{storage_id}/`
- 知识库存储在：`knowledge_base/{knowledge_base_name}/`
- 提取的数据保存在：`knowledge_base/{knowledge_base_name}/extracted_data.json`

## 依赖要求

确保安装了以下Python包：

```bash
pip install PyPDF2 pdfplumber numpy
# 可选：用于高级向量搜索
pip install chromadb
```

## 注意事项

1. **按需提取**：系统会根据用户指定的章节和需求，只提取和处理相关的PDF内容，避免不必要的处理。

2. **自动章节检测**：如果用户选择"优化全部课程"，系统会自动检测所有章节（从文件名或PDF内容中）。

3. **知识库复用**：每个章节的知识库是独立的，可以单独查询和分析。

4. **OpenAI API Key**：需要有效的OpenAI API Key来生成embeddings和分析内容。

## 与现有系统的集成

这个功能可以：
- 作为catalog模式的增强版使用
- 生成的内容可以结合到现有的course generation流程中
- 改进建议可以作为用户输入反馈到系统中

## 故障排除

1. **PDF无法提取文本**：确保PDF不是纯图片格式，或者使用OCR功能。

2. **章节无法识别**：检查文件名或PDF内容是否包含章节信息，可以手动指定章节名称。

3. **Embedding生成失败**：检查OpenAI API Key是否有效，以及网络连接是否正常。

## 未来改进

- [ ] 支持OCR识别图片中的文本
- [ ] 支持更多章节识别格式
- [ ] 集成到前端界面
- [ ] 支持批量上传和异步处理
- [ ] 支持更多向量数据库选项

