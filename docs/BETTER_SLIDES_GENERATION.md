# Better Slides Generation Branch

This document is the single documentation source for changes introduced on the
`better-slides-generation` branch. All other Markdown files under `docs/` are
kept identical to `main` so the branch-specific workflow remains isolated.

## Scope and baseline

- Branch: `better-slides-generation`
- Baseline: `main` at `1c2a9f9`
- Primary entry point: `python3 run.py`
- Main result: the original instructional workflow now selects one validated
  course-wide presentation design and produces offline HTML slides, an
  HTML-derived PDF, and an HTML-derived PPTX for every chapter.

The branch preserves the original Beamer source and PDF workflow. The new HTML
artifacts are additional outputs, not replacements for `slides.tex` or
`slides.pdf`.

## Quick start

### Standard course generation

```bash
python3 run.py "Introduction to Machine Learning" \
  --exp ml_course_v1
```

This uses the default stored media settings. For a new experiment, generated
slide images and Carbon code images are off by default.

### Enable generated images with automatic AI-selected counts

```bash
python3 run.py "Systems Thinking" \
  --exp systems_v1 \
  --image-generation on \
  --image-count on
```

### Enable Carbon-rendered code images

```bash
python3 run.py "Programming Languages" \
  --exp programming_v1 \
  --code-images on
```

### Enable both image systems

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --image-generation on \
  --image-count on \
  --code-images on
```

### Resume an interrupted experiment

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --resume
```

Omitted media flags preserve the settings already stored in the experiment
directory.

### Force replacement of generated images

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --resume \
  --image-generation replace
```

`replace` enables generated images persistently but is itself a one-run action.
It bypasses valid generated-image cache entries for chapters processed during
that invocation.

### Disable generated images or code images

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --resume \
  --image-generation off \
  --code-images off
```

### Re-select the presentation design

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --resume \
  --reselect-presentation-design
```

Re-selection is intentionally explicit because it can invalidate and rebuild
frontend artifacts across completed chapters.

### Add image guidance to a legacy experiment

Experiments created before this branch may have a frozen presentation design
without image guidance. Upgrade them with:

```bash
python3 run.py "Computational Methods" \
  --exp computational_methods_v1 \
  --resume \
  --reselect-presentation-design \
  --image-generation on \
  --image-count on
