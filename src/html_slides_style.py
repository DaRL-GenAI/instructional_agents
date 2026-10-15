"""Course-wide HTML slide style selection, validation, assets, and persistence."""

from __future__ import annotations

import hashlib
import json
import random
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from src.agents import Agent, Deliberation
from src.slide_io import atomic_write as _atomic_write
from src.slide_io import parse_json_object


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class FrontendSlidesError(RuntimeError):
    """Raised when course style selection or chapter finalization fails."""


# ---------------------------------------------------------------------------
# Style data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectedStyle:
    source: str
    key: str
    name: str


@dataclass(frozen=True)
class PresentationMethod:
    narrative: str
    pacing: str
    density: str
    emphasis: str
    layout_rotation: list[str]
    engagement: str


@dataclass(frozen=True)
class RenderTheme:
    colors: dict[str, str]
    display_font: str
    body_font: str
    mono_font: str
    title_size: int
    heading_size: int
    panel_style: str
    border_style: str
    shadow_style: str
    grid_opacity: float


@dataclass(frozen=True)
class ImageGuidance:
    enabled: bool
    visual_types: list[str]
    prompt_style_notes: str
    avoid_notes: str
    max_images_per_chapter: int | None


@dataclass(frozen=True)
class CourseSlideStyle:
    schema_version: int
    asset_version: str
    selected_style: SelectedStyle
    presentation_method: PresentationMethod
    ta_guidance: str
    render_theme: RenderTheme
    inventory_sha256: str
    selected_asset_sha256: str
    image_guidance: ImageGuidance = field(
        default_factory=lambda: DEFAULT_IMAGE_GUIDANCE
    )


# ---------------------------------------------------------------------------
# Skill assets
# ---------------------------------------------------------------------------

class SkillAssetError(RuntimeError):
    """Raised when the copied frontend-slides assets are incomplete."""


@dataclass(frozen=True)
class TemplateRecord:
    slug: str
    name: str
    tagline: str
    mood: list[str]
    tone: list[str]
    formality: str
    density: str
    scheme: str
    best_for: str
    avoid_for: str
    design_md: str


@dataclass(frozen=True)
class FrontendSlidesAssets:
    root: Path
    style_presets_path: Path
    viewport_css_path: Path
    selection_index_path: Path
    selection_index: dict[str, Any]
    templates: dict[str, TemplateRecord]

    @property
    def style_presets(self) -> str:
        return self.style_presets_path.read_text(encoding="utf-8")

    @property
    def viewport_css(self) -> str:
        return self.viewport_css_path.read_text(encoding="utf-8")

    def read_asset(self, relative_path: str) -> str:
        path = self.root / relative_path
        if not path.exists():
            raise SkillAssetError(f"Missing skill asset: {relative_path}")
        return path.read_text(encoding="utf-8")

    def template(self, slug: str) -> TemplateRecord:
        try:
            return self.templates[slug]
        except KeyError as exc:
            raise SkillAssetError(f"Unknown bold template slug: {slug}") from exc

    def read_design_md(self, slug: str) -> str:
        return self.read_asset(self.template(slug).design_md)


def slide_gen_asset_root() -> Path:
    """Return the installed or source-checkout slide resource directory."""
    return Path(str(files("assets.slide_gen")))


def default_asset_root() -> Path:
    return slide_gen_asset_root() / "skill"


def load_assets(root: Path | str | None = None) -> FrontendSlidesAssets:
    asset_root = Path(root) if root else default_asset_root()
    required = {
        "STYLE_PRESETS.md": asset_root / "STYLE_PRESETS.md",
        "viewport-base.css": asset_root / "viewport-base.css",
        "selection-index.json": asset_root / "bold-template-pack" / "selection-index.json",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise SkillAssetError(f"Missing required frontend-slides assets: {', '.join(missing)}")

    selection_index = json.loads(required["selection-index.json"].read_text(encoding="utf-8"))
    records: dict[str, TemplateRecord] = {}
    for item in selection_index.get("templates", []):
        record = TemplateRecord(**item)
        design_path = asset_root / record.design_md
        if not design_path.exists():
            raise SkillAssetError(f"Missing design.md for template {record.slug}: {record.design_md}")
        records[record.slug] = record

    declared_count = int(selection_index.get("template_count", -1))
    if declared_count != 34 or len(records) != declared_count:
        raise SkillAssetError(
            f"Expected 34 bold templates, found declared={declared_count}, loaded={len(records)}"
        )

    return FrontendSlidesAssets(
        root=asset_root,
        style_presets_path=required["STYLE_PRESETS.md"],
        viewport_css_path=required["viewport-base.css"],
        selection_index_path=required["selection-index.json"],
        selection_index=selection_index,
        templates=records,
    )


# ---------------------------------------------------------------------------
# Style validation and persistence
# ---------------------------------------------------------------------------

STYLE_SCHEMA_VERSION = 1


IMAGE_VISUAL_TYPES = {
    "conceptual-diagram",
    "process-flow",
    "architecture-overview",
    "data-metaphor",
    "comparison-illustration",
    "scene-illustration",
    "abstract-motif",
    "icon-composition",
}


DEFAULT_IMAGE_GUIDANCE = ImageGuidance(
    enabled=False,
    visual_types=[],
    prompt_style_notes="",
    avoid_notes="",
    max_images_per_chapter=0,
)


IMAGE_SAFETY_GUIDANCE = (
    "Generated images must never include embedded text, letters, numbers, "
    "labels, logos, watermarks, UI chrome, or real identifiable people."
)


ASSET_VERSION = "frontend-slides-2026-07"


STYLE_FILENAME = "course_slide_style.json"


STYLE_SOURCE_FILENAME = "course_slide_style_source.md"


STYLE_STATS_FILENAME = "statistics_slide_style.json"


PRESENTATION_DESIGN_FILENAME = "result_presentation_design.md"


FONT_FAMILIES = {
    "archivo": ("Course Archivo", "archivo"),
    "dm-sans": ("Course DM Sans", "dm-sans"),
    "source-serif-4": ("Course Source Serif", "source-serif-4"),
    "space-grotesk": ("Course Space Grotesk", "space-grotesk"),
    "ibm-plex-mono": ("Course IBM Plex Mono", "ibm-plex-mono"),
}


DISPLAY_FONTS = {"archivo", "source-serif-4", "space-grotesk"}


BODY_FONTS = {"archivo", "dm-sans", "source-serif-4", "space-grotesk"}


MONO_FONTS = {"ibm-plex-mono"}


FONT_ALIASES = {
    "inter": "dm-sans",
    "arial": "dm-sans",
    "helvetica": "dm-sans",
    "manrope": "space-grotesk",
    "jetbrains-mono": "ibm-plex-mono",
    "space-mono": "ibm-plex-mono",
    "source-serif": "source-serif-4",
}


COLOR_KEYS = {
    "stage_bg",
    "background",
    "background_alt",
    "text",
    "muted",
    "accent",
    "accent2",
    "surface",
    "surface_alt",
    "border",
    "panel_fill",
}


COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


SHORT_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3})$")


