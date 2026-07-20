from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .assets import FrontendSlidesAssets, load_assets
from .errors import FrontendSlidesError
from .models import (
    CourseSlideStyle,
    PresentationMethod,
    RenderTheme,
    SelectedStyle,
)


STYLE_SCHEMA_VERSION = 1
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
}


@dataclass(frozen=True)
class StyleInventoryEntry:
    source: str
    key: str
    name: str
    summary: str
    source_ref: str


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
) -> tuple[SelectedStyle, PresentationMethod, str]:
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
        narrative=_bounded_string(method, "narrative", 1200),
        pacing=_bounded_string(method, "pacing", 800),
        density=density,
        emphasis=_bounded_string(method, "emphasis", 800),
        layout_rotation=list(dict.fromkeys(layout_rotation)),
        engagement=_bounded_string(method, "engagement", 800),
    )
    reason = _bounded_string(payload, "reason", 1600)
    return SelectedStyle(source=entry.source, key=entry.key, name=entry.name), presentation, reason


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
        for key, value in list(colors.items()):
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


def validate_materialization(
    payload: dict[str, Any],
    *,
    selected_style: SelectedStyle,
    presentation_method: PresentationMethod,
    inventory_sha256: str,
    selected_asset_sha256: str,
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
    )


def course_style_from_dict(data: dict[str, Any]) -> CourseSlideStyle:
    try:
        selected_data = data["selected_style"]
        method_data = data["presentation_method"]
        theme_data = data["render_theme"]
        style = CourseSlideStyle(
            schema_version=int(data["schema_version"]),
            asset_version=str(data["asset_version"]),
            selected_style=SelectedStyle(**selected_data),
            presentation_method=PresentationMethod(**method_data),
            ta_guidance=str(data["ta_guidance"]),
            render_theme=RenderTheme(**theme_data),
            inventory_sha256=str(data["inventory_sha256"]),
            selected_asset_sha256=str(data["selected_asset_sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
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


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


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