```

## Final command-line interface

### New branch flags

| Flag | Values | Persistence | Behavior |
|---|---|---|---|
| `--image-generation` | `on`, `off`, `replace` | `on`/`off` persist; `replace` persists enablement but replacement is one-run | Controls generated instructional imagery |
| `--image-count` | `on`, `off` | Persistent | `on` always delegates the count to the AI; `off` restores the stored fixed cap |
| `--code-images` | `on`, `off` | Persistent | Controls Carbon-rendered code PNGs versus styled HTML code blocks |
| `--reselect-presentation-design` | Boolean switch | One-run action | Replaces the frozen course-wide presentation design |

For a new experiment, the stored fixed generated-image cap is 3. When
`--image-count on` is active, that cap remains stored but is not applied; the AI
may select any number of strong eligible opportunities, including zero. Using
`--image-count off` clears automatic-count mode and restores the stored cap.

All three value-based flags default to no override. Omitting them preserves the
experiment's saved configuration.

### Removed development spellings

Earlier commits on this branch temporarily exposed more granular switches.
They were consolidated before the branch's final state:

| Removed branch flag | Final equivalent |
|---|---|
| `--enable-image-generation` | `--image-generation on` |
| `--replace-images` | `--image-generation replace` |
| `--max-images-per-chapter N` | Removed from the CLI; fixed-cap mode uses the stored cap |
| `--ai-decides-image-count` | `--image-count on` |
| `--enable-code-images` | `--code-images on` |
| `--disable-code-images` | `--code-images off` |

### Pre-existing flags preserved from `main`

The branch does not rename or change the defaults of the original `run.py`
flags:

```text
course_name
--copilot [SOURCE]
--catalog [NAME]
--model MODEL
--exp EXP
--seed SEED
--temperature TEMPERATURE
--resume
--optimize STORAGE_ID
--requirements TEXT
--chapter NAME
--pptx
--convert-pptx DIR
```

`--convert-pptx` remains the legacy conversion-only mode. The branch's new
frontend finalizer creates `slides-html.pptx` independently for every finalized
chapter.

## Course-wide presentation design

The branch adds presentation design as the seventh foundation deliberation.
The Teaching Faculty, Instructional Designer, Course Coordinator, and
Summarizer evaluate the course context and select one packaged presentation
style for the whole course.

The decision produces:

- `result_presentation_design.md`: readable decision summary.
- `course_slide_style.json`: validated design authority used by renderers.
- `course_slide_style_source.md`: selected packaged style source.
- `statistics_slide_style.json`: selection and materialization statistics.

The selected design is frozen and reused on ordinary resumes. It can be
replaced only through `--reselect-presentation-design` or the corresponding API
request field.

### Catalog presentation preferences

Catalogs may include an optional `presentation_style_preferences` object with:

```json
{
  "preferred_visual_direction": "",
  "color_preferences": "",
  "typography_preferences": "",
  "layout_and_density_preferences": "",
  "accessibility_requirements": "",
  "styles_to_avoid": "",
  "image_generation_preferences": "",
  "additional_notes": ""
}
```

These fields guide selection among packaged styles. Accessibility, readability,
course fit, renderer feasibility, and each template's constraints take priority
over incompatible preferences. Preferences select a template; they do not
silently rewrite the selected template's design tokens.

## Packaged slide design system

`assets/slide_gen/` contains the complete presentation asset package:

- A selection index and style-preset guidance.
- A shared viewport base stylesheet.
- Offline runtime fonts and their licenses.
- A bundled MathJax runtime and license.
- Packaged design sources used by the presentation deliberation.

The bold template pack contains:

- 8 Bit Orbit
- Biennale Yellow
- Block Frame
- Blue Professional
- Bold Poster
- Broadside
- Capsule
- Cartesian
- Cobalt Grid
- Coral
- Creative Mode
- Daisy Days
- Editorial Forest
- Editorial Tri-Tone
- Emerald Editorial
- Grove
- Long Table
- Mat
- Monochrome
- Neo Grid Bold
- Peoples Platform
- Pin and Paper
- Pink Script
- Playful
- Raw Grid
- Retro Windows
- Retro Zine
- Sakura Chroma
- Scatterbrain
- Signal
- Soft Editorial
- Stencil Tablet
- Studio
- Vellum

Style inventory loading, candidate ordering, selection validation,
materialization, normalization, hashing, and persistence are implemented in
`src/html_slides_style.py`.

## Offline frontend slide generation

`src/html_slides.py` adds a complete deterministic frontend renderer. It:

1. Parses saved Beamer frames into a structured deck.
2. Correlates speaker notes with stable slide identifiers.
3. Chooses layouts based on content type and density.
4. Applies the frozen course presentation design.
5. Embeds local fonts and MathJax assets for offline use.
6. Produces responsive HTML with presenter controls and a notes panel.
7. Exports an HTML-derived PDF.
8. Exports a static image-based PPTX that preserves the HTML appearance.
9. Writes a manifest containing source, script, style, media, and pipeline
   fingerprints.

Press `N` in the HTML presentation to toggle the correlated speaker-notes
panel. Presenter UI is omitted from PDF and PPTX exports.

Each finalized chapter now contains:

```text
chapter_<number>/
├── slides.tex
├── slides.pdf
├── script.md
├── assessment.md
├── html/
│   ├── slides.html
│   └── assets/
├── slides-html.pdf
├── slides-html.pptx
├── frontend-slides-manifest.json
├── statistics_slide_images.json
└── statistics_slides_chapter_<number>.json
```

The HTML bundle is portable as long as `slides.html` remains beside its
`assets/` directory.

## Beamer parsing and preflight

`src/beamer_preflight.py` adds structural checks and repair support before
frontend conversion. The branch includes safeguards for:

- Deeply nested Beamer lists.
- Display-math density and sizing.
- Invalid or unsupported color expressions.
- Math constructs that previously caused LaTeX compilation failures.
- Unsafe or mismatched frame boundaries.
- Source-to-script speaker-note correlation.
- Layout overflow risks before browser export.

The slide-generation prompts were tightened so each outline item produces one
stable frame instead of asking an agent to create unpredictable multi-frame
transitions. This improves correspondence between Beamer frames, scripts,
frontend pages, and speaker notes.

## Chapter finalization, caching, and resume

Chapter compilation and frontend creation now happen immediately after a
chapter's source files are ready. This preserves completed work if a later
chapter fails.

The finalizer uses content hashes and manifests to determine whether artifacts
are current. It can rebuild missing or stale deterministic outputs without
repeating chapter model calls. Relevant inputs include:

- `slides.tex` hash.
- `script.md` hash.
- Course presentation-style hash.
- Generated-image request fingerprint.
- Code-image request fingerprint and Carbon version.
- Frontend pipeline/schema version.

`--resume` skips completed foundation documents and chapter source generation,
then recreates only missing or invalidated outputs. Mid-chapter checkpoints are
also preserved and cleaned after successful completion.

Atomic file writing and shared parsing/validation utilities live in
`src/slide_io.py`.

## Generated instructional images

`src/html_slides_img.py` implements optional AI-generated imagery for frontend
slides.

### Stored configuration

The experiment stores `course_image_generation.json` with values including:

- Enabled state.
- Stored fixed cap, default 3.
- Automatic AI-count state.
- Image model, currently `gpt-image-2` by default.
- Image size, currently `1536x864`.
- Quality, currently `medium`.
- Estimated per-image cost used for statistics.

Replacement is invocation-only and is not persisted as a permanent mode.

### Image workflow

1. The course presentation deliberation determines whether imagery is
   pedagogically and stylistically appropriate.
2. The chapter placement agent identifies strong eligible opportunities.
3. Automatic count mode allows the agent to keep every strong opportunity.
4. A prompt-writing pass creates text-free visual prompts.
5. The image API generates native 16:9 assets.
6. Images are attached to compatible layouts and embedded into the HTML bundle.
7. Provenance, fingerprints, cost estimates, warnings, and placements are
   recorded in manifests and statistics.

Image prompts prohibit text, labels, numbers, logos, watermarks, UI chrome, and
identifiable real people. Labels and legends are rendered as accessible HTML
instead of being baked into pixels.

Generated images affect only the HTML-derived artifacts. The Beamer source and
Beamer PDF remain unchanged.

### Cache and replacement behavior

- A matching request fingerprint reuses valid existing images.
- `--image-generation replace` requests a fresh set.
- Incomplete or failed replacement retains the prior valid set.
- A valid replacement selecting zero images removes the old placements.
- Image failures warn and degrade gracefully rather than failing the complete
  instructional workflow.

## Carbon code images

`src/html_slides_code.py` optionally renders code blocks as Carbon PNGs.

- Enable with `--code-images on`.
- Disable with `--code-images off`.
- The setting is stored in `course_code_images.json`.
- The pinned renderer is `carbon-now-cli@2.1.0`.
- Installation is attempted lazily only when code exists, code images are
  enabled, and `carbon-now` is missing.
- Node.js and npm must already be installed.
- Installation or rendering failures retain the styled HTML `<pre>` fallback.
- Successful images are cached by snippet, language, theme, settings, pipeline,
  and Carbon version.

The branch does not install Node.js or npm. Enabling code images authorizes a
possible global npm installation of the pinned Carbon CLI.

## API integration

The REST API retains JSON fields rather than adopting CLI string choices. This
preserves API compatibility while using the same underlying image and code
configuration objects.

Course generation requests may include:

```json
{
  "reselect_presentation_design": false,
  "enable_image_generation": true,
  "replace_images": false,
  "max_images_per_chapter": null,
  "ai_decides_image_count": true,
  "code_images": true
}
```

`max_images_per_chapter` and `ai_decides_image_count` remain mutually exclusive
at the API boundary. The API also supports the existing `generate_pptx` field
for legacy LaTeX-to-PPTX conversion after course generation.

An earlier branch commit changed the browser frontend, but those changes were
subsequently reverted. In the final branch state, the files under `frontend/`
match `main`; the new workflow is exposed through `run.py` and the API model.

## Packaging and dependencies

The branch updates packaging so the new `assets.slide_gen` package, design
assets, offline fonts, licenses, MathJax runtime, and frontend runtime files are
included in distributions.

Dependency changes support:

- Browser-based HTML rendering and export.
- PowerPoint generation.
- LaTeX parsing and safer conversion.
- Existing PDF processing paths.

Repository metadata also adds the attributed frontend-design skill used during
development, worktree inclusion metadata, and ignore/package rules for the new
asset layout.

## Test coverage

The branch adds or expands tests for:

- Foundation presentation-design selection and persistence.
- Style inventory distribution and deterministic ordering.
- Beamer parsing and preflight validation.
- Offline runtime packaging and MathJax rendering.
- Frontend HTML, PDF, and PPTX generation.
- Speaker-note correlation.
- Generated-image configuration, placement, caching, replacement, and cost
  statistics.
- Carbon installation, caching, fallback, versioning, and timeouts.
- Atomic slide I/O helpers.
- `run.py` media flags and persistence behavior.
- API validation for image settings.

At the time this document was created, the complete repository test suite
reported:

```text
183 passed, 2 skipped
```

The skipped tests are environment-dependent integration checks.

## Primary implementation files

| Area | Files |
|---|---|
| Main CLI and API | `run.py`, `api_server.py` |
| Workflow integration | `src/ADDIE.py`, `src/agents.py`, `src/slides.py` |
| Presentation design | `src/html_slides_style.py`, `assets/slide_gen/skill/` |
| Frontend rendering | `src/html_slides.py` |
| Generated images | `src/html_slides_img.py` |
| Carbon code images | `src/html_slides_code.py` |
| Beamer safety | `src/beamer_preflight.py` |
| Compilation | `src/compile.py` |
| Shared safe I/O | `src/slide_io.py` |
| Catalog examples | `catalog/default_catalog.json`, `catalog/mwe_catalog.json` |
| Packaging | `pyproject.toml`, `MANIFEST.in`, `requirements.txt` |
| Tests | `tests/` |

## Operational notes

- Set `OPENAI_API_KEY` before generation or allow the CLI to prompt for it.
- Install the Python project dependencies before running the workflow.
- Install the browser runtime required by Playwright for HTML-derived exports.
- Keep LaTeX installed for Beamer PDF compilation.
- Keep Node.js and npm available only if Carbon code images are desired.
- Use a distinct `--exp` value for unrelated courses or materially different
  foundation settings.
- Prefer `--resume` when changing media settings on an existing experiment so
  completed model-generated source work is reused.
- Use `--reselect-presentation-design` sparingly because it intentionally
  changes the course-wide visual authority and invalidates dependent frontend
  artifacts.
