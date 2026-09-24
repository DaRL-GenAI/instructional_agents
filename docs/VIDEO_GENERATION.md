# Lecture Video Generation

Turn a generated chapter (slides + script) into a narrated lecture video with captions.
The approach is ported from [EduCAST / EduHarness](https://github.com/DaRL-GenAI/EduCAST):
one still image per slide, narration from the OpenAI speech API, ffmpeg for muxing and
concatenation, and proportional caption cues. Remotion, Manim and a browser are **not** needed.

## Requirements

| Dependency | Why | Install |
|---|---|---|
| `ffmpeg` + `ffprobe` | encode segments, concat, captions | `apt-get install ffmpeg` / `brew install ffmpeg` (already in the Docker image) |
| `pillow` | fallback slide drawing when no `slides.pdf` exists | `pip install pillow` (in `requirements.txt`) |
| `pymupdf` *or* `pdftoppm` | rasterize `slides.pdf` | `pip install pymupdf` or `apt-get install poppler-utils` |
| `OPENAI_API_KEY` | text-to-speech (`gpt-4o-mini-tts` by default) | — |

## Usage

```bash
# Generate a course and render a video for every chapter at the end
python run.py "LLM-based Agents" --catalog default_catalog --video

# Render videos for an existing experiment directory (no course generation, only TTS calls)
python run.py --render-video ./exp/my_course/
python run.py --render-video ./exp/my_course/ --voice nova --tts-model gpt-4o-mini-tts --burn-subtitles
python run.py --render-video ./exp/my_course/ --video-chapters 1,3     # only chapter_1 and chapter_3
```

REST API (after a completed generation task):

```bash
curl -X POST http://localhost:8000/api/course/render-video/<task_id> \
     -H "X-OpenAI-API-Key: $OPENAI_API_KEY" \
     -H "Content-Type: application/json" -d '{"voice": "alloy", "burn_subtitles": false}'
```

The web UI has an **"Also render lecture videos"** checkbox in the generation form and a
**"Render videos"** button on finished tasks.

## Inputs and outputs

For each `exp/<name>/chapter_N/`:

| Input | Used for |
|---|---|
| `slides.pdf` | one PNG per page (preferred) |
| `slides.tex` | Pillow-drawn fallback slides (title + bullets) when the PDF is missing |
| `script.md` | narration; `## Section N:` blocks map onto slides, `*(k frames)*` markers split a section over k slides |
| `../processed_chapters.json` | chapter titles for the title slide |

Outputs in `chapter_N/video/`:

| File | Content |
|---|---|
| `lecture.mp4` | H.264/AAC, 1920×1080, soft `mov_text` captions (or burned in with `--burn-subtitles`) |
| `lecture.vtt`, `lecture.srt` | sidecar captions |
| `timeline.json` | every segment: slide page, narration text, audio SHA-1, duration, start/end, cue list — the audit record of the render |
| `narration/<sha1>.mp3` | cached narration clips (keyed by model, voice and text; re-runs only synthesize changed text) |
| `frames/page_NNN.png` | the slide images used |

`exp/<name>/videos.json` indexes all chapter summaries.

## Python API

```python
from src.video import render_course_videos, render_chapter_video, VideoOptions

render_course_videos("./exp/my_course", options=VideoOptions(voice="nova"), course_name="LLM-based Agents")
render_chapter_video("./exp/my_course/chapter_2", options=VideoOptions(burn_subtitles=True))
```

`LectureVideoBuilder(chapter_dir, options, tts=callable)` accepts any `tts(text, out_path)` callable,
so narration can come from another provider (or a silent stub in tests).

## How it maps script to slides

1. `parse_script_sections()` reads `script.md`; Markdown emphasis, code fences and bullets are stripped for speech.
2. If the deck has one more page than the total number of frames, page 1 is treated as the title page and gets a short generated welcome line listing the sections.
3. A section marked `*(k frames)*` is split over k consecutive pages by sentence count.
4. Extra pages (appendix) are shown silently for 3 s; a script with more sections than pages appends the remainder to the last slide's narration.

## Costs

TTS is billed per character. A 12-slide chapter with ~1,500 words of script is roughly 9,000 characters.
`timeline.json` records `narration_chars` and `tts_calls` per chapter.
