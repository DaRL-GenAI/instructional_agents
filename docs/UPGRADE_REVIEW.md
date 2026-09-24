# `upgrade` branch — review of open PRs and what was merged

Date: 2026-09-23. Base: `main` @ `8b7d9ab`. Reviewed: PR #12, #13, #14, #15 and the
`origin/feature/slide-local-refine` branch. Decisions below can be reversed; every kept
piece is a separate commit on `upgrade`.

## Summary table

| Source | Kept | Kept with fixes | Dropped |
|---|---|---|---|
| `feature/slide-local-refine` (592ab5a) | Localized "refine" optimize mode (`src/slide_refiner.py`, `src/optimize.py`, API `mode` field, frontend select) | — | — |
| PR #15 *Better slides generation* (rayankzi) | `src/agents.py` error-path fix + opt-in `Deliberation` flags; `src/beamer_preflight.py`, `src/slide_io.py`; `src/compile.py` preflight-repair retry; prompt guidelines against invented colors / deep nesting / nested display math / multiple listings; preflight normalization before `slides.tex` is written | — | HTML-slides workflow (`src/html_slides*.py`, 3.8 MB `assets/slide_gen/**` incl. a 2.1 MB MathJax blob, 46 style templates, 7th "presentation design" deliberation, AI image generation, Carbon code images), `.DS_Store`/`.worktreeinclude`, catalog re-indent |
| PR #14 *Add textbook analysis* (maimaimai084) | `src/textbook_reference.py` (LLM-free textbook → catalog seed), `POST /api/textbook/catalog`, frontend file input | Comments translated to English; `max_slide_count` configurable (default 50 instead of the hard-coded 10); zh UI strings added | Nothing (the refine-mode files in the PR were inherited from 592ab5a, taken once) |
| PR #12 *Refiner pipeline* (Aarsh-collab) | `src/refinement.py` (Script/Assessment/Syllabus/Objectives refiners), `src/refinement_runner.py`, `src/evaluate.py` `{score, thought}` records + `overall_summary` fix, `run.py` `--evaluate/--refine*` flags, API fields, frontend panel | Duplicate `SlideRefiner` replaced by an import; pdflatex re-compile scan made opt-in; post-processing wrapped in try/except so a finished course is never marked failed | `tests/test_refiner.py` (live-API script calling a non-existent method), `fastapi[standard]`, `.env.example` / `.gitignore` noise |
| PR #13 *textbook grounding* (shrey-Bish) | see "PR #13" below | see below | see below |
| EduCAST video generation | `src/video.py`, `src/video_captions.py`, `src/video_media.py` + CLI/API/UI hooks | — | Remotion / Manim / Playwright rendering, scene planner, vision reviewer |

## Why the PR #15 HTML workflow was not merged

The reviewer reproduced three regressions for users who never enable the new flags:

1. `src/ADDIE.py` and `src/slides.py` import `src.html_slides` at module top, which imports
   `pylatexenc`, `PyPDF2` and `python-pptx` — the pipeline no longer imports with the old requirements.
2. `finalize_chapter()` runs for every chapter and raises `FrontendSlidesError` when Chromium is not
   installed (`validate_with_playwright` → "Playwright browser unavailable"); the Dockerfile was not
   updated, so the shipped image fails after chapter 1's LLM spend.
3. `pdflatex` becomes mandatory (`compile_one` raises) where `main` only warned.

It also adds a 7th deliberation that always runs (with the 46-entry style inventory in the prompt),
changes the deck contract to exactly one frame per outline item, bumps the checkpoint version so
in-flight `--resume` runs restart, and copies 2.3 MB of MathJax/fonts into every chapter.
The feature is well tested (177 tests) and can be revisited behind an opt-in flag with lazy
imports; `docs/BETTER_SLIDES_GENERATION.md` on `pr/15` documents it.

## PR #13 (textbook grounding)

The PR mixes an opt-in grounding stack with unrelated changes that alter output for everyone.
Kept (ported by hand onto `upgrade`): the grounding core — `src/textbook/` ingestion
(pymupdf4llm / Markdown), `src/grounding/` knowledge base, hybrid BM25 + embedding retriever,
chapter→section contract, TOC context for the foundation deliberations, per-slide evidence
blocks in `SlidesDeliberation`, `--use-textbook PATH`, `/api/textbooks/*`, frontend picker;
plus the separable PPTX-export improvements in `src/latex_to_pptx.py` / `src/build_pptx.js`
(with the `\$` and `a * b * c` regressions fixed) and the `evaluate.py --rigorous` option.

Dropped: the fastembed/onnxruntime cross-encoder reranker (24 MB wheel + 90 MB model download
at `ADDIE()` construction; the author's later commits removed its consumer), the VLM "hybrid"
PDF path (`ingest_pdf_hybrid.py`, `spatial_router.py`, `vlm_adapter.py`: 7.5-minute retry hangs
without a key, deprecated SDK call, figure overwrite bug), the gpt-4o "content verifier",
the "syllabus admin scaffolding" LLM call, the unconditional `_clean_latex_artifacts`
post-processor (it rewrites `&` and `%` inside `align*`, `cases`, `lstlisting`, `verbatim`
and deletes every `\ref`), the rewritten outline / frame prompts, dead code
(`toc.py`, `*_via_markdown`, citation remnants), and unconditional heavy dependencies in
`requirements.txt` (grounding deps are an optional extra: `pip install .[grounding]`).

Fixes applied while porting: model names come from `--model` / config instead of hard-coded
`gpt-4o`; caches live under `exp/<name>/.grounding_cache/` instead of the repo root and are
keyed by content hash; `pymupdf4llm` is declared and its absence is warned about; directory
ingestion no longer overwrites figures of earlier files; vision calls during ingestion are
opt-in; the upload endpoint requires the API-key header and uploads are gitignored.

## Test status on `upgrade`

```
OPENAI_API_KEY=dummy PYTHONMALLOC=malloc python -m pytest -q tests
523 passed, 28 skipped   (main had 39 tests)
```

Skips are LaTeX-dependent tests (no `pdflatex`) and grounding tests that need textbooks which are
not in the repo. No test makes network calls. Note: on the conda Python 3.13.11 build used for
this work, pytest's assertion rewriting occasionally segfaults inside `ast` during collection with
the default pymalloc allocator; `PYTHONMALLOC=malloc` avoids it and is unrelated to the code.

Real-API smoke checks performed while building the branch: `python run.py --render-video` on a
4-slide fixture (OpenAI TTS, ffmpeg, captions), and the Studio page end to end in headless
Chromium (8 model calls, 4 TTS calls, a 182 s WebM lecture video, full audit log).

## Branch summary

| Area | Commits on `upgrade` |
|---|---|
| Refine mode (feature/slide-local-refine) | 592ab5a |
| PR #15 safe parts + slides.py prompt/preflight port | 99213ed, a9f6767 |
| PR #14 (author commits + follow-ups) | 55ae950, 1ce9790, 277774c, 0c324a3 |
| PR #12 refinement pipeline (with fixes) | 32d3e0d |
| EduCAST video rendering + CLI/API/UI hooks | 3aeaffa, 30e2c48, f0031da |
| PR #13 PPTX/evaluate port | 451468b (merge d97ef32) |
| PR #13 grounding core | 7 commits merged after 798e3fa |
| evaluate.py shim, README zh | 798e3fa |
