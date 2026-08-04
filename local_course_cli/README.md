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
├── course_code_images.json
├── result_instructional_goals.md
├── result_resource_assessment.md
├── result_target_audience.md
├── result_syllabus_design.md
├── result_assessment_planning.md
├── result_final_exam_project.md
├── result_presentation_design.md
├── processed_chapters.json
├── course_slide_style.json
├── course_slide_style_source.md
└── statistics_slide_style.json
```

It never starts chapter generation. Presentation design is the seventh
foundation deliberation: the four roles used by the other foundation
deliberations choose one course-wide slide style and presentation method, then
save its readable summary in `result_presentation_design.md`. Repeating the same
command reloads the frozen decision and resumes only missing work. Use
`--reselect-presentation-design`
only when intentionally replacing the course-wide style. Omitted model,
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

Opt in to Carbon-rendered code images for the whole course:

```bash
./local_course_cli/course foundation "My Course" \
  --course-id my-course \
  --code-images on
```

The setting is off by default and persists in `course_code_images.json`.
Enabling it authorizes a lazy global
`npm install --global carbon-now-cli@2.1.0` only when a chapter actually
contains code and `carbon-now` is missing. Node.js and npm are prerequisites
and are not installed automatically. Any install or rendering failure warns
and falls back to the styled `<pre>` block. Use `--code-images off` on a
foundation or chapter command to persistently opt out and refinalize completed
HTML-derived artifacts.

Generated slide images use the same consolidated controls as `run.py`:

```bash
./local_course_cli/course foundation "My Course" \
  --course-id my-course \
  --image-generation on \
  --image-count on
```

`--image-generation` accepts `on`, `off`, or `replace`. `--image-count on`
always delegates the image count to the AI; `--image-count off` restores the
stored fixed cap. Omitted media flags preserve the saved course settings.

If a legacy `script.md` cannot be matched safely to its saved Beamer frames,
repair only the notes before finalization:

```bash
./local_course_cli/course chapter --course-id my-course --number 13 --repair-notes
```

The chapter command validates the complete foundation, loads it without new
foundation model calls, and creates only `exp/my-course/chapter_13/`. It
produces:

```text
chapter_<number>/
├── slides.tex
├── slides.pdf
├── html/
│   ├── slides.html
│   └── assets/
├── slides-html.pdf
├── slides-html.pptx
├── frontend-slides-manifest.json
├── script.md
├── assessment.md
└── statistics_slides_chapter_<number>.json
```

The `html/` directory is a portable offline bundle: keep `slides.html` beside
its `assets/` directory. Press `N` while presenting to toggle the correlated
speaker-notes panel; presenter UI is excluded from PDF and PPTX exports.
`slides-html.pptx` preserves the HTML appearance as one full-slide image per
PowerPoint slide; it is not element-editable.

Interrupted chapter runs resume from `_checkpoint.json`. Completed source
artifacts are never regenerated automatically. If the source files exist but
`slides.pdf` or a frontend export does not, the command runs only the missing
deterministic compilation/export stages. Changed LaTeX or course-style hashes
invalidate and rebuild the corresponding frontend artifacts without repeating
chapter model calls.

## Removing the CLI

Delete `local_course_cli/` to remove the wrapper and its virtual environment.
Course outputs under `exp/`, the original workflow, and the repository `.env`
remain untouched.
