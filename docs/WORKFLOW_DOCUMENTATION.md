# Instructional Agents System - Workflow Documentation

## 系统概述

本系统基于ADDIE（Analyze, Design, Develop, Implement, Evaluate）教学设计模型，使用多个LLM Agent协作自动生成完整的课程材料。系统工作流程分为两个主要阶段：

1. **Foundation Phase（基础阶段）**：定义课程目标和结构
2. **Chapter Development Phase（章节开发阶段）**：为每个章节生成详细的教学材料

---

## 完整工作流程

### Phase 1: Foundation Phase（基础阶段）

基础阶段包含6个顺序执行的deliberation任务，每个任务都有专门的Agent协作完成。

#### Task 1: Instructional Goals Definition（教学目标定义）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责根据认证标准、能力差距和机构需求定义清晰的学习目标
- **Instructional Designer（教学设计师）**: 负责审查学习目标，评估是否符合认证要求，并建议修改以确保与整体课程的一致性
- **Summarizer（总结者）**: 负责生成最终的学习目标文档

**Input:**
- `course_name`: 课程名称
- `current_context`: 之前的讨论结果（初始为空）
- `input_files`: 来自catalog的`course_structure`和`institutional_requirements`

**Output:**
- `result_instructional_goals.md`: 定义好的学习目标，符合认证标准、解决课程缺口、满足行业需求

**功能描述:**
教学教师提出学习目标草案，教学设计师审查并提出修改建议，最后由Summarizer生成最终的学习目标文档。

---

#### Task 2: Resource & Constraints Assessment（资源与约束评估）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责评估基于教师专业知识、设施资源和时间安排的课程可行性
- **Instructional Designer（教学设计师）**: 负责评估当前教学技术和平台是否支持课程，识别潜在限制，并提出可行解决方案
- **Summarizer（总结者）**: 生成详细的资源和约束评估文档

**Input:**
- `current_context`: 包含Task 1的输出（学习目标）
- `input_files`: 来自catalog的`teaching_constraints`和`institutional_requirements`

**Output:**
- `result_resource_assessment.md`: 详细的资源评估，包括可用资源、约束和技术要求

**功能描述:**
教学教师评估资源需求，教学设计师评估技术支持和限制，最终生成全面的资源和约束评估报告。

---

#### Task 3: Target Audience & Needs Analysis（目标受众与需求分析）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责基于先验知识、注册趋势和学术表现数据识别学生学习需求
- **Course Coordinator（课程协调员）**: 负责提供学生人口统计学、注册趋势和过去学生反馈的机构数据，并与教授协作确定必要的课程调整
- **Summarizer（总结者）**: 生成目标学生档案和基于数据的课程调整建议

**Input:**
- `current_context`: 包含Task 1和Task 2的输出
- `input_files`: 来自catalog的`student_profile`和`prior_feedback`

**Output:**
- `result_target_audience.md`: 目标学生的综合档案（包括先验知识、学习需求和适当的教育方法），以及基于数据的课程调整建议

**功能描述:**
教学教师分析学生学习需求，课程协调员提供机构数据，最终生成学生档案和课程调整建议。

---

#### Task 4: Syllabus & Learning Objectives Design（课程大纲与学习目标设计）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责创建定义课程内容、节奏和预期学习结果的结构化大纲
- **Instructional Designer（教学设计师）**: 负责审查大纲草案，评估是否符合机构政策和认证要求，并提供改进建议
- **Summarizer（总结者）**: 生成完整的课程大纲，包含课程结构、目标、每周主题和评估计划

**Input:**
- `current_context`: 包含Task 1-3的输出（学习目标、资源评估、学生分析）
- `input_files`: 来自catalog的`course_structure`、`institutional_requirements`和`instructor_preferences`

**Output:**
- `result_syllabus_design.md`: 完整的课程大纲，包括课程结构、目标、每周主题和评估计划（格式清晰，易于解析为章节）

**功能描述:**
教学教师起草大纲，教学设计师审查并提出改进建议，最终生成完整的课程大纲。此输出将被后续处理为章节列表。

---

#### Task 5: Assessment & Evaluation Planning（评估与评价规划）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责设计课程的评估和评价策略，定义项目驱动、里程碑式的评估，包括格式、时间、评分标准和提交物流
- **Instructional Designer（教学设计师）**: 负责评估评估计划是否符合机构政策、学习结果和能力教育最佳实践，提供建设性反馈
- **Summarizer（总结者）**: 生成结构化的评估规划文档

