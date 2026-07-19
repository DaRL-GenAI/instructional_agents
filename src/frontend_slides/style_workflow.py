from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.agents import Agent, Deliberation

from .assets import load_assets
from .errors import FrontendSlidesError
from .models import CourseSlideStyle, PresentationMethod, SelectedStyle
from .style import (
    FONT_FAMILIES,
    STYLE_FILENAME,
    STYLE_SOURCE_FILENAME,
    STYLE_STATS_FILENAME,
    build_style_inventory,
    course_style_from_dict,
    selected_asset_text,
    sha256_file,
    sha256_text,
    validate_materialization,
    validate_selection,
    write_course_style,
)


def ensure_course_slide_style(
    addie: Any,
    output_dir: Path | str,
    foundation_results: list[Any],
    chapters: list[dict[str, str]],
) -> CourseSlideStyle:
    output_path = Path(output_dir)
    style_path = output_path / STYLE_FILENAME
    if style_path.is_file():
        try:
            style = load_course_slide_style(output_path)
        except FrontendSlidesError as exc:
            print(
                "[resume] Existing course slide style is stale or invalid; "
                f"rerunning only the style phase: {exc}"
            )
        else:
            print(f"[resume] Loaded course slide style: {style.selected_style.name}")
            return style

    assets = load_assets()
    inventory, inventory_hash = build_style_inventory(assets)
    inventory_payload = [asdict(entry) for entry in inventory]
    course_context = {
        "course_name": getattr(addie, "course_name", ""),
        "foundation_documents": [
            str(result)[:12000] for result in foundation_results[1:]
        ],
        "chapters": chapters,
    }

    teaching_faculty = Agent(
        name="Teaching Faculty",
        role="Professor evaluating the course narrative and teaching approach",
        llm=addie.llm,
        system_prompt=(
            "Choose visual and presentation approaches that improve explanation, examples, "
            "student attention, and conceptual continuity across an entire course."
        ),
    )
    instructional_designer = Agent(
        name="Instructional Designer",
        role="Expert evaluating structure, accessibility, density, and layout",
        llm=addie.llm,
        system_prompt=(
            "Evaluate course-wide slide styles for learning alignment, accessible contrast, "
            "readable density, layout variety, and consistent information hierarchy."
        ),
    )
    course_coordinator = Agent(
        name="Course Coordinator",
        role="Course consistency and delivery constraints reviewer",
        llm=addie.llm,
        system_prompt=(
            "Evaluate whether a style can remain coherent across every chapter and respect the "
            "course audience, institutional context, and delivery constraints."
        ),
    )
    teaching_assistant = Agent(
        name="Teaching Assistant",
        role="Beamer and HTML slide production feasibility reviewer",
        llm=addie.llm,
        system_prompt=(
            "Evaluate which style and presentation method can be applied faithfully to generated "
            "Beamer content and deterministic 1920x1080 HTML rendering."
        ),
    )
    summarizer = Agent(
        name="Summarizer",
        role="Course slide-style decision maker",
        llm=addie.llm,
        system_prompt=(
            "Synthesize the discussion into one course-wide style choice and presentation method. "
            "Return strict JSON and select only a source/key pair present in the supplied inventory."
        ),
        output_constraint=_SELECTION_CONSTRAINT,
    )

    deliberation = Deliberation(
        id="course_slide_style",
        name="Course Slide Style & Presentation Method",
        agents=[
            teaching_faculty,
            instructional_designer,
            course_coordinator,
            teaching_assistant,
        ],
        summary_agent=summarizer,
        max_rounds=1,
        instruction_prompt=(
            "Discuss and choose exactly one visual style for all chapter presentations. "
            "Also decide the course-wide narrative, pacing, density, emphasis, layout rotation, "
            "and engagement method.\n\n"
            f"Course context:\n{json.dumps(course_context, ensure_ascii=False)}\n\n"
            "Complete style inventory (12 presets and 34 bold templates):\n"
            f"{json.dumps(inventory_payload, ensure_ascii=False)}"
        ),
        output_format="json",
    )
    summary, total_time, total_tokens = deliberation.run()
    selected_style: SelectedStyle | None = None
    presentation_method: PresentationMethod | None = None
    reason = ""
    selection_error = ""
    for attempt in range(3):
        try:
            payload = _parse_json_object(summary)
            selected_style, presentation_method, reason = validate_selection(
                payload, inventory
            )
            break
        except FrontendSlidesError as exc:
            selection_error = str(exc)
            if attempt == 2:
                raise FrontendSlidesError(
                    f"Course style selection remained invalid after retries: {exc}"
                ) from exc
            summary, elapsed, tokens = _call_agent(
                summarizer,
                (
                    f"{deliberation.format_discussion_history()}\n\n"
                    f"Your previous JSON was rejected: {exc}\n"
                    "Return a corrected JSON object only."
                ),
            )
            total_time += elapsed
            total_tokens += tokens
    assert selected_style is not None and presentation_method is not None

    selected_source = selected_asset_text(selected_style, assets)
    selected_hash = sha256_text(selected_source)
    materializer = Agent(
        name="Teaching Assistant",
        role="Selected slide-style implementation specialist",
        llm=addie.llm,
        system_prompt=(
            "Translate one selected slide design into safe rendering tokens and compact guidance "
            "for future chapter generation. Use only the selected asset provided. Do not emit CSS."
        ),
        output_constraint=_MATERIALIZATION_CONSTRAINT,
    )
    materialization_prompt = (
        "Selected style:\n"
        f"{json.dumps(asdict(selected_style), indent=2)}\n\n"
        "Selected presentation method:\n"
        f"{json.dumps(asdict(presentation_method), indent=2)}\n\n"
        "Selected style asset (this is the only style asset available for this pass):\n"
        f"{selected_source}"
    )
    materialized, elapsed, tokens = _call_agent(materializer, materialization_prompt)
    total_time += elapsed
    total_tokens += tokens
    style: CourseSlideStyle | None = None
    materialization_error = ""
    for attempt in range(3):
        try:
            style = validate_materialization(
                _parse_json_object(materialized),
                selected_style=selected_style,
                presentation_method=presentation_method,
                inventory_sha256=inventory_hash,
                selected_asset_sha256=selected_hash,
            )
            break
        except FrontendSlidesError as exc:
            materialization_error = str(exc)
            if attempt == 2:
                raise FrontendSlidesError(
                    f"Selected style materialization remained invalid after retries: {exc}"
                ) from exc
            materialized, retry_time, retry_tokens = _call_agent(
                materializer,
                (
                    f"{materialization_prompt}\n\n"
                    f"Your previous JSON was rejected: {exc}\n"
                    "Return corrected JSON only, following the exact schema and allowed values."
                ),
            )
            total_time += retry_time
            total_tokens += retry_tokens
    assert style is not None

    output_path.mkdir(parents=True, exist_ok=True)
    write_course_style(style_path, style)
    _atomic_write(output_path / STYLE_SOURCE_FILENAME, selected_source)
    _atomic_write(
        output_path / STYLE_STATS_FILENAME,
        json.dumps(
            {
                "elapsed_time": total_time,
                "token_usage": total_tokens,
                "participating_agents": [
                    "Teaching Faculty",
                    "Instructional Designer",
                    "Course Coordinator",
                    "Teaching Assistant",
                    "Summarizer",
                ],
                "selected_style": asdict(style.selected_style),
                "reason": reason,
                "last_selection_error": selection_error or None,
                "last_materialization_error": materialization_error or None,
            },
            indent=2,
        )
        + "\n",
    )
    print(f"Course slide style selected: {style.selected_style.name}")
    return style


