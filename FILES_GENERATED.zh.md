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

# 生成文件说明

## 文件生成顺序和类型

系统会按照 ADDIE 工作流顺序生成以下文件：

### 📋 第一阶段：基础审议文件（Foundation Phase）

这些文件会在工作流开始时生成，位于 `exp/{实验名称}/` 根目录：

1. **`result_instructional_goals.md`**
   - 📝 学习目标定义
   - 包含课程的学习目标和教学目的
   - 生成时间：第1个审议完成后

2. **`result_resource_assessment.md`**
   - 📝 资源与约束评估
   - 包含教学资源、技术要求和约束条件
   - 生成时间：第2个审议完成后

3. **`result_target_audience.md`**
   - 📝 目标受众分析
   - 包含学生画像、学习需求和背景分析
   - 生成时间：第3个审议完成后

4. **`result_syllabus_design.md`**
   - 📝 课程大纲设计
   - 包含完整的课程大纲、周次安排和学习目标
   - 生成时间：第4个审议完成后

5. **`result_assessment_planning.md`**
   - 📝 评估规划
   - 包含评估方法、评分标准和评估时间表
   - 生成时间：第5个审议完成后

6. **`result_final_exam_project.md`**
   - 📝 期末项目设计
   - 包含期末项目的详细说明和要求
   - 生成时间：第6个审议完成后

7. **`processed_chapters.json`**
   - 📋 处理后的章节信息
   - 包含从大纲中提取的所有章节（标题和描述）
   - 生成时间：大纲处理完成后

8. **`statistics.json`**
   - 📊 统计信息
   - 包含每个审议的执行时间和Token使用量
   - 持续更新，每个审议完成后更新

### 📚 第二阶段：章节材料（Chapter Materials）

每个章节会在 `exp/{实验名称}/chapter_{序号}/` 目录下生成以下文件：

#### 每个章节包含：

1. **`slides.tex`**
   - 📄 LaTeX 幻灯片源代码
   - 使用 Beamer 格式，可直接编译为 PDF
   - 生成时间：章节幻灯片生成完成后

2. **`slides.pdf`**（如果编译成功）
   - 📕 编译后的 PDF 幻灯片
   - 由 `slides.tex` 自动编译生成
   - 生成时间：LaTeX 编译完成后

3. **`script.md`**
   - 📝 演讲脚本
   - 包含详细的讲解内容和说明
   - 生成时间：幻灯片脚本生成完成后

4. **`assessment.md`**
   - 📝 评估材料
   - 包含：
     - 选择题
     - 实践活动
     - 学习目标
     - 讨论问题
   - 生成时间：评估材料生成完成后

5. **`statistics_{章节ID}.json`**
   - 📊 章节统计信息
   - 包含该章节生成的时间和Token使用量

### 📁 目录结构示例

```
exp/{实验名称}/
├── result_instructional_goals.md          # 基础文件
├── result_resource_assessment.md
├── result_target_audience.md
├── result_syllabus_design.md
├── result_assessment_planning.md
├── result_final_exam_project.md
├── processed_chapters.json
├── statistics.json
│
├── chapter_1/                              # 第1章
│   ├── slides.tex
│   ├── slides.pdf
│   ├── script.md
│   ├── assessment.md
│   └── statistics_slides_chapter_1.json
│
├── chapter_2/                              # 第2章
│   ├── slides.tex
│   ├── slides.pdf
│   ├── script.md
│   ├── assessment.md
│   └── statistics_slides_chapter_2.json
│
└── ...                                     # 更多章节
```

## 文件生成时间线

### 典型时间线（假设有3个章节）：

| 时间 | 阶段 | 生成的文件 |
|------|------|-----------|
| 0-5分钟 | 基础审议1-2 | `result_instructional_goals.md`, `result_resource_assessment.md` |
| 5-10分钟 | 基础审议3-4 | `result_target_audience.md`, `result_syllabus_design.md`, `processed_chapters.json` |
| 10-15分钟 | 基础审议5-6 | `result_assessment_planning.md`, `result_final_exam_project.md` |
| 15-25分钟 | 第1章生成 | `chapter_1/slides.tex`, `chapter_1/script.md`, `chapter_1/assessment.md` |
| 25-30分钟 | 第1章编译 | `chapter_1/slides.pdf` |
| 30-40分钟 | 第2章生成 | `chapter_2/slides.tex`, `chapter_2/script.md`, `chapter_2/assessment.md` |
| 40-45分钟 | 第2章编译 | `chapter_2/slides.pdf` |
| ... | 后续章节 | 类似模式 |

**注意**：实际时间取决于：
- 章节数量
- 模型选择（gpt-4o 比 gpt-4o-mini 慢）
- 网络速度
- 内容复杂度

## 文件用途

### 📝 Markdown 文件（.md）
- 可直接在 Markdown 编辑器中查看
- 包含格式化的文本内容
- 适合阅读和编辑

### 📄 LaTeX 文件（.tex）
- 需要 LaTeX 编译器才能查看
- 可以编译为 PDF
- 包含专业的数学公式和图表支持

### 📕 PDF 文件（.pdf）
- 最终可用的幻灯片格式
- 可以直接用于演示
- 包含完整的格式和布局

### 📋 JSON 文件（.json）
- 结构化数据
- 可用于程序处理
- 包含元数据和统计信息

## 文件大小参考

- **Markdown 文件**：通常 5-50 KB
- **LaTeX 文件**：通常 10-100 KB
- **PDF 文件**：通常 50-500 KB（取决于内容）
- **JSON 文件**：通常 1-10 KB

## 下载建议

### 优先下载：
1. **`result_syllabus_design.md`** - 了解课程结构
2. **`processed_chapters.json`** - 查看章节列表
3. **`chapter_*/slides.pdf`** - 直接可用的幻灯片
4. **`chapter_*/script.md`** - 教学脚本

### 按需下载：
- 其他基础审议文件（用于参考）
- LaTeX 源文件（如需编辑）
- 评估材料（用于出题）

## 注意事项

1. **PDF 编译**：如果 LaTeX 编译失败，可能没有 PDF 文件
2. **文件顺序**：文件按生成顺序出现，不一定按章节顺序
3. **增量下载**：每个文件生成后立即可下载，无需等待全部完成
4. **文件更新**：如果重新运行任务，文件会被覆盖

## 文件图标说明

在前端界面中，不同文件类型会显示不同图标：

- 📝 Markdown 文件（.md）
- 📄 LaTeX 文件（.tex）
- 📕 PDF 文件（.pdf）
- 📋 JSON 文件（.json）
- 📄 其他文本文件
- 🐍 Python 文件（.py）
- 🌐 HTML 文件（.html）