**Input:**
- `current_context`: 包含Task 1-4的输出
- `input_files`: 来自catalog的`assessment_design`和`instructor_preferences`

**Output:**
- `result_assessment_planning.md`: 评估类型的结构化文档，包括里程碑结构、评分标准、提交格式和交付平台

**功能描述:**
教学教师设计评估策略，教学设计师审查以确保符合政策和最佳实践，最终生成完整的评估规划文档。

---

#### Task 6: Final Project Assessment Design（最终项目评估设计）

**Agents:**
- **Teaching Faculty（教学教师）**: 负责设计基于项目的最终评估，取代传统考试
- **Instructional Designer（教学设计师）**: 负责审查和优化最终项目设计，确保符合课程目标、学生工作量平衡和包容性学习原则
- **Summarizer（总结者）**: 生成结构化的最终项目计划

**Input:**
- `current_context`: 包含Task 1-5的输出
- `input_files`: 来自catalog的`assessment_planning`

**Output:**
- `result_final_exam_project.md`: 最终项目计划，包括描述、目标、时间表、交付物、评分标准和学术诚信指南

**功能描述:**
教学教师设计最终项目，教学设计师审查以确保质量和公平性，最终生成完整的最终项目计划。

---

### Syllabus Processing（大纲处理）

在完成Task 4后，系统使用**SyllabusProcessor Agent**处理大纲内容：

**Agent:**
- **SyllabusProcessor**: 负责分析课程大纲并提取每周主题和时间表，创建结构化的章节列表

**Input:**
- `syllabus_content`: Task 4的输出（`result_syllabus_design.md`）

**Output:**
- `processed_chapters.json`: JSON格式的章节列表，每个章节包含`title`和`description`字段

**功能描述:**
从大纲中提取章节信息，格式化为标准化的章节列表，供后续章节开发使用。

---

### Phase 2: Chapter Development Phase（章节开发阶段）

对于每个从大纲中提取的章节，系统执行**SlidesDeliberation**流程，生成详细的教学材料。

#### SlidesDeliberation（幻灯片审议）

**Agents:**
- **Instructional Designer（教学设计师）**: 负责将课程内容组织成逻辑化的幻灯片结构，创建涵盖所有关键主题的纲要
- **Teaching Faculty（教学教师）**: 负责创建详细的教学内容，清晰解释概念，提供示例，使复杂主题易于理解
- **Teaching Assistant（教学助理）**: 负责创建LaTeX幻灯片和详细的演讲笔记，创建格式良好的幻灯片和全面的演讲说明

**Input:**
- `chapter`: 章节信息（包含`title`和`description`）
- `user_feedback`: 用户反馈（在copilot模式下），包含slides、script、assessment和overall反馈
- `foundation_results`: 基础阶段的所有输出结果
- `course_name`: 课程名称
- `catalog_dict`: 来自catalog的配置（如`slides_length`）

**Output:**
- `slides.tex`: 完整的LaTeX幻灯片源代码
- `script.md`: 详细的演讲脚本
- `assessment.md`: 每张幻灯片的评估内容（问题、活动、学习目标）

---

#### SlidesDeliberation详细步骤

**Step 0: 获取模板（Get Templates）**
- 从catalog中加载LaTeX模板（如果可用），或使用默认模板

**Step 1: 生成幻灯片纲要（Generate Slides Outline）**
- **Agent**: Instructional Designer
- **Input**: 章节信息、用户反馈、`slides_length`配置
- **Output**: JSON格式的幻灯片纲要，包含每张幻灯片的`slide_id`、`title`和`description`

**Step 2: 生成初始LaTeX模板（Generate Initial LaTeX）**
- **Agent**: Teaching Assistant
- **Input**: 章节信息、幻灯片纲要、LaTeX模板、用户反馈
- **Output**: 包含所有幻灯片框架占位符的初始LaTeX代码，解析为`latex_dict`结构

**Step 3: 生成幻灯片脚本模板（Generate Slides Script Template）**
- **Agent**: Teaching Assistant
- **Input**: 幻灯片纲要、用户反馈
- **Output**: JSON格式的脚本模板，包含每张幻灯片的`slide_id`、`title`和`script`占位符

