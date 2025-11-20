# Instructional Agents System - Workflow Documentation

## System Overview

This system is based on the ADDIE (Analyze, Design, Develop, Implement, Evaluate) instructional design model, using multiple LLM Agents to collaboratively and automatically generate complete course materials. The system workflow is divided into two main phases:

1. **Foundation Phase**: Define course objectives and structure
2. **Chapter Development Phase**: Generate detailed instructional materials for each chapter

---

## Complete Workflow

### Phase 1: Foundation Phase

The Foundation Phase contains 6 sequential deliberation tasks, each completed through collaboration by specialized Agents.

#### Task 1: Instructional Goals Definition

**Agents:**
- **Teaching Faculty**: Responsible for defining clear learning objectives based on accreditation standards, competency gaps, and institutional needs
- **Instructional Designer**: Responsible for reviewing learning objectives, assessing alignment with accreditation requirements, and suggesting modifications to ensure consistency within the broader curriculum
- **Summarizer**: Responsible for generating the final learning objectives document

**Input:**
- `course_name`: Course name
- `current_context`: Previous deliberation results (initially empty)
- `input_files`: `course_structure` and `institutional_requirements` from catalog

**Output:**
- `result_instructional_goals.md`: Well-defined learning objectives that align with accreditation standards, address curriculum gaps, and meet industry needs

**Function Description:**
Teaching Faculty proposes a draft of learning objectives, Instructional Designer reviews and provides modification suggestions, and finally Summarizer generates the final learning objectives document.

---

#### Task 2: Resource & Constraints Assessment

**Agents:**
- **Teaching Faculty**: Responsible for assessing course feasibility based on faculty expertise, facility resources, and scheduling constraints
- **Instructional Designer**: Responsible for assessing whether current instructional technologies and platforms support proposed courses, identifying potential limitations, and proposing viable solutions
- **Summarizer**: Generates a detailed resource and constraints assessment document

**Input:**
- `current_context`: Contains output from Task 1 (learning objectives)
- `input_files`: `teaching_constraints` and `institutional_requirements` from catalog

**Output:**
- `result_resource_assessment.md`: Detailed resource assessment including available resources, constraints, and technological requirements

**Function Description:**
Teaching Faculty assesses resource requirements, Instructional Designer evaluates technology support and limitations, ultimately generating a comprehensive resource and constraints assessment report.

---

#### Task 3: Target Audience & Needs Analysis

**Agents:**
- **Teaching Faculty**: Responsible for identifying student learning needs based on prior knowledge, enrollment trends, and academic performance data
- **Course Coordinator**: Responsible for providing institutional data on student demographics, enrollment trends, and past student feedback, and collaborating with professors to determine necessary course adjustments
- **Summarizer**: Generates target student profile and data-driven course adjustment recommendations

**Input:**
- `current_context`: Contains outputs from Task 1 and Task 2
- `input_files`: `student_profile` and `prior_feedback` from catalog

**Output:**
- `result_target_audience.md`: Comprehensive profile of target students (including prior knowledge, learning needs, and appropriate educational approaches), along with data-driven course adjustment recommendations

**Function Description:**
Teaching Faculty analyzes student learning needs, Course Coordinator provides institutional data, ultimately generating student profiles and course adjustment recommendations.

---

#### Task 4: Syllabus & Learning Objectives Design

**Agents:**
- **Teaching Faculty**: Responsible for creating a structured syllabus that defines course content, pacing, and expected learning outcomes
- **Instructional Designer**: Responsible for reviewing syllabus drafts, assessing alignment with institutional policies and accreditation requirements, and providing recommendations for improvement
- **Summarizer**: Generates a complete course syllabus including course structure, objectives, weekly topics, and assessment schedule

**Input:**
- `current_context`: Contains outputs from Task 1-3 (learning objectives, resource assessment, student analysis)
- `input_files`: `course_structure`, `institutional_requirements`, and `instructor_preferences` from catalog

**Output:**
- `result_syllabus_design.md`: Complete course syllabus including course structure, objectives, weekly topics, and assessment schedule (formatted clearly for easy parsing into chapters)

**Function Description:**
Teaching Faculty drafts the syllabus, Instructional Designer reviews and provides improvement suggestions, ultimately generating a complete course syllabus. This output will be subsequently processed into a chapter list.

---

#### Task 5: Assessment & Evaluation Planning