def load_course_slide_style(output_dir: Path | str) -> CourseSlideStyle:
    output_path = Path(output_dir)
    style_path = output_path / STYLE_FILENAME
    source_path = output_path / STYLE_SOURCE_FILENAME
    if not style_path.is_file() or not source_path.is_file():
        raise FrontendSlidesError(
            "Course slide style is missing. Rerun the foundation command before generating chapters."
        )
    try:
        data = json.loads(style_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FrontendSlidesError(f"Cannot read {style_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FrontendSlidesError(f"{style_path} must contain a JSON object.")
    style = course_style_from_dict(data)
    inventory, current_inventory_hash = build_style_inventory()
    if style.inventory_sha256 != current_inventory_hash:
        raise FrontendSlidesError(
            "The persisted course slide style uses a different asset inventory. "
            "Rerun the foundation command to select and materialize a current style."
        )
    selected_entry = next(
        (
            entry
            for entry in inventory
            if entry.source == style.selected_style.source
            and entry.key == style.selected_style.key
        ),
        None,
    )
    if (
        selected_entry is None
        or selected_entry.name != style.selected_style.name
    ):
        raise FrontendSlidesError(
            "The persisted selected style is not present in the current asset inventory."
        )
    actual_source_hash = sha256_file(source_path)
    if actual_source_hash != style.selected_asset_sha256:
        raise FrontendSlidesError(
            f"{STYLE_SOURCE_FILENAME} does not match the persisted selected asset hash."
        )
    packaged_source_hash = sha256_text(
        selected_asset_text(style.selected_style)
    )
    if packaged_source_hash != style.selected_asset_sha256:
        raise FrontendSlidesError(
            "The selected style asset has changed since foundation generation. "
            "Rerun the foundation command before generating chapters."
        )
    return style


def _parse_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise FrontendSlidesError("Agent response was not text.")
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise FrontendSlidesError("Agent response did not contain a JSON object.")
    try:
        value = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        raise FrontendSlidesError(f"Agent response contained invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise FrontendSlidesError("Agent response must be a JSON object.")
    return value


def _call_agent(agent: Agent, prompt: str) -> tuple[str, float, int]:
    result = agent.generate_response(prompt, stream=True, save_to_history=False)
    if not isinstance(result, tuple) or len(result) != 3:
        raise FrontendSlidesError(f"{agent.name} failed to return response accounting.")
    response, elapsed, tokens = result
    if not isinstance(response, str) or response.startswith("Error:"):
        raise FrontendSlidesError(f"{agent.name} failed: {response}")
    return response, float(elapsed), int(tokens)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


_SELECTION_CONSTRAINT = """
Return only this JSON shape:
{
  "selected_style": {"source": "preset|bold_template", "key": "exact inventory key"},
  "presentation_method": {
    "narrative": "course-wide narrative approach",
    "pacing": "pacing guidance",
    "density": "low|medium|high",
    "emphasis": "what visual hierarchy should emphasize",
    "layout_rotation": ["hero", "split", "top", "columns", "math"],
    "engagement": "student engagement approach"
  },
  "reason": "why this exact style and method fit the whole course"
}
Use at least two supported layout names. Do not invent a style key.
"""


_MATERIALIZATION_CONSTRAINT = f"""
Return only this JSON shape:
{{
  "ta_guidance": "compact visual guidance under 4000 characters",
  "render_theme": {{
    "colors": {{
      "stage_bg": "#RRGGBB",
      "background": "#RRGGBB",
      "background_alt": "#RRGGBB",
      "text": "#RRGGBB",
      "muted": "#RRGGBB",
      "accent": "#RRGGBB",
      "accent2": "#RRGGBB",
      "surface": "#RRGGBB",
      "surface_alt": "#RRGGBB",
      "border": "#RRGGBB",
      "panel_fill": "#RRGGBB"
    }},
    "display_font": "archivo|source-serif-4|space-grotesk",
    "body_font": "archivo|dm-sans|source-serif-4|space-grotesk",
    "mono_font": "ibm-plex-mono",
    "title_size": 72,
    "heading_size": 44,
    "panel_style": "open|filled|outlined",
    "border_style": "none|thin|thick|dashed",
    "shadow_style": "none|soft|hard",
    "grid_opacity": 0.0
  }}
}}
title_size must be 72-128, heading_size 44-78, grid_opacity 0-0.8.
Allowed packaged fonts: {", ".join(sorted(FONT_FAMILIES))}.
"""