**Step 4: 生成评估模板（Generate Assessment Template）**
- **Agent**: Teaching Assistant
- **Input**: 章节信息、幻灯片纲要、用户反馈、评估要求
- **Output**: JSON格式的评估模板，包含每张幻灯片的`slide_id`、`title`和`assessment`结构（包含问题、活动、学习目标占位符）

**Step 5: 为每张幻灯片生成详细内容（For Each Slide）**

对每张幻灯片执行以下子步骤：

##### Step 5.1: 生成幻灯片草案（Generate Slide Draft）
- **Agent**: Teaching Faculty
- **Input**: 
  - 当前幻灯片信息
  - 相邻幻灯片上下文（用于保持连贯性）
  - 章节信息
  - 用户反馈
- **Output**: 详细的教学内容草案，包含概念解释、示例、关键点和公式/代码片段

##### Step 5.2: 生成幻灯片LaTeX代码（Generate Slide LaTeX）
- **Agent**: Teaching Assistant
- **Input**: 
  - 幻灯片信息
  - 幻灯片草案内容
  - 当前的LaTeX框架（用于参考）
  - 用户反馈
- **Output**: 一张或多张LaTeX框架（如果内容过长，可以分成多个框架，最多3个），更新`latex_dict`

##### Step 5.3: 生成幻灯片脚本（Generate Slide Script）
- **Agent**: Teaching Assistant
- **Input**: 
  - 幻灯片信息
  - 幻灯片草案内容
  - 当前幻灯片的所有LaTeX框架
  - 相邻幻灯片的脚本（用于平滑过渡）
  - 用户反馈
- **Output**: 详细的演讲脚本，包含介绍、关键点解释、框架间过渡（如果有多帧）、示例和连接内容，更新`slides_script`

##### Step 5.4: 生成幻灯片评估（Generate Slide Assessment）
- **Agent**: Teaching Assistant
- **Input**: 
  - 幻灯片信息
  - 幻灯片草案内容
  - 当前幻灯片的评估模板
  - 用户反馈
- **Output**: JSON格式的详细评估内容，包含多选题（3-5个问题，每个4个选项）、实践活动、学习目标和讨论问题，更新`assessment_content`

**Step 6: 编译最终LaTeX源代码（Compile Final LaTeX Source）**
- 将所有幻灯片框架合并为完整的LaTeX文档
- **Output**: 完整的`slides.tex`文件

**Step 7: 编译最终幻灯片脚本（Compile Final Slides Script）**
- 将所有幻灯片脚本合并为Markdown文档
- **Output**: 完整的`script.md`文件

**Step 8: 编译最终评估（Compile Final Assessment）**
- 将所有幻灯片评估合并为Markdown文档
- **Output**: 完整的`assessment.md`文件

---

### 最终编译（Final Compilation）

在完成所有章节的SlidesDeliberation后，系统使用**LaTeXCompiler**编译所有LaTeX文件。

**Input:**
- 所有章节目录中的`slides.tex`文件

**Output:**
- 编译后的PDF文件（如果LaTeX编译成功）

---

## Agent角色总结

| Agent名称 | 主要职责 | 参与的Deliberation |
|-----------|---------|-------------------|
| **Teaching Faculty** | 定义教学目标、评估资源、分析学生需求、设计大纲、规划评估、创建教学内容 | Foundation Phase的所有Task 1-6，SlidesDeliberation的内容生成 |
| **Instructional Designer** | 审查目标、评估技术资源、组织幻灯片结构 | Foundation Phase的Task 1, 2, 4, 5, 6，SlidesDeliberation的结构设计 |
| **Course Coordinator** | 提供机构数据和学生反馈 | Foundation Phase的Task 3 |
| **Summarizer** | 生成最终文档摘要 | Foundation Phase的所有Task 1-6 |
| **SyllabusProcessor** | 处理大纲并提取章节 | Syllabus Processing阶段 |
| **Teaching Assistant** | 创建LaTeX代码、演讲脚本和评估内容 | SlidesDeliberation的所有步骤 |
| **LaTeXCompiler** | 编译LaTeX文件为PDF | 最终编译阶段 |

---

## 数据流图

### Foundation Phase数据流

```
Course Name + Catalog Data
    ↓
Task 1: Instructional Goals Definition
    ↓ (Learning Objectives)
Task 2: Resource & Constraints Assessment
    ↓ (Resource Assessment)
Task 3: Target Audience & Needs Analysis
    ↓ (Student Profile)
Task 4: Syllabus & Learning Objectives Design
    ↓ (Syllabus)
SyllabusProcessor → Processed Chapters (JSON)
    ↓ (Assessment Planning)
Task 5: Assessment & Evaluation Planning
    ↓ (Final Project Design)
Task 6: Final Project Assessment Design
```