RGB_COLOR_RE = re.compile(
    r"^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})"
    r"(?:\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?))?\s*\)$",
    flags=re.IGNORECASE,
)


KEY_RE = re.compile(r"[^a-z0-9]+")


PANEL_STYLES = {"open", "filled", "outlined"}


BORDER_STYLES = {"none", "thin", "thick", "dashed"}


SHADOW_STYLES = {"none", "soft", "hard"}


DENSITIES = {"low", "medium", "high"}


LAYOUTS = {"hero", "split", "top", "columns", "math"}


LAYOUT_ALIASES = {
    "overview": "hero",
    "title": "hero",
    "introduction": "hero",
    "content": "top",
    "lecture": "top",
    "application": "split",
    "example": "split",
    "comparison": "columns",
    "summary": "columns",
    "equation": "math",
    "derivation": "math",
    "full-page": "hero",
    "full-page-visual": "hero",
    "side-by-side": "split",
    "two-column": "columns",
    "two-columns": "columns",
}


PLACEHOLDER_SELECTION_TEXT = {
    "course-wide narrative approach",
    "pacing guidance",
    "what visual hierarchy should emphasize",
    "student engagement approach",
    "why this exact style and method fit the whole course",
}


@dataclass(frozen=True)
class StyleInventoryEntry:
    source: str
    key: str
    name: str
    summary: str
    source_ref: str
    # "light", "dark", or "mixed" for bold templates; empty for presets, whose
    # markdown does not declare one. Used to require a comparison set that spans
    # more than one visual register.
    scheme: str = ""


def style_slug(value: str) -> str:
    return KEY_RE.sub("-", value.lower()).strip("-")


def build_style_inventory(
    assets: FrontendSlidesAssets | None = None,
) -> tuple[list[StyleInventoryEntry], str]:
    assets = assets or load_assets()
    entries: list[StyleInventoryEntry] = []
    for name, section in preset_sections(assets.style_presets).items():
        entries.append(
            StyleInventoryEntry(
                source="preset",
                key=style_slug(name),
                name=name,
                summary=_compact(section, 1600),
                source_ref="STYLE_PRESETS.md",
            )
        )
    for record in assets.templates.values():
        summary = (
            f"Mood: {', '.join(record.mood)}. Tone: {', '.join(record.tone)}. "
            f"Formality: {record.formality}. Density: {record.density}. "
            f"Scheme: {record.scheme}. Best for: {record.best_for}. "
            f"Avoid for: {record.avoid_for}."
        )
        entries.append(
            StyleInventoryEntry(
                source="bold_template",
                key=record.slug,
                name=record.name,
                summary=summary,
                source_ref=record.design_md,
                scheme=record.scheme,
            )
        )
    entries.sort(key=lambda item: (item.source, item.key))
    if len(entries) != 46:
        raise FrontendSlidesError(
            f"Expected 46 frontend slide styles (12 presets + 34 templates), found {len(entries)}."
        )
    inventory_hash = sha256_text(
        json.dumps([asdict(entry) for entry in entries], sort_keys=True)
    )
    return entries, inventory_hash


def presentation_order(
    entries: list[StyleInventoryEntry], course_name: str
) -> list[StyleInventoryEntry]:
    """Return the candidate order shown to the model for one course.

    ``build_style_inventory`` sorts by ``(source, key)``, which puts the same
    handful of slugs at the top of every prompt and makes them disproportionately
    likely to be chosen. Shuffling per course removes that anchor while keeping a
    single course reproducible, because the seed comes from its name.

    Only the prompt-facing copy is reordered. ``inventory_hash`` stays on the
    canonical sort, so the fingerprint persisted in ``course_slide_style.json``
    is unaffected.
    """
    seed = int(sha256_text(course_name)[:16], 16)
    shuffled = list(entries)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def preset_sections(markdown: str) -> dict[str, str]:
    matches = list(
        re.finditer(r"^###\s+\d+\.\s+(.+?)\s*$", markdown, flags=re.MULTILINE)
    )
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        name = match.group(1).strip()
        sections[name] = markdown[match.start() : end].strip() + "\n"
    return sections


def selected_asset_text(
    selected: SelectedStyle,
    assets: FrontendSlidesAssets | None = None,
) -> str:
    assets = assets or load_assets()
    if selected.source == "bold_template":
        return assets.read_design_md(selected.key)
    if selected.source == "preset":
        for name, section in preset_sections(assets.style_presets).items():
            if style_slug(name) == selected.key:
                return section
    raise FrontendSlidesError(
        f"Selected style asset is unavailable: {selected.source}:{selected.key}"
    )


def validate_selection(
    payload: dict[str, Any], inventory: list[StyleInventoryEntry]
) -> tuple[SelectedStyle, PresentationMethod, str, dict[str, Any]]:
    selected = payload.get("selected_style")
    method = payload.get("presentation_method")
    if not isinstance(selected, dict) or not isinstance(method, dict):
        raise FrontendSlidesError(
            "Style decision requires selected_style and presentation_method objects."
        )
    source = _required_string(selected, "source")
    key = _required_string(selected, "key")
    lookup = {(entry.source, entry.key): entry for entry in inventory}
    entry = lookup.get((source, key))
    if entry is None:
        normalized_key = style_slug(key)
        suggestions = [
            f"{candidate.source}:{candidate.key}"
            for candidate in inventory
            if candidate.key == normalized_key
            or style_slug(candidate.name) == normalized_key
        ]
        hint = (
            f". Similar exact inventory pair(s): {', '.join(suggestions)}"
            if suggestions
            else ""
        )
        raise FrontendSlidesError(
            f"Unknown selected style: {source}:{key}{hint}"
        )

    density = _required_string(method, "density")
    if density not in DENSITIES:
        raise FrontendSlidesError("presentation_method.density must be low, medium, or high.")
    layout_rotation = method.get("layout_rotation")
    if (
        not isinstance(layout_rotation, list)
        or len(layout_rotation) < 2
        or any(item not in LAYOUTS for item in layout_rotation)
        or not any(item != "hero" for item in layout_rotation)
    ):
        raise FrontendSlidesError(
            "presentation_method.layout_rotation must contain at least two supported layouts."
        )
    presentation = PresentationMethod(
        narrative=_specific_string(method, "narrative", 30, 1200),
        pacing=_specific_string(method, "pacing", 20, 800),
        density=density,
        emphasis=_specific_string(method, "emphasis", 20, 800),
        layout_rotation=list(dict.fromkeys(layout_rotation)),
        engagement=_specific_string(method, "engagement", 20, 800),
    )
    reason = _specific_string(payload, "reason", 100, 1600)
    evidence = _validate_selection_evidence(
        payload,
        inventory=inventory,
        selected_pair=(entry.source, entry.key),
    )
    return (
        SelectedStyle(source=entry.source, key=entry.key, name=entry.name),
        presentation,
        reason,
        evidence,
    )