**Agents:**
- **Teaching Faculty**: Responsible for designing a course's assessment and evaluation strategy, defining project-based, milestone-driven assessments including formats, timing, grading rubrics, and submission logistics
- **Instructional Designer**: Responsible for evaluating whether assessment plans align with institutional policies, learning outcomes, and best practices in competency-based education, providing constructive feedback
- **Summarizer**: Generates a structured assessment planning document

**Input:**
- `current_context`: Contains outputs from Task 1-4
- `input_files`: `assessment_design` and `instructor_preferences` from catalog

**Output:**
- `result_assessment_planning.md`: Structured document outlining assessment types, milestone structure, grading criteria, submission formats, and delivery platforms

**Function Description:**
Teaching Faculty designs the assessment strategy, Instructional Designer reviews to ensure compliance with policies and best practices, ultimately generating a complete assessment planning document.

---

#### Task 6: Final Project Assessment Design

**Agents:**
- **Teaching Faculty**: Responsible for designing a project-based final assessment that replaces traditional exams
- **Instructional Designer**: Responsible for reviewing and refining the design of a final project, ensuring alignment with course objectives, student workload balance, and inclusive learning principles
- **Summarizer**: Generates a structured final project plan

**Input:**
- `current_context`: Contains outputs from Task 1-5
- `input_files`: `assessment_planning` from catalog

**Output:**
- `result_final_exam_project.md`: Final project plan including description, objectives, timeline, deliverables, grading rubric, and academic integrity guidelines

**Function Description:**
Teaching Faculty designs the final project, Instructional Designer reviews to ensure quality and fairness, ultimately generating a complete final project plan.

---

### Syllabus Processing

After completing Task 4, the system uses the **SyllabusProcessor Agent** to process the syllabus content:

**Agent:**
- **SyllabusProcessor**: Responsible for analyzing the course syllabus and extracting weekly topics and schedule, creating a structured chapter list

**Input:**
- `syllabus_content`: Output from Task 4 (`result_syllabus_design.md`)

**Output:**
- `processed_chapters.json`: JSON-formatted chapter list, each chapter containing `title` and `description` fields

**Function Description:**
Extracts chapter information from the syllabus, formats it into a standardized chapter list for subsequent chapter development.

---

### Phase 2: Chapter Development Phase

For each chapter extracted from the syllabus, the system executes the **SlidesDeliberation** process to generate detailed instructional materials.

#### SlidesDeliberation

**Agents:**
- **Instructional Designer**: Responsible for organizing course content into a logical slide structure, creating an outline that covers all key topics
- **Teaching Faculty**: Responsible for creating detailed educational content, clearly explaining concepts, providing examples, and making complex topics accessible
- **Teaching Assistant**: Responsible for creating LaTeX slides and detailed speaker notes, creating well-formatted slides and comprehensive speaking instructions

**Input:**
- `chapter`: Chapter information (containing `title` and `description`)
- `user_feedback`: User feedback (in copilot mode), including slides, script, assessment, and overall feedback
- `foundation_results`: All output results from the Foundation Phase
- `course_name`: Course name
- `catalog_dict`: Configuration from catalog (such as `slides_length`)

**Output:**
- `slides.tex`: Complete LaTeX slide source code
- `script.md`: Detailed speaking script
- `assessment.md`: Assessment content for each slide (questions, activities, learning objectives)

---

#### SlidesDeliberation Detailed Steps

**Step 0: Get Templates**
- Load LaTeX template from catalog (if available), or use default template

**Step 1: Generate Slides Outline**
- **Agent**: Instructional Designer
- **Input**: Chapter information, user feedback, `slides_length` configuration
- **Output**: JSON-formatted slides outline containing `slide_id`, `title`, and `description` for each slide

**Step 2: Generate Initial LaTeX**
- **Agent**: Teaching Assistant
- **Input**: Chapter information, slides outline, LaTeX template, user feedback
- **Output**: Initial LaTeX code with frame placeholders for all slides, parsed into `latex_dict` structure

**Step 3: Generate Slides Script Template**
- **Agent**: Teaching Assistant
- **Input**: Slides outline, user feedback
- **Output**: JSON-formatted script template containing `slide_id`, `title`, and `script` placeholders for each slide

**Step 4: Generate Assessment Template**
- **Agent**: Teaching Assistant
- **Input**: Chapter information, slides outline, user feedback, assessment requirements
- **Output**: JSON-formatted assessment template containing `slide_id`, `title`, and `assessment` structure for each slide (including question, activity, and learning objective placeholders)