### Chapter Development Phase数据流

```
Chapter Information
    ↓
SlidesDeliberation
    ├─ Step 1: Slides Outline (JSON)
    ├─ Step 2: Initial LaTeX Template
    ├─ Step 3: Script Template (JSON)
    └─ Step 4: Assessment Template (JSON)
    ↓
For Each Slide:
    ├─ Step 5.1: Slide Draft (Content)
    ├─ Step 5.2: Slide LaTeX (Frames)
    ├─ Step 5.3: Slide Script (Text)
    └─ Step 5.4: Slide Assessment (JSON)
    ↓
Compilation:
    ├─ slides.tex
    ├─ script.md
    └─ assessment.md
```

---

## 输入输出总结表

### Foundation Phase Tasks

| Task | Input | Output |
|------|-------|--------|
| Task 1: Instructional Goals | Course name, Catalog: course_structure, institutional_requirements | result_instructional_goals.md |
| Task 2: Resource Assessment | Task 1 output, Catalog: teaching_constraints, institutional_requirements | result_resource_assessment.md |
| Task 3: Target Audience | Task 1-2 outputs, Catalog: student_profile, prior_feedback | result_target_audience.md |
| Task 4: Syllabus Design | Task 1-3 outputs, Catalog: course_structure, institutional_requirements, instructor_preferences | result_syllabus_design.md |
| Task 5: Assessment Planning | Task 1-4 outputs, Catalog: assessment_design, instructor_preferences | result_assessment_planning.md |
| Task 6: Final Project | Task 1-5 outputs, Catalog: assessment_planning | result_final_exam_project.md |

### Syllabus Processing

| Step | Input | Output |
|------|-------|--------|
| Syllabus Processing | result_syllabus_design.md | processed_chapters.json |

### Chapter Development (per chapter)

| Step | Input | Output |
|------|-------|--------|
| Slides Outline | Chapter info, User feedback, slides_length | slides_outline (JSON) |
| Initial LaTeX | Chapter info, slides_outline, LaTeX template | latex_dict (structured) |
| Script Template | slides_outline, User feedback | slides_script (JSON) |
| Assessment Template | Chapter info, slides_outline, User feedback | assessment_template (JSON) |
| For Each Slide: | | |
| - Slide Draft | Slide info, Context slides, Chapter info | slide_draft (text) |
| - Slide LaTeX | Slide info, slide_draft, Current frames | Updated latex_dict |
| - Slide Script | Slide info, slide_draft, LaTeX frames, Adjacent scripts | Updated slides_script |
| - Slide Assessment | Slide info, slide_draft, Assessment template | Updated assessment_content |
| Compilation | All generated content | slides.tex, script.md, assessment.md |

---

## 文件结构输出

```
exp/{experiment_name}/
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
│   ├── script.md
│   ├── assessment.md
│   └── statistics_slides_chapter_1.json
├── chapter_2/
│   └── ...
└── ...
```

---

## 关键设计特点

1. **Sequential Context Building（顺序上下文构建）**: 每个任务都使用之前所有任务的输出作为上下文，确保一致性和连贯性
2. **Multi-Agent Collaboration（多Agent协作）**: 每个任务都有专门的Agent角色，通过deliberation机制协作
3. **Template-Based Generation（基于模板生成）**: SlidesDeliberation使用模板确保输出格式一致性
4. **Context-Aware Content（上下文感知内容）**: 每个幻灯片的生成都考虑相邻幻灯片的内容，确保连贯性
5. **Iterative Refinement（迭代优化）**: 在copilot模式下，用户可以多次重新运行deliberation以改进结果

---

## Copilot Mode（副驾驶模式）

当启用copilot模式时，用户可以在每个deliberation前后提供反馈：

1. **Pre-Deliberation**: 用户可以在开始deliberation前提供建议
2. **Post-Deliberation**: 用户可以选择：
   - 继续到下一个deliberation
   - 使用额外建议重新运行当前deliberation

所有的用户建议都会被累积并在重新运行时一起使用，确保改进是增量的。

---

本文档提供了系统工作流程的完整说明，包括各个Agent的角色、每个子任务的输入输出，以及数据在系统中的流动方式。