def _validate_selection_evidence(
    payload: dict[str, Any],
    *,
    inventory: list[StyleInventoryEntry],
    selected_pair: tuple[str, str],
) -> dict[str, Any]:
    raw_evidence = payload.get("selection_evidence")
    if not isinstance(raw_evidence, dict):
        raise FrontendSlidesError("selection_evidence must be an object.")

    raw_requirements = raw_evidence.get("course_requirements")
    if not isinstance(raw_requirements, list) or not 3 <= len(raw_requirements) <= 6:
        raise FrontendSlidesError(
            "selection_evidence.course_requirements must contain 3 to 6 items."
        )
    requirements: list[str] = []
    for index, value in enumerate(raw_requirements):
        requirement = _specific_value(
            value,
            f"selection_evidence.course_requirements[{index}]",
            20,
            300,
        )
        if requirement.casefold() in {item.casefold() for item in requirements}:
            raise FrontendSlidesError(
                "selection_evidence.course_requirements must be distinct."
            )
        requirements.append(requirement)

    raw_alternatives = raw_evidence.get("alternatives")
    if not isinstance(raw_alternatives, list) or not 2 <= len(raw_alternatives) <= 4:
        raise FrontendSlidesError(
            "selection_evidence.alternatives must contain 2 to 4 items."
        )
    lookup = {(item.source, item.key): item for item in inventory}
    seen_pairs: set[tuple[str, str]] = set()
    alternatives: list[dict[str, str]] = []
    for index, raw_alternative in enumerate(raw_alternatives):
        if not isinstance(raw_alternative, dict):
            raise FrontendSlidesError(
                f"selection_evidence.alternatives[{index}] must be an object."
            )
        source = _required_string(raw_alternative, "source")
        key = _required_string(raw_alternative, "key")
        pair = (source, key)
        if pair == selected_pair:
            raise FrontendSlidesError(
                "selection_evidence alternatives cannot include the selected style."
            )
        if pair in seen_pairs:
            raise FrontendSlidesError(
                "selection_evidence alternatives must be distinct."
            )
        inventory_entry = lookup.get(pair)
        if inventory_entry is None:
            raise FrontendSlidesError(
                f"Unknown alternative style: {source}:{key}"
            )
        rejection_reason = _specific_string(
            raw_alternative, "reason_rejected", 40, 800
        )
        seen_pairs.add(pair)
        alternatives.append(
            {
                "source": inventory_entry.source,
                "key": inventory_entry.key,
                "name": inventory_entry.name,
                "reason_rejected": rejection_reason,
            }
        )

    _require_comparison_breadth(
        selected_entry=lookup.get(selected_pair),
        alternative_entries=[lookup[(item[0], item[1])] for item in seen_pairs],
    )

    avoid_for_assessment = _specific_string(
        raw_evidence, "avoid_for_assessment", 80, 1200
    )
    return {
        "course_requirements": requirements,
        "alternatives": alternatives,
        "avoid_for_assessment": avoid_for_assessment,
    }


def _require_comparison_breadth(
    *,
    selected_entry: StyleInventoryEntry | None,
    alternative_entries: list[StyleInventoryEntry],
) -> None:
    """Reject a shortlist that only compared one visual register.

    Two or three near-identical light, medium-formality templates is not a
    comparison, and it is the shape the deliberation falls into when it anchors
    on the first plausible candidate. At least one rejected alternative has to
    come from somewhere else: a different scheme, or a preset, which is a
    structurally different family of asset.

    Presets do not declare a scheme, so they always satisfy the rule. This keeps
    the check from blocking a run it cannot actually evaluate.
    """
    if selected_entry is None or not selected_entry.scheme:
        return
    for entry in alternative_entries:
        if not entry.scheme or entry.scheme != selected_entry.scheme:
            return
    raise FrontendSlidesError(
        "selection_evidence.alternatives must compare more than one visual "
        f"register: every candidate uses the '{selected_entry.scheme}' scheme. "
        "Include at least one alternative with a different scheme or a preset."
    )


def canonicalize_selection_payload(
    payload: dict[str, Any],
    inventory: list[StyleInventoryEntry],
) -> tuple[dict[str, Any], list[str]]:
    """Normalize only unambiguous style identifiers and known layout synonyms."""
    normalized = deepcopy(payload)
    notes: list[str] = []
    selected = normalized.get("selected_style")
    if isinstance(selected, dict):
        source = selected.get("source")
        key = selected.get("key")
        if isinstance(source, str) and isinstance(key, str):
            exact = any(
                entry.source == source and entry.key == key
                for entry in inventory
            )
            if not exact:
                normalized_key = style_slug(key)
                candidates = [
                    entry
                    for entry in inventory
                    if entry.key == normalized_key
                    or style_slug(entry.name) == normalized_key
                ]
                if len(candidates) == 1:
                    candidate = candidates[0]
                    selected["source"] = candidate.source
                    selected["key"] = candidate.key
                    notes.append(
                        "Canonicalized selected style "
                        f"{source}:{key} to the unique inventory pair "
                        f"{candidate.source}:{candidate.key}."
                    )

    method = normalized.get("presentation_method")
    if isinstance(method, dict):
        rotation = method.get("layout_rotation")
        if isinstance(rotation, list) and all(
            isinstance(item, str) for item in rotation
        ):
            canonical_rotation: list[str] = []
            replacements: list[str] = []
            for item in rotation:
                key = style_slug(item)
                canonical = LAYOUT_ALIASES.get(key, key)
                if canonical != item:
                    replacements.append(f"{item}->{canonical}")
                if canonical not in canonical_rotation:
                    canonical_rotation.append(canonical)
            if replacements:
                method["layout_rotation"] = canonical_rotation
                notes.append(
                    "Canonicalized recognized layout labels: "
                    + ", ".join(replacements)
                    + "."
                )
    return normalized, notes