**Step 5: For Each Slide - Generate Detailed Content**

For each slide, execute the following sub-steps:

##### Step 5.1: Generate Slide Draft
- **Agent**: Teaching Faculty
- **Input**: 
  - Current slide information
  - Adjacent slides context (for coherence)
  - Chapter information
  - User feedback
- **Output**: Detailed educational content draft containing concept explanations, examples, key points, and formulas/code snippets

##### Step 5.2: Generate Slide LaTeX
- **Agent**: Teaching Assistant
- **Input**: 
  - Slide information
  - Slide draft content
  - Current LaTeX frames (for reference)
  - User feedback
- **Output**: One or more LaTeX frames (can be split into multiple frames if content is too long, maximum 3 frames), updates `latex_dict`

##### Step 5.3: Generate Slide Script
- **Agent**: Teaching Assistant
- **Input**: 
  - Slide information
  - Slide draft content
  - All LaTeX frames for current slide
  - Adjacent slides' scripts (for smooth transitions)
  - User feedback
- **Output**: Detailed speaking script including introduction, key point explanations, frame transitions (if multiple frames), examples and connections, updates `slides_script`

##### Step 5.4: Generate Slide Assessment
- **Agent**: Teaching Assistant
- **Input**: 
  - Slide information
  - Slide draft content
  - Assessment template for current slide
  - User feedback
- **Output**: JSON-formatted detailed assessment content containing multiple-choice questions (3-5 questions, 4 options each), practical activities, learning objectives, and discussion questions, updates `assessment_content`

**Step 6: Compile Final LaTeX Source**
- Merge all slide frames into a complete LaTeX document
- **Output**: Complete `slides.tex` file

**Step 7: Compile Final Slides Script**
- Merge all slide scripts into a Markdown document
- **Output**: Complete `script.md` file

**Step 8: Compile Final Assessment**
- Merge all slide assessments into a Markdown document
- **Output**: Complete `assessment.md` file

---

### Final Compilation

After completing SlidesDeliberation for all chapters, the system uses **LaTeXCompiler** to compile all LaTeX files.

**Input:**
- All `slides.tex` files in chapter directories

**Output:**
- Compiled PDF files (if LaTeX compilation succeeds)

---

## Agent Role Summary

| Agent Name | Main Responsibilities | Participating Deliberations |
|-----------|---------------------|---------------------------|
| **Teaching Faculty** | Define instructional goals, assess resources, analyze student needs, design syllabus, plan assessments, create instructional content | All Tasks 1-6 in Foundation Phase, content generation in SlidesDeliberation |
| **Instructional Designer** | Review objectives, assess technology resources, organize slide structure | Tasks 1, 2, 4, 5, 6 in Foundation Phase, structure design in SlidesDeliberation |
| **Course Coordinator** | Provide institutional data and student feedback | Task 3 in Foundation Phase |
| **Summarizer** | Generate final document summaries | All Tasks 1-6 in Foundation Phase |
| **SyllabusProcessor** | Process syllabus and extract chapters | Syllabus Processing phase |
| **Teaching Assistant** | Create LaTeX code, speaking scripts, and assessment content | All steps in SlidesDeliberation |
| **LaTeXCompiler** | Compile LaTeX files to PDF | Final compilation phase |

---

## Data Flow Diagram

### Foundation Phase Data Flow

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

### Chapter Development Phase Data Flow

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

## Input-Output Summary Table

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

## Output File Structure

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

## Key Design Features

1. **Sequential Context Building**: Each task uses outputs from all previous tasks as context, ensuring consistency and coherence
2. **Multi-Agent Collaboration**: Each task has specialized Agent roles that collaborate through deliberation mechanisms
3. **Template-Based Generation**: SlidesDeliberation uses templates to ensure consistent output format
4. **Context-Aware Content**: Each slide's generation considers content from adjacent slides, ensuring coherence
5. **Iterative Refinement**: In copilot mode, users can re-run deliberations multiple times to improve results

---

## Copilot Mode

When copilot mode is enabled, users can provide feedback before and after each deliberation:

1. **Pre-Deliberation**: Users can provide suggestions before starting a deliberation
2. **Post-Deliberation**: Users can choose:
   - Continue to the next deliberation
   - Re-run the current deliberation with additional suggestions

All user suggestions are accumulated and used together when re-running, ensuring incremental improvements.

---

This document provides a complete description of the system workflow, including the roles of each Agent, input and output for each subtask, and how data flows through the system.
