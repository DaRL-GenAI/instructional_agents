# Local Course-Phase CLI

This directory is an isolated development wrapper around Instructional Agents.
It does not change `run.py` or anything under `src/`. Its virtual environment,
launcher, tests, and documentation all live here.

Generated course artifacts are deliberately stored outside this directory in
`exp/<course-id>/`. You can delete `local_course_cli/` without deleting those
course documents or damaging the original workflow.

## Setup

From the repository root:

```bash
./local_course_cli/setup.sh
```

The setup script creates `local_course_cli/.venv` with Python 3.12, installs the
project requirements and pytest, runs both test suites, checks LaTeX/Node
prerequisites, and authenticates with OpenAI using a non-generating
`models.list()` request. It loads `OPENAI_API_KEY` from the repository `.env`
without displaying it.

To recreate dependencies without running tests:

```bash
SKIP_TESTS=1 ./local_course_cli/setup.sh
```

Run diagnostics again at any time:

```bash
./local_course_cli/course doctor
./local_course_cli/course doctor --live-openai
```

## Generate foundation documents only

```bash
./local_course_cli/course foundation "My Course" \
  --course-id my-course \
  --catalog default_catalog \
  --model gpt-4o-mini
```

`--catalog` is optional. Catalog names refer to JSON files in `catalog/` and
must be passed without `.json`. New courses default to `gpt-4o-mini`.

This command creates or safely resumes only:

```text
exp/my-course/
├── .course_cli.json
├── result_instructional_goals.md
├── result_resource_assessment.md
├── result_target_audience.md
├── result_syllabus_design.md
├── result_assessment_planning.md
├── result_final_exam_project.md
└── processed_chapters.json
```

It never starts chapter generation. Repeating the same command reloads
completed foundation files and resumes only missing work. Omitted model,
catalog, seed, and temperature values inherit the existing manifest on reruns.
Conflicting settings are rejected instead of mixing outputs.

## List and generate chapters

List the chapter numbers extracted from the syllabus:

```bash
./local_course_cli/course chapters --course-id my-course
```

Generate exactly one chapter:

```bash
./local_course_cli/course chapter --course-id my-course --number 13
```

The chapter command validates the complete foundation, loads it without new
foundation model calls, and creates only `exp/my-course/chapter_13/`. It
produces `slides.tex`, `slides.pdf`, `script.md`, `assessment.md`, and chapter
statistics.

Interrupted chapter runs resume from `_checkpoint.json`. Completed source
artifacts are never regenerated automatically. If the source files exist but
`slides.pdf` does not, the command runs only `pdflatex`.

## Removing the CLI

Delete `local_course_cli/` to remove the wrapper and its virtual environment.
Course outputs under `exp/`, the original workflow, and the repository `.env`
remain untouched.