def canonicalize_materialization_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Convert recognized design tokens to the strict, packaged render interface."""
    normalized = deepcopy(payload)
    notes: list[str] = []
    theme = normalized.get("render_theme")
    if not isinstance(theme, dict):
        return normalized, notes

    colors = theme.get("colors")
    if isinstance(colors, dict):
        background = _opaque_color(colors.get("background"), (255, 255, 255))
        backdrop = _hex_to_rgb(background) if background else (255, 255, 255)
        if background is not None and colors.get("background") != background:
            original_background = colors.get("background")
            colors["background"] = background
            notes.append(
                "Canonicalized render_theme.colors.background from "
                f"{original_background!r} to {background!r}."
            )
        for key, value in list(colors.items()):
            if key == "background":
                continue
            canonical = _opaque_color(value, backdrop)
            if canonical is not None and canonical != value:
                colors[key] = canonical
                notes.append(
                    f"Canonicalized render_theme.colors.{key} from "
                    f"{value!r} to {canonical!r}."
                )

    font_fields = {
        "display_font": DISPLAY_FONTS,
        "body_font": BODY_FONTS,
        "mono_font": MONO_FONTS,
    }
    guidance_replacements: list[tuple[str, str]] = []
    for field, allowed in font_fields.items():
        value = theme.get(field)
        if not isinstance(value, str) or value in allowed:
            continue
        normalized_id = style_slug(value)
        canonical = FONT_ALIASES.get(normalized_id)
        if canonical in allowed:
            theme[field] = canonical
            notes.append(
                f"Mapped known font alias {field}={value!r} to packaged "
                f"font {canonical!r}."
            )
            guidance_replacements.append((value, canonical))

    guidance = normalized.get("ta_guidance")
    if isinstance(guidance, str):
        for original, canonical in guidance_replacements:
            packaged_name = FONT_FAMILIES[canonical][0].removeprefix("Course ")
            guidance = re.sub(
                rf"\b{re.escape(original)}\b",
                packaged_name,
                guidance,
                flags=re.IGNORECASE,
            )
        normalized["ta_guidance"] = guidance
    return normalized, notes


def _validate_image_guidance(raw: Any) -> ImageGuidance:
    if not isinstance(raw, dict):
        raise FrontendSlidesError("image_guidance must be an object.")
    allowed_fields = {
        "enabled",
        "visual_types",
        "prompt_style_notes",
        "avoid_notes",
        "max_images_per_chapter",
    }
    unknown_fields = sorted(set(raw) - allowed_fields)
    if unknown_fields:
        raise FrontendSlidesError(
            "image_guidance contains unsupported fields: "
            + ", ".join(unknown_fields)
        )
    enabled = raw.get("enabled")
    if not isinstance(enabled, bool):
        raise FrontendSlidesError("image_guidance.enabled must be a boolean.")
    raw_types = raw.get("visual_types")
    if not isinstance(raw_types, list) or any(
        not isinstance(item, str) for item in raw_types
    ):
        raise FrontendSlidesError("image_guidance.visual_types must be a list of strings.")
    visual_types = list(dict.fromkeys(item.strip() for item in raw_types if item.strip()))
    invalid = sorted(set(visual_types) - IMAGE_VISUAL_TYPES)
    if invalid:
        raise FrontendSlidesError(
            "image_guidance.visual_types contains unsupported values: "
            + ", ".join(invalid)
        )
    prompt_notes = raw.get("prompt_style_notes", "")
    avoid_notes = raw.get("avoid_notes", "")
    if not isinstance(prompt_notes, str) or len(prompt_notes.strip()) > 1200:
        raise FrontendSlidesError(
            "image_guidance.prompt_style_notes must be text of at most 1200 characters."
        )
    if not isinstance(avoid_notes, str) or len(avoid_notes.strip()) > 600:
        raise FrontendSlidesError(
            "image_guidance.avoid_notes must be text of at most 600 characters."
        )
    if "max_images_per_chapter" not in raw:
        raise FrontendSlidesError(
            "image_guidance.max_images_per_chapter is required."
        )
    budget = raw["max_images_per_chapter"]
    if budget is not None and (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or not 0 <= budget <= 3
    ):
        raise FrontendSlidesError(
            "image_guidance.max_images_per_chapter must be null or an integer "
            "from 0 to 3."
        )
    if not enabled:
        return DEFAULT_IMAGE_GUIDANCE
    if not visual_types:
        raise FrontendSlidesError(
            "Enabled image guidance requires at least one visual type."
        )
    if len(prompt_notes.strip()) < 40:
        raise FrontendSlidesError(
            "Enabled image guidance requires at least 40 characters of prompt style notes."
        )
    if budget is not None and budget < 1:
        raise FrontendSlidesError(
            "Enabled capped image guidance requires max_images_per_chapter of "
            "at least 1."
        )
    return ImageGuidance(
        enabled=True,
        visual_types=visual_types,
        prompt_style_notes=prompt_notes.strip(),
        avoid_notes=avoid_notes.strip(),
        max_images_per_chapter=budget,
    )


def validate_materialization(
    payload: dict[str, Any],
    *,
    selected_style: SelectedStyle,
    presentation_method: PresentationMethod,
    inventory_sha256: str,
    selected_asset_sha256: str,
    image_guidance: ImageGuidance | None = None,
) -> CourseSlideStyle:
    guidance = _bounded_string(payload, "ta_guidance", 4000)
    raw_theme = payload.get("render_theme")
    if not isinstance(raw_theme, dict):
        raise FrontendSlidesError("render_theme must be an object.")
    colors = raw_theme.get("colors")
    if not isinstance(colors, dict) or set(colors) != COLOR_KEYS:
        raise FrontendSlidesError(
            "render_theme.colors must contain exactly the supported color keys."
        )
    normalized_colors: dict[str, str] = {}
    for key, value in colors.items():
        if not isinstance(value, str) or not COLOR_RE.fullmatch(value):
            raise FrontendSlidesError(f"Invalid color for render_theme.colors.{key}.")
        normalized_colors[key] = value.lower()

    display_font = _choice(raw_theme, "display_font", DISPLAY_FONTS)
    body_font = _choice(raw_theme, "body_font", BODY_FONTS)
    mono_font = _choice(raw_theme, "mono_font", MONO_FONTS)
    title_size = _bounded_int(raw_theme, "title_size", 72, 128)
    heading_size = _bounded_int(raw_theme, "heading_size", 44, 78)
    panel_style = _choice(raw_theme, "panel_style", PANEL_STYLES)
    border_style = _choice(raw_theme, "border_style", BORDER_STYLES)
    shadow_style = _choice(raw_theme, "shadow_style", SHADOW_STYLES)
    grid_opacity = raw_theme.get("grid_opacity")
    if (
        isinstance(grid_opacity, bool)
        or not isinstance(grid_opacity, (int, float))
        or not 0 <= float(grid_opacity) <= 0.8
    ):
        raise FrontendSlidesError("render_theme.grid_opacity must be between 0 and 0.8.")

    resolved_image_guidance = (
        image_guidance
        if image_guidance is not None
        else _validate_image_guidance(
            payload.get("image_guidance", asdict(DEFAULT_IMAGE_GUIDANCE))
        )
    )
    return CourseSlideStyle(
        schema_version=STYLE_SCHEMA_VERSION,
        asset_version=ASSET_VERSION,
        selected_style=selected_style,
        presentation_method=presentation_method,
        ta_guidance=guidance,
        render_theme=RenderTheme(
            colors=normalized_colors,
            display_font=display_font,
            body_font=body_font,
            mono_font=mono_font,
            title_size=title_size,
            heading_size=heading_size,
            panel_style=panel_style,
            border_style=border_style,
            shadow_style=shadow_style,
            grid_opacity=float(grid_opacity),
        ),
        inventory_sha256=inventory_sha256,
        selected_asset_sha256=selected_asset_sha256,
        image_guidance=resolved_image_guidance,
    )


def course_style_from_dict(data: dict[str, Any]) -> CourseSlideStyle:
    try:
        selected_data = data["selected_style"]
        method_data = data["presentation_method"]
        theme_data = data["render_theme"]
        raw_image_guidance = data.get(
            "image_guidance", asdict(DEFAULT_IMAGE_GUIDANCE)
        )
        image_guidance = _validate_image_guidance(raw_image_guidance)
        style = CourseSlideStyle(
            schema_version=int(data["schema_version"]),
            asset_version=str(data["asset_version"]),
            selected_style=SelectedStyle(**selected_data),
            presentation_method=PresentationMethod(**method_data),
            ta_guidance=str(data["ta_guidance"]),
            render_theme=RenderTheme(**theme_data),
            inventory_sha256=str(data["inventory_sha256"]),
            selected_asset_sha256=str(data["selected_asset_sha256"]),
            image_guidance=image_guidance,
        )
    except (KeyError, TypeError, ValueError, FrontendSlidesError) as exc:
        raise FrontendSlidesError(f"Malformed {STYLE_FILENAME}: {exc}") from exc
    if style.schema_version != STYLE_SCHEMA_VERSION:
        raise FrontendSlidesError(
            f"Unsupported slide-style schema {style.schema_version}; expected {STYLE_SCHEMA_VERSION}."
        )
    if style.asset_version != ASSET_VERSION:
        raise FrontendSlidesError(
            f"Unsupported slide-style asset version {style.asset_version!r}; expected {ASSET_VERSION!r}."
        )
    if (
        style.selected_style.source not in {"preset", "bold_template"}
        or not style.selected_style.key
        or style_slug(style.selected_style.key) != style.selected_style.key
        or not style.selected_style.name.strip()
    ):
        raise FrontendSlidesError("Persisted selected_style is invalid.")
    if (
        style.presentation_method.density not in DENSITIES
        or len(style.presentation_method.layout_rotation) < 2
        or any(
            layout not in LAYOUTS
            for layout in style.presentation_method.layout_rotation
        )
        or not any(
            layout != "hero" for layout in style.presentation_method.layout_rotation
        )
    ):
        raise FrontendSlidesError("Persisted presentation_method is invalid.")
    # Re-run the strict materialization validator for values loaded from disk.
    return validate_materialization(
        {
            "ta_guidance": style.ta_guidance,
            "render_theme": asdict(style.render_theme),
            "image_guidance": asdict(style.image_guidance),
        },
        selected_style=style.selected_style,
        presentation_method=style.presentation_method,
        inventory_sha256=style.inventory_sha256,
        selected_asset_sha256=style.selected_asset_sha256,
    )


def renderer_theme(style: CourseSlideStyle) -> dict[str, str]:
    colors = style.render_theme.colors
    border_map = {
        "none": "0",
        "thin": "1px solid var(--border)",
        "thick": "3px solid var(--border)",
        "dashed": "2px dashed var(--border)",
    }
    shadow_map = {
        "none": "none",
        "soft": "0 18px 50px rgba(0,0,0,0.18)",
        "hard": "10px 10px 0 var(--accent2)",
    }
    panel_fill = (
        "transparent"
        if style.render_theme.panel_style == "open"
        else colors["panel_fill"]
    )
    display_family = FONT_FAMILIES[style.render_theme.display_font][0]
    body_family = FONT_FAMILIES[style.render_theme.body_font][0]
    mono_family = FONT_FAMILIES[style.render_theme.mono_font][0]
    return {
        **colors,
        "glow": colors["accent"] + "33",
        "grid": colors["text"] + "18",
        "grid_opacity": str(style.render_theme.grid_opacity),
        "display_font": f"'{display_family}', sans-serif",
        "body_font": f"'{body_family}', sans-serif",
        "mono_font": f"'{mono_family}', monospace",
        "title_size": f"{style.render_theme.title_size}px",
        "heading_size": f"{style.render_theme.heading_size}px",
        "panel_border": border_map[style.render_theme.border_style],
        "panel_fill": panel_fill,
        "shadow": shadow_map[style.render_theme.shadow_style],
        "carbon_theme": "nord",
        "carbon_background": "rgba(0,0,0,0)",
        "course_density": {
            "low": "1.06",
            "medium": "1",
            "high": "0.92",
        }[style.presentation_method.density],
    }


def write_course_style(path: Path, style: CourseSlideStyle) -> None:
    _atomic_write(path, json.dumps(asdict(style), indent=2, sort_keys=True) + "\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FrontendSlidesError(f"{key} must be a nonempty string.")
    return value.strip()


def _bounded_string(data: dict[str, Any], key: str, maximum: int) -> str:
    value = _required_string(data, key)
    if len(value) > maximum:
        raise FrontendSlidesError(f"{key} exceeds {maximum} characters.")
    return value


def _specific_string(
    data: dict[str, Any], key: str, minimum: int, maximum: int
) -> str:
    return _specific_value(data.get(key), key, minimum, maximum)


def _specific_value(value: Any, label: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrontendSlidesError(f"{label} must be a nonempty string.")
    stripped = value.strip()
    if len(stripped) < minimum:
        raise FrontendSlidesError(
            f"{label} must contain at least {minimum} characters of specific evidence."
        )
    if len(stripped) > maximum:
        raise FrontendSlidesError(f"{label} exceeds {maximum} characters.")
    if (
        stripped.casefold() in PLACEHOLDER_SELECTION_TEXT
        or "<course-specific" in stripped.casefold()
        or "<explain" in stripped.casefold()
    ):
        raise FrontendSlidesError(f"{label} still contains placeholder text.")
    return stripped


def _bounded_int(data: dict[str, Any], key: str, minimum: int, maximum: int) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise FrontendSlidesError(f"{key} must be an integer from {minimum} to {maximum}.")
    return value


def _choice(data: dict[str, Any], key: str, choices: set[str]) -> str:
    value = _required_string(data, key)
    if value not in choices:
        raise FrontendSlidesError(f"{key} must be one of: {', '.join(sorted(choices))}.")
    return value


def _compact(value: str, maximum: int) -> str:
    return " ".join(value.split())[:maximum]


def _opaque_color(
    value: Any,
    backdrop: tuple[int, int, int],
) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if COLOR_RE.fullmatch(stripped):
        return stripped.lower()
    short = SHORT_COLOR_RE.fullmatch(stripped)
    if short:
        return "#" + "".join(
            character * 2 for character in short.group(1)
        ).lower()
    rgb = RGB_COLOR_RE.fullmatch(stripped)
    if not rgb:
        return None
    channels = tuple(int(rgb.group(index)) for index in range(1, 4))
    if any(channel > 255 for channel in channels):
        return None
    alpha_text = rgb.group(4)
    alpha = float(alpha_text) if alpha_text is not None else 1.0
    composited = tuple(
        round(alpha * foreground + (1 - alpha) * background)
        for foreground, background in zip(channels, backdrop)
    )
    return "#" + "".join(f"{channel:02x}" for channel in composited)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    return tuple(
        int(value[index : index + 2], 16)
        for index in (1, 3, 5)
    )


# ---------------------------------------------------------------------------
# Presentation-design workflow
# ---------------------------------------------------------------------------

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
    image_generation_requested: bool = False,
    ai_decides_image_count: bool = False,
) -> CourseSlideStyle:
    output_path = Path(output_dir)
    style_path = output_path / STYLE_FILENAME
    if style_path.is_file() and not reselect:
        legacy_without_image_guidance = False
        try:
            persisted_style = json.loads(style_path.read_text(encoding="utf-8"))
            legacy_without_image_guidance = (
                isinstance(persisted_style, dict)
                and "image_guidance" not in persisted_style
            )
        except (OSError, json.JSONDecodeError):
            pass
        try:
            style = load_course_slide_style(output_path)
        except FrontendSlidesError as exc:
            raise FrontendSlidesError(
                "The persisted presentation-design authority is invalid and will not "
                "be silently replaced. Repair the frozen style files or explicitly run "
                "the foundation command with --reselect-presentation-design. "
                f"Details: {exc}"
            ) from exc
        upgraded_style = _with_required_image_safety_guidance(
            _with_required_guidance(style)
        )
        if upgraded_style != style:
            if legacy_without_image_guidance:
                legacy_payload = asdict(upgraded_style)
                legacy_payload.pop("image_guidance", None)
                _atomic_write(
                    style_path,
                    json.dumps(
                        legacy_payload, indent=2, sort_keys=True
                    )
                    + "\n",
                )
            else:
                write_course_style(style_path, upgraded_style)
        style = upgraded_style
        write_presentation_design_result(output_path, style)
        print(f"[resume] Loaded course slide style: {style.selected_style.name}")
        return style

    assets = load_assets()
    inventory, inventory_hash = build_style_inventory(assets)
    course_name = getattr(addie, "course_name", "") or ""
    # Prompt-facing order only; validation and the persisted hash keep using the
    # canonical sort returned by build_style_inventory.
    prompt_inventory = presentation_order(inventory, course_name)
    inventory_payload = [asdict(entry) for entry in prompt_inventory]
    selection_constraint = _selection_constraint(prompt_inventory)
    catalog_dict = getattr(addie, "catalog_dict", {})
    if not isinstance(catalog_dict, dict):
        raise FrontendSlidesError("ADDIE catalog context must be a dictionary.")
    catalog_style_preferences = catalog_dict.get(
        "presentation_style_preferences", {}
    )
    if not isinstance(catalog_style_preferences, dict):
        raise FrontendSlidesError(
            "Catalog presentation style preferences must be a dictionary."
        )
    course_context = {
        "course_name": course_name,
        "foundation_documents": [
            str(result)[:12000] for result in foundation_results[1:]
        ],
        "chapters": chapters,
        "catalog_style_preferences": catalog_style_preferences,
        "operator_image_generation_opt_in": image_generation_requested,
        "operator_ai_decides_image_count": ai_decides_image_count,
    }

    teaching_faculty = Agent(
        name="Teaching Faculty",
        role="Professor evaluating the course narrative and teaching approach",
        llm=addie.llm,
        system_prompt=(
            "Choose visual and presentation approaches that improve explanation, examples, "
            "student attention, and conceptual continuity across an entire course. Argue "
            "for a style that resonates with this subject in particular: what the field "
            "looks like, what its practitioners' materials look like, what would make a "
            "student recognize the discipline from the slide alone. A style that would "
            "suit any course equally is a weak answer, not a safe one."
        ),
    )
    instructional_designer = Agent(
        name="Instructional Designer",
        role=(
            "Expert evaluating structure, accessibility, density, layout, and "
            "rendering feasibility"
        ),
        llm=addie.llm,
        system_prompt=(
            "Evaluate course-wide slide styles for learning alignment, accessible contrast, "
            "readable density, layout variety, and consistent information hierarchy. Also "
            "evaluate whether each style and presentation method can be applied faithfully to "
            "generated Beamer content and deterministic 1920x1080 HTML rendering."
        ),
    )
    course_coordinator = Agent(
        name="Course Coordinator",
        role="Course consistency and delivery constraints reviewer",
        llm=addie.llm,
        system_prompt=(
            "Evaluate whether a style can remain coherent across every chapter and respect the "
            "course audience, institutional context, and delivery constraints. Coherence is "
            "about holding up across chapters, not about being unobtrusive: do not reject a "
            "distinctive style for being distinctive, and name the specific chapter or "
            "delivery context where a candidate would actually break down."
        ),
    )
    summarizer = Agent(
        name="Summarizer",
        role="Course slide-style decision maker",
        llm=addie.llm,
        system_prompt=(
            "Decide one course-wide style choice and presentation method. You receive the "
            "same course context and style inventory the reviewers had, followed by their "
            "discussion. Weigh the discussion against the course itself; where the reviewers "
            "converged without arguing, say so in the reason and check the choice against "
            "the inventory yourself rather than ratifying it. Write every course-specific "
            "field from the course context, never from the shape of this contract. "
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
        ],
        summary_agent=summarizer,
        max_rounds=2,
        summary_sees_context=True,
        independent_first_round=True,
        instruction_prompt=(
            "Discuss and choose exactly one visual style for all chapter presentations. "
            "Also decide the course-wide narrative, pacing, density, emphasis, layout rotation, "
            "and engagement method. Each reviewer "
            "must derive concrete visual requirements from the course audience and activities, "
            "compare at least three exact inventory candidates, and explicitly consider each "
            "candidate's Best for and Avoid for guidance. Explain tradeoffs using course-specific "
            "details; generic claims such as merely being professional, clear, or engaging are "
            "not sufficient. Treat every non-empty catalog_style_preferences value as direct, "
            "instructor-supplied visual guidance and more specific than the legacy "
            "instructor_style_preferences field. Honor those preferences when compatible, but "
            "prioritize accessibility, readability, course suitability, and renderer feasibility "
            "when they conflict with a preference or an inventory asset's guidance. Explicitly "
            "explain honored and unmet preferences in the course requirements and final selection "
            "rationale.\n\n"
            "This deliberation runs in two rounds. In round one you will not see the other "
            "reviewers' turns: nominate your own top three candidates and say what each one "
            "would cost this course, without hedging toward a safe default. In round two you "
            "will see every nomination; argue for one of them and say plainly where you "
            "disagree with a colleague. Your shortlist must span more than one visual "
            "register — do not nominate three near-identical light, medium-formality "
            "templates. The inventory is presented in no meaningful order, so position in "
            "the list is not a recommendation.\n\n"
            "Also decide whether "
            "AI-generated, text-free imagery would materially improve this specific "
            "course and which supported visual types fit. If "
            "operator_ai_decides_image_count is true, use null for "
            "max_images_per_chapter so the chapter placement referee can choose every "
            "strong eligible placement without a numeric budget. Otherwise choose a "
            "budget from zero to three images per chapter. The operator opt-in permits "
            "image spending but does not require it: an image recommendation of "
            "disabled remains a valid veto.\n\n"
            f"Course context:\n{json.dumps(course_context, ensure_ascii=False)}\n\n"
            "Complete style inventory (12 presets and 34 bold templates):\n"
            f"{json.dumps(inventory_payload, ensure_ascii=False)}"
        ),
        output_format="json",
    )
    summary, total_time, total_tokens = deliberation.run()
    selected_style: SelectedStyle | None = None
    presentation_method: PresentationMethod | None = None
    image_recommendation: ImageGuidance | None = None
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
            raw_image_recommendation = payload.get("image_recommendation")
            if raw_image_recommendation is None:
                image_recommendation = DEFAULT_IMAGE_GUIDANCE
            else:
                try:
                    image_recommendation = _validate_image_guidance(
                        raw_image_recommendation
                    )
                    if (
                        ai_decides_image_count
                        and image_recommendation.enabled
                        and image_recommendation.max_images_per_chapter
                        is not None
                    ):
                        image_recommendation = replace(
                            image_recommendation,
                            max_images_per_chapter=None,
                        )
                        note = (
                            "Normalized the image recommendation to AI-decides "
                            "count mode because the operator requested no fixed "
                            "chapter cap."
                        )
                        selection_normalizations.append(note)
                        print(f"[style normalization] {note}")
                except FrontendSlidesError as image_exc:
                    image_recommendation = DEFAULT_IMAGE_GUIDANCE
                    note = (
                        "Image recommendation was invalid and safely degraded "
                        f"to disabled guidance ({image_exc})."
                    )
                    selection_normalizations.append(note)
                    print(f"[style normalization] {note}")
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
                    inventory=prompt_inventory,
                ),
            )
            total_time += elapsed
            total_tokens += tokens
    assert (
        selected_style is not None
        and presentation_method is not None
        and selection_evidence is not None
        and image_recommendation is not None
    )

    selected_source = selected_asset_text(selected_style, assets)
    selected_hash = sha256_text(selected_source)
    materializer = Agent(
        name="Instructional Designer",
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
    materialization_image_context = {
        "course_name": course_context["course_name"],
        "chapters": course_context["chapters"],
        "operator_image_generation_opt_in": image_generation_requested,
        "operator_ai_decides_image_count": ai_decides_image_count,
        "image_generation_preferences": catalog_style_preferences.get(
            "image_generation_preferences", ""
        ),
    }
    materialization_prompt = (
        "Selected style:\n"
        f"{json.dumps(asdict(selected_style), indent=2)}\n\n"
        "Selected presentation method:\n"
        f"{json.dumps(asdict(presentation_method), indent=2)}\n\n"
        "Validated image recommendation from the presentation deliberation:\n"
        f"{json.dumps(asdict(image_recommendation), indent=2)}\n\n"
        "Course and chapter context for operational image prompting:\n"
        f"{json.dumps(materialization_image_context, ensure_ascii=False)[:16000]}\n\n"
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
            try:
                materialized_image_guidance = _validate_image_guidance(
                    materialization_payload.get("image_guidance")
                )
                if (
                    materialized_image_guidance.enabled
                    != image_recommendation.enabled
                ):
                    raise FrontendSlidesError(
                        "image_guidance.enabled must preserve the deliberation verdict."
                    )
                recommendation_cap = image_recommendation.max_images_per_chapter
                materialized_cap = (
                    materialized_image_guidance.max_images_per_chapter
                )
                if (
                    ai_decides_image_count
                    and materialized_image_guidance.enabled
                    and materialized_cap is not None
                ):
                    materialized_image_guidance = replace(
                        materialized_image_guidance,
                        max_images_per_chapter=None,
                    )
                    materialized_cap = None
                    note = (
                        "Normalized materialized image guidance to AI-decides "
                        "count mode."
                    )
                    if note not in materialization_normalizations:
                        materialization_normalizations.append(note)
                expands_budget = (
                    recommendation_cap is not None
                    and (
                        materialized_cap is None
                        or materialized_cap > recommendation_cap
                    )
                )
                if materialized_image_guidance.enabled and (
                    not set(materialized_image_guidance.visual_types).issubset(
                        image_recommendation.visual_types
                    )
                    or expands_budget
                ):
                    raise FrontendSlidesError(
                        "image_guidance cannot expand the deliberated visual "
                        "types or image budget."
                    )
            except FrontendSlidesError as image_exc:
                if attempt < 2:
                    raise
                materialized_image_guidance = DEFAULT_IMAGE_GUIDANCE
                note = (
                    "Image guidance materialization remained invalid after "
                    "retries and safely degraded to disabled guidance "
                    f"({image_exc})."
                )
                if note not in materialization_normalizations:
                    materialization_normalizations.append(note)
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
                image_guidance=materialized_image_guidance,
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
    style = _with_required_image_safety_guidance(_with_required_guidance(style))

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
                    "Summarizer",
                ],
                "selected_style": asdict(style.selected_style),
                # 1-based position of the winner in the order the model actually
                # saw. A run of low ranks across courses means the shuffle stopped
                # working and position is driving the choice again.
                "selected_prompt_rank": _prompt_rank(
                    prompt_inventory, style.selected_style
                ),
                "image_recommendation": asdict(image_recommendation),
                "catalog_style_preferences": catalog_style_preferences,
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
    image_guidance = style.image_guidance
    image_types = (
        ", ".join(image_guidance.visual_types)
        if image_guidance.visual_types
        else "None"
    )
    image_cap_text = (
        "AI decides (no fixed cap)"
        if image_guidance.max_images_per_chapter is None
        else str(image_guidance.max_images_per_chapter)
    )
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
        "## Image Generation Guidance\n\n"
        f"- Enabled by deliberation: {image_guidance.enabled}\n"
        f"- Visual types: {image_types}\n"
        f"- Maximum images per chapter: {image_cap_text}\n"
        f"- Prompt style: {image_guidance.prompt_style_notes or 'None'}\n"
        f"- Avoid: {image_guidance.avoid_notes or 'None'}\n\n"
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


def _with_required_image_safety_guidance(
    style: CourseSlideStyle,
) -> CourseSlideStyle:
    guidance = style.image_guidance
    if not guidance.enabled or IMAGE_SAFETY_GUIDANCE in guidance.avoid_notes:
        return style
    separator = "\n\n" if guidance.avoid_notes.strip() else ""
    available = 600 - len(separator) - len(IMAGE_SAFETY_GUIDANCE)
    existing = guidance.avoid_notes.strip()[:available].rstrip()
    return replace(
        style,
        image_guidance=replace(
            guidance,
            avoid_notes=f"{existing}{separator}{IMAGE_SAFETY_GUIDANCE}",
        ),
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
    value = parse_json_object(text)
    if value is None:
        raise FrontendSlidesError(
            "Agent response did not contain a valid JSON object."
        )
    return value


def _call_agent(agent: Agent, prompt: str) -> tuple[str, float, int]:
    result = agent.generate_response(prompt, stream=True, save_to_history=False)
    if not isinstance(result, tuple) or len(result) != 3:
        raise FrontendSlidesError(f"{agent.name} failed to return response accounting.")
    response, elapsed, tokens = result
    if not isinstance(response, str) or response.startswith("Error:"):
        raise FrontendSlidesError(f"{agent.name} failed: {response}")
    return response, float(elapsed), int(tokens)


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
    "density": "<low, medium, or high, chosen for this course's slide content>",
    "emphasis": "<course-specific visual emphasis of at least 20 characters>",
    "layout_rotation": ["<supported layout>", "<another supported layout>"],
    "engagement": "<course-specific engagement method of at least 20 characters>"
  }},
  "image_recommendation": {{
    "enabled": true,
    "visual_types": ["conceptual-diagram", "scene-illustration"],
    "prompt_style_notes": "<at least 40 course-specific characters describing suitable image style>",
    "avoid_notes": "<optional course-specific exclusions>",
    "max_images_per_chapter": 2
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
- image_recommendation.enabled must be a boolean. When enabled, visual_types
  must contain supported values and prompt_style_notes must be course-specific.
  When operator_ai_decides_image_count is true, max_images_per_chapter must be
  null. Otherwise it must be 1 to 3. When disabled, return an empty visual_types
  list and a zero budget.
- supported image visual types are: {", ".join(sorted(IMAGE_VISUAL_TYPES))}.
- layout_rotation must contain at least two distinct values selected from:
  "hero", "split", "top", "columns", "math".
- alternatives must contain 2 to 4 distinct exact inventory pairs, must not contain
  the selected style, and must come from candidates actually compared in the discussion.
  Each rejection must identify a course-specific tradeoff.
- the compared set must span more than one visual register. At least one alternative
  must use a different "scheme" value than the selected entry, or be a preset. A
  shortlist of near-identical light, medium-formality templates is rejected.
- avoid_for_assessment must accurately state the selected inventory entry's Avoid for
  warning before explaining why it does or does not conflict with this presentation context.
  It is a disclosure, not a tiebreak: do not choose a style merely because its Avoid for
  warning is the easiest one to clear. Pick the style that fits the course best and then
  report its warning honestly.
- the inventory is presented in no meaningful order. Position in the list carries no
  recommendation; judge every candidate on its Best for, Avoid for, mood, and scheme.
- when non-empty catalog_style_preferences are supplied, course_requirements and reason
  must explicitly explain which preferences are honored and which cannot be satisfied;
  preferences do not override accessibility, readability, course suitability, renderer
  feasibility, or the selected inventory entry's constraints.
- do not copy placeholder prose from this contract. Generic claims such as "professional
  and clear" are not adequate without details from the supplied course context.

ALLOWED_STYLE_PAIRS:
{json.dumps(allowed_pairs, ensure_ascii=False)}
"""


