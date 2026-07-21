from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from src.agents import Agent, Deliberation

from .assets import load_assets
from .errors import FrontendSlidesError
from .models import CourseSlideStyle, PresentationMethod, SelectedStyle
from .style import (
    FONT_FAMILIES,
    PRESENTATION_DESIGN_FILENAME,
    STYLE_FILENAME,
    STYLE_SOURCE_FILENAME,
    STYLE_STATS_FILENAME,
    build_style_inventory,
    canonicalize_materialization_payload,
    canonicalize_selection_payload,
    course_style_from_dict,
    selected_asset_text,
    sha256_file,
    sha256_text,
    validate_materialization,
    validate_selection,
    write_course_style,
)

PRESENTATION_DESIGN_NAME = "Presentation Design"
EQUATION_GUIDANCE = (
    "Render equations directly on the slide canvas with transparent backgrounds, "
    "no borders, no shadows, and compact spacing; do not place equations in decorative cards."
)


def ensure_course_slide_style(
    addie: Any,
    output_dir: Path | str,
    foundation_results: list[Any],
    chapters: list[dict[str, str]],
    *,
    reselect: bool = False,
) -> CourseSlideStyle:
    output_path = Path(output_dir)
    style_path = output_path / STYLE_FILENAME
    if style_path.is_file() and not reselect:
        try:
            style = load_course_slide_style(output_path)
        except FrontendSlidesError as exc:
            raise FrontendSlidesError(
                "The persisted presentation-design authority is invalid and will not "
                "be silently replaced. Repair the frozen style files or explicitly run "
                "the foundation command with --reselect-presentation-design. "
                f"Details: {exc}"
            ) from exc
        upgraded_style = _with_required_guidance(style)
        if upgraded_style != style:
            write_course_style(style_path, upgraded_style)
        style = upgraded_style
        write_presentation_design_result(output_path, style)
        print(f"[resume] Loaded course slide style: {style.selected_style.name}")
        return style

    assets = load_assets()
    inventory, inventory_hash = build_style_inventory(assets)
    inventory_payload = [asdict(entry) for entry in inventory]
    selection_constraint = _selection_constraint(inventory)
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
            'Return strict JSON. selected_style.source must be exactly "preset" or '
            '"bold_template"; a vertical bar is never part of the value. Copy the selected '
            "source/key pair verbatim from the supplied inventory, preserving hyphens."
        ),
        output_constraint=selection_constraint,
    )

    deliberation = Deliberation(
        id="presentation_design",
        name=PRESENTATION_DESIGN_NAME,
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
            "and engagement method. During the same standard deliberation turn, each reviewer "
            "must derive concrete visual requirements from the course audience and activities, "
            "compare at least three exact inventory candidates, and explicitly consider each "
            "candidate's Best for and Avoid for guidance. Explain tradeoffs using course-specific "
            "details; generic claims such as merely being professional, clear, or engaging are "
            "not sufficient. Preserve the normal sequential discussion: respond to earlier "
            "reviewers while adding your own comparison evidence.\n\n"
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
    selection_evidence: dict[str, Any] | None = None
    selection_error = ""
    selection_normalizations: list[str] = []
    for attempt in range(3):
        try:
            payload = _parse_json_object(summary)
            payload, normalization_notes = canonicalize_selection_payload(
                payload, inventory
            )
            for note in normalization_notes:
                if note not in selection_normalizations:
                    selection_normalizations.append(note)
                    print(f"[style normalization] {note}")
            (
                selected_style,
                presentation_method,
                reason,
                selection_evidence,
            ) = validate_selection(payload, inventory)
            break
        except FrontendSlidesError as exc:
            selection_error = str(exc)
            if attempt == 2:
                raise FrontendSlidesError(
                    f"Course style selection remained invalid after retries: {exc}"
                ) from exc
            summary, elapsed, tokens = _call_agent(
                summarizer,
                _selection_repair_prompt(
                    deliberation=deliberation,
                    rejected_response=summary,
                    error=exc,
                    inventory=inventory,
                ),
            )
            total_time += elapsed
            total_tokens += tokens
    assert (
        selected_style is not None
        and presentation_method is not None
        and selection_evidence is not None
    )

    selected_source = selected_asset_text(selected_style, assets)
    selected_hash = sha256_text(selected_source)
    materializer = Agent(
        name="Teaching Assistant",
        role="Selected slide-style implementation specialist",
        llm=addie.llm,
        system_prompt=(
            "Translate one selected slide design into safe rendering tokens and compact guidance "
            "for future chapter generation. Use only the selected asset provided. Do not emit CSS. "
            "Require equations to render directly on the slide canvas without decorative "
            "background cards, borders, shadows, or oversized padding."
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
    materialization_normalizations: list[str] = []
    for attempt in range(3):
        try:
            materialization_payload = _parse_json_object(materialized)
            (
                materialization_payload,
                normalization_notes,
            ) = canonicalize_materialization_payload(materialization_payload)
            for note in normalization_notes:
                if note not in materialization_normalizations:
                    materialization_normalizations.append(note)
                    print(f"[style normalization] {note}")
            style = validate_materialization(
                materialization_payload,
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
                _materialization_repair_prompt(
                    materialization_prompt=materialization_prompt,
                    rejected_response=materialized,
                    error=exc,
                ),
            )
            total_time += retry_time
            total_tokens += retry_tokens
    assert style is not None
    style = _with_required_guidance(style)

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
                "selection_evidence": selection_evidence,
                "selection_normalizations": selection_normalizations,
                "materialization_normalizations": materialization_normalizations,
                "last_selection_error": selection_error or None,
                "last_materialization_error": materialization_error or None,
            },
            indent=2,
        )
        + "\n",
    )
    write_presentation_design_result(
        output_path,
        style,
        reason=reason,
        selection_evidence=selection_evidence,
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
    actual_source_hash = sha256_file(source_path)
    if actual_source_hash != style.selected_asset_sha256:
        raise FrontendSlidesError(
            f"{STYLE_SOURCE_FILENAME} does not match the persisted selected asset hash."
        )
    return style


def write_presentation_design_result(
    output_dir: Path | str,
    style: CourseSlideStyle,
    *,
    reason: str | None = None,
    selection_evidence: dict[str, Any] | None = None,
) -> Path:
    """Persist the human-readable seventh foundation result from validated state."""
    output_path = Path(output_dir)
    resolved_reason = reason or _saved_selection_reason(output_path)
    resolved_evidence = (
        selection_evidence
        if selection_evidence is not None
        else _saved_selection_evidence(output_path)
    )
    result_path = output_path / PRESENTATION_DESIGN_FILENAME
    _atomic_write(
        result_path,
        presentation_design_markdown(
            style,
            reason=resolved_reason,
            selection_evidence=resolved_evidence,
        ),
    )
    return result_path


def presentation_design_markdown(
    style: CourseSlideStyle,
    *,
    reason: str | None = None,
    selection_evidence: dict[str, Any] | None = None,
) -> str:
    """Build a deterministic summary that cannot diverge from renderer state."""
    selected = style.selected_style
    method = style.presentation_method
    theme = style.render_theme
    rationale = (reason or "").strip() or (
        "This is the validated course-wide presentation decision persisted for "
        "all chapters."
    )
    palette = "\n".join(
        f"- `{key}`: `{value}`" for key, value in sorted(theme.colors.items())
    )
    fonts = (
        f"- Display: {FONT_FAMILIES[theme.display_font][0]}\n"
        f"- Body: {FONT_FAMILIES[theme.body_font][0]}\n"
        f"- Monospace: {FONT_FAMILIES[theme.mono_font][0]}"
    )
    layouts = ", ".join(method.layout_rotation)
    evidence_markdown = _selection_evidence_markdown(selection_evidence)
    return (
        f"{PRESENTATION_DESIGN_NAME}\n"
        f"{'=' * len(PRESENTATION_DESIGN_NAME)}\n\n"
        "## Final Style\n\n"
        f"- Name: {selected.name}\n"
        f"- Source: `{selected.source}`\n"
        f"- Key: `{selected.key}`\n\n"
        "## Selection Rationale\n\n"
        f"{rationale}\n\n"
        f"{evidence_markdown}"
        "## Presentation Method\n\n"
        f"- Narrative: {method.narrative}\n"
        f"- Pacing: {method.pacing}\n"
        f"- Density: {method.density}\n"
        f"- Emphasis: {method.emphasis}\n"
        f"- Layout rotation: {layouts}\n"
        f"- Engagement: {method.engagement}\n\n"
        "## Palette\n\n"
        f"{palette}\n\n"
        "## Typography\n\n"
        f"{fonts}\n\n"
        "## Implementation Guidance\n\n"
        f"{style.ta_guidance.strip()}\n\n"
        "## Course-Wide Requirements\n\n"
        "- Use this one selected style for every chapter; chapter generation must "
        "not select or substitute another theme.\n"
        f"- {EQUATION_GUIDANCE}\n"
    )


def _with_required_guidance(style: CourseSlideStyle) -> CourseSlideStyle:
    if EQUATION_GUIDANCE in style.ta_guidance:
        return style
    separator = "\n\n" if style.ta_guidance.strip() else ""
    available = 4000 - len(separator) - len(EQUATION_GUIDANCE)
    existing = style.ta_guidance.strip()[:available].rstrip()
    return replace(
        style,
        ta_guidance=f"{existing}{separator}{EQUATION_GUIDANCE}",
    )


def _saved_selection_reason(output_dir: Path) -> str | None:
    stats_path = output_dir / STYLE_STATS_FILENAME
    if not stats_path.is_file():
        return None
    try:
        payload = json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    reason = payload.get("reason") if isinstance(payload, dict) else None
    return reason.strip() if isinstance(reason, str) and reason.strip() else None


def _saved_selection_evidence(output_dir: Path) -> dict[str, Any] | None:
    stats_path = output_dir / STYLE_STATS_FILENAME
    if not stats_path.is_file():
        return None
    try:
        payload = json.loads(stats_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    evidence = payload.get("selection_evidence") if isinstance(payload, dict) else None
    return evidence if isinstance(evidence, dict) else None


def _selection_evidence_markdown(evidence: dict[str, Any] | None) -> str:
    if not isinstance(evidence, dict):
        return ""
    requirements = evidence.get("course_requirements")
    alternatives = evidence.get("alternatives")
    avoid_for_assessment = evidence.get("avoid_for_assessment")
    if (
        not isinstance(requirements, list)
        or not isinstance(alternatives, list)
        or not isinstance(avoid_for_assessment, str)
    ):
        return ""
    requirement_lines = "\n".join(f"- {item}" for item in requirements)
    alternative_lines = "\n".join(
        "- "
        f"{item.get('name', item.get('key', 'Unknown'))} "
        f"(`{item.get('source', '')}:{item.get('key', '')}`): "
        f"{item.get('reason_rejected', '')}"
        for item in alternatives
        if isinstance(item, dict)
    )
    return (
        "## Course Visual Requirements\n\n"
        f"{requirement_lines}\n\n"
        "## Alternatives Considered\n\n"
        f"{alternative_lines}\n\n"
        "## Selected-Style Conflict Check\n\n"
        f"{avoid_for_assessment.strip()}\n\n"
    )


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


def _selection_constraint(inventory: list[Any]) -> str:
    allowed_pairs = [
        {"source": entry.source, "key": entry.key}
        for entry in inventory
    ]
    return f"""
Return one JSON object only, with this shape:
{{
  "selected_style": {{
    "source": "<exactly preset or bold_template>",
    "key": "<exact key copied from the inventory>"
  }},
  "presentation_method": {{
    "narrative": "<course-specific narrative of at least 30 characters>",
    "pacing": "<course-specific pacing guidance of at least 20 characters>",
    "density": "medium",
    "emphasis": "<course-specific visual emphasis of at least 20 characters>",
    "layout_rotation": ["hero", "columns"],
    "engagement": "<course-specific engagement method of at least 20 characters>"
  }},
  "selection_evidence": {{
    "course_requirements": [
      "<course-specific visual requirement one, at least 20 characters>",
      "<course-specific visual requirement two, at least 20 characters>",
      "<course-specific visual requirement three, at least 20 characters>"
    ],
    "alternatives": [
      {{
        "source": "<exactly preset or bold_template>",
        "key": "<exact rejected key copied from the inventory>",
        "reason_rejected": "<course-specific tradeoff of at least 40 characters>"
      }},
      {{
        "source": "<exactly preset or bold_template>",
        "key": "<another exact rejected key copied from the inventory>",
        "reason_rejected": "<course-specific tradeoff of at least 40 characters>"
      }}
    ],
    "avoid_for_assessment": "<at least 80 characters explaining whether the selected style's Avoid for guidance conflicts with this course>"
  }},
  "reason": "<at least 100 characters tying the exact selected style to the course audience, activities, and visual requirements>"
}}
Every angle-bracketed value is an instruction placeholder and must be replaced.
Rules:
- source must be exactly "preset" or "bold_template". Never return
  "preset|bold_template".
- source and key must be copied as one exact pair from ALLOWED_STYLE_PAIRS below.
  Preserve every hyphen; do not replace hyphens with underscores or spaces.
- density must be exactly "low", "medium", or "high".
- layout_rotation must contain at least two distinct values selected from:
  "hero", "split", "top", "columns", "math".
- alternatives must contain 2 to 4 distinct exact inventory pairs, must not contain
  the selected style, and must come from candidates actually compared in the discussion.
  Each rejection must identify a course-specific tradeoff.
- avoid_for_assessment must accurately state the selected inventory entry's Avoid for
  warning before explaining why it does or does not conflict with this presentation context.
- do not copy placeholder prose from this contract. Generic claims such as "professional
  and clear" are not adequate without details from the supplied course context.

ALLOWED_STYLE_PAIRS:
{json.dumps(allowed_pairs, ensure_ascii=False)}
"""


def _selection_repair_prompt(
    *,
    deliberation: Deliberation,
    rejected_response: str,
    error: FrontendSlidesError,
    inventory: list[Any],
) -> str:
    exact_pairs = [
        f"{entry.source}:{entry.key}"
        for entry in inventory
    ]
    return (
        f"{deliberation.format_discussion_history()}\n\n"
        "The previous response failed strict validation.\n"
        f"Validation error: {error}\n\n"
        "Previous rejected response:\n"
        f"{rejected_response[:12000]}\n\n"
        "Correct only the invalid fields while preserving the intended style and "
        "presentation method. The source must be exactly `preset` or "
        "`bold_template`—never the literal text `preset|bold_template`. Copy the key "
        "verbatim, including hyphens, from one of these exact pairs:\n"
        f"{json.dumps(exact_pairs, ensure_ascii=False)}\n\n"
        "Use only supported layouts: hero, split, top, columns, or math; `full-page` "
        "means `hero` and is not a valid output value. Replace every angle-bracketed "
        "placeholder with course-specific evidence and return the complete corrected "
        "JSON object only."
    )


def _materialization_repair_prompt(
    *,
    materialization_prompt: str,
    rejected_response: str,
    error: FrontendSlidesError,
) -> str:
    return (
        f"{materialization_prompt}\n\n"
        "The previous response failed strict validation.\n"
        f"Validation error: {error}\n\n"
        "Previous rejected response:\n"
        f"{rejected_response[:12000]}\n\n"
        "Return corrected JSON only. Every color must be an opaque six-digit hex "
        "value such as #1e2bfa; do not return rgb(), rgba(), CSS variables, or other "
        "CSS. Use only one exact packaged font identifier and one exact enum value "
        "from the output contract for each field."
    )


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
    "display_font": "source-serif-4",
    "body_font": "dm-sans",
    "mono_font": "ibm-plex-mono",
    "title_size": 104,
    "heading_size": 60,
    "panel_style": "filled",
    "border_style": "thin",
    "shadow_style": "soft",
    "grid_opacity": 0.2
  }}
}}
title_size must be 72-128, heading_size 44-78, grid_opacity 0-0.8.
Choose exactly one value for each enum; never return pipe-separated alternatives.
Allowed display_font values: archivo, source-serif-4, space-grotesk.
Allowed body_font values: archivo, dm-sans, source-serif-4, space-grotesk.
Allowed mono_font value: ibm-plex-mono.
Allowed panel_style values: open, filled, outlined.
Allowed border_style values: none, thin, thick, dashed.
Allowed shadow_style values: none, soft, hard.
All packaged font identifiers: {", ".join(sorted(FONT_FAMILIES))}.
"""
