# Generated Files Guide

**Language / 语言**: [English](FILES_GENERATED.md) | [中文](FILES_GENERATED.zh.md)

## File Generation Order and Types

The system generates the following files in the order of the ADDIE workflow:

### 📋 Phase 1: Foundation Deliberation Files

These files are generated at the start of the workflow, located in `exp/{experiment_name}/` root directory:

1. **`result_instructional_goals.md`**
   - 📝 Learning objectives definition
   - Contains course learning objectives and teaching goals
   - Generated: After 1st deliberation completes

2. **`result_resource_assessment.md`**
   - 📝 Resource and constraint assessment
   - Contains teaching resources, technical requirements, and constraints
   - Generated: After 2nd deliberation completes

3. **`result_target_audience.md`**
   - 📝 Target audience analysis
   - Contains student profiles, learning needs, and background analysis
   - Generated: After 3rd deliberation completes

4. **`result_syllabus_design.md`**
   - 📝 Course syllabus design
   - Contains complete course syllabus, weekly schedule, and learning objectives
   - Generated: After 4th deliberation completes

5. **`result_assessment_planning.md`**
   - 📝 Assessment planning
   - Contains assessment methods, grading criteria, and assessment schedule
   - Generated: After 5th deliberation completes

6. **`result_final_exam_project.md`**
   - 📝 Final exam project design
   - Contains detailed final project description and requirements
   - Generated: After 6th deliberation completes

7. **`processed_chapters.json`**
   - 📋 Processed chapter information
   - Contains all chapters extracted from syllabus (titles and descriptions)
   - Generated: After syllabus processing completes

8. **`statistics.json`**
   - 📊 Statistics information
   - Contains execution time and token usage for each deliberation
   - Continuously updated, updated after each deliberation completes

### 📚 Phase 2: Chapter Materials

Each chapter generates the following files in `exp/{experiment_name}/chapter_{number}/` directory:

#### Each Chapter Contains:

1. **`slides.tex`**
   - 📄 LaTeX slide source code
   - Uses Beamer format, can be directly compiled to PDF
   - Generated: After chapter slide generation completes

2. **`slides.pdf`** (if compilation succeeds)
   - 📕 Compiled PDF slides
   - Automatically compiled from `slides.tex`
   - Generated: After LaTeX compilation completes

3. **`script.md`**
   - 📝 Presentation script
   - Contains detailed explanation content and instructions
   - Generated: After slide script generation completes

4. **`assessment.md`**
   - 📝 Assessment materials
   - Contains:
     - Multiple choice questions
     - Practice activities
     - Learning objectives
     - Discussion questions
   - Generated: After assessment material generation completes

5. **`statistics_{chapter_id}.json`**
   - 📊 Chapter statistics
   - Contains generation time and token usage for this chapter

### 📁 Directory Structure Example

```
exp/{experiment_name}/
├── result_instructional_goals.md          # Foundation files
├── result_resource_assessment.md
├── result_target_audience.md
├── result_syllabus_design.md
├── result_assessment_planning.md
├── result_final_exam_project.md
├── processed_chapters.json
├── statistics.json
│
├── chapter_1/                              # Chapter 1
│   ├── slides.tex
│   ├── slides.pdf
│   ├── script.md
│   ├── assessment.md
│   └── statistics_slides_chapter_1.json
│
├── chapter_2/                              # Chapter 2
│   ├── slides.tex
│   ├── slides.pdf
│   ├── script.md
│   ├── assessment.md
│   └── statistics_slides_chapter_2.json
│
└── ...                                     # More chapters
```

## File Generation Timeline

### Typical Timeline (assuming 3 chapters):

| Time | Phase | Generated Files |
|------|-------|----------------|
| 0-5 min | Foundation 1-2 | `result_instructional_goals.md`, `result_resource_assessment.md` |
| 5-10 min | Foundation 3-4 | `result_target_audience.md`, `result_syllabus_design.md`, `processed_chapters.json` |
| 10-15 min | Foundation 5-6 | `result_assessment_planning.md`, `result_final_exam_project.md` |
| 15-25 min | Chapter 1 generation | `chapter_1/slides.tex`, `chapter_1/script.md`, `chapter_1/assessment.md` |
| 25-30 min | Chapter 1 compilation | `chapter_1/slides.pdf` |
| 30-40 min | Chapter 2 generation | `chapter_2/slides.tex`, `chapter_2/script.md`, `chapter_2/assessment.md` |
| 40-45 min | Chapter 2 compilation | `chapter_2/slides.pdf` |
| ... | Subsequent chapters | Similar pattern |

**Note**: Actual time depends on:
- Number of chapters
- Model selection (gpt-4o is slower than gpt-4o-mini)
- Network speed
- Content complexity

## File Usage

### 📝 Markdown Files (.md)
- Can be directly viewed in Markdown editors
- Contains formatted text content
- Suitable for reading and editing

### 📄 LaTeX Files (.tex)
- Requires LaTeX compiler to view
- Can be compiled to PDF
- Contains professional mathematical formulas and chart support

### 📕 PDF Files (.pdf)
- Final usable slide format
- Can be directly used for presentations
- Contains complete formatting and layout

### 📋 JSON Files (.json)
- Structured data
- Can be used for program processing
- Contains metadata and statistics

## File Size Reference

- **Markdown files**: Usually 5-50 KB
- **LaTeX files**: Usually 10-100 KB
- **PDF files**: Usually 50-500 KB (depends on content)
- **JSON files**: Usually 1-10 KB

## Download Recommendations

### Priority Downloads:
1. **`result_syllabus_design.md`** - Understand course structure
2. **`processed_chapters.json`** - View chapter list
3. **`chapter_*/slides.pdf`** - Directly usable slides
4. **`chapter_*/script.md`** - Teaching scripts

### Download as Needed:
- Other foundation deliberation files (for reference)
- LaTeX source files (if editing needed)
- Assessment materials (for creating questions)

## Notes

1. **PDF Compilation**: If LaTeX compilation fails, PDF file may not exist
2. **File Order**: Files appear in generation order, not necessarily chapter order
3. **Incremental Download**: Each file can be downloaded immediately after generation, no need to wait for all to complete
4. **File Updates**: If task is re-run, files will be overwritten

## File Icon Guide

In the frontend interface, different file types display different icons:

- 📝 Markdown files (.md)
- 📄 LaTeX files (.tex)
- 📕 PDF files (.pdf)
- 📋 JSON files (.json)
- 📄 Other text files
- 🐍 Python files (.py)
- 🌐 HTML files (.html)