def _prompt_rank(
    prompt_inventory: list[StyleInventoryEntry], selected: SelectedStyle
) -> int | None:
    for index, entry in enumerate(prompt_inventory):
        if (entry.source, entry.key) == (selected.source, selected.key):
            return index + 1
    return None


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
  "image_guidance": {{
    "enabled": true,
    "visual_types": ["conceptual-diagram"],
    "prompt_style_notes": "course-specific image style guidance of at least 40 characters",
    "avoid_notes": "course-specific exclusions under 600 characters",
    "max_images_per_chapter": 2
  }},
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
image_guidance.enabled must preserve the validated deliberation verdict.
max_images_per_chapter may be null to delegate the chapter image count to the
placement referee without a fixed numeric cap.
Allowed image visual types: {", ".join(sorted(IMAGE_VISUAL_TYPES))}.
Choose exactly one value for each enum; never return pipe-separated alternatives.
Allowed display_font values: archivo, source-serif-4, space-grotesk.
Allowed body_font values: archivo, dm-sans, source-serif-4, space-grotesk.
Allowed mono_font value: ibm-plex-mono.
Allowed panel_style values: open, filled, outlined.
Allowed border_style values: none, thin, thick, dashed.
Allowed shadow_style values: none, soft, hard.
All packaged font identifiers: {", ".join(sorted(FONT_FAMILIES))}.
"""
