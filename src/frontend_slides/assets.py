from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    preview_md: str
    design_md: str


@dataclass(frozen=True)
class FrontendSlidesAssets:
    root: Path
    style_presets_path: Path
    viewport_css_path: Path
    html_template_path: Path
    animation_patterns_path: Path
    selection_index_path: Path
    selection_index: dict[str, Any]
    templates: dict[str, TemplateRecord]

    @property
    def style_presets(self) -> str:
        return self.style_presets_path.read_text(encoding="utf-8")

    @property
    def viewport_css(self) -> str:
        return self.viewport_css_path.read_text(encoding="utf-8")

    @property
    def html_template(self) -> str:
        return self.html_template_path.read_text(encoding="utf-8")

    @property
    def animation_patterns(self) -> str:
        return self.animation_patterns_path.read_text(encoding="utf-8")

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

    def read_preview_md(self, slug: str) -> str:
        return self.read_asset(self.template(slug).preview_md)

    def read_design_md(self, slug: str) -> str:
        return self.read_asset(self.template(slug).design_md)


def default_asset_root() -> Path:
    return Path(__file__).resolve().parent / "skill_assets" / "frontend_slides"


def load_assets(root: Path | str | None = None) -> FrontendSlidesAssets:
    asset_root = Path(root) if root else default_asset_root()
    required = {
        "STYLE_PRESETS.md": asset_root / "STYLE_PRESETS.md",
        "viewport-base.css": asset_root / "viewport-base.css",
        "html-template.md": asset_root / "html-template.md",
        "animation-patterns.md": asset_root / "animation-patterns.md",
        "selection-index.json": asset_root / "bold-template-pack" / "selection-index.json",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        raise SkillAssetError(f"Missing required frontend-slides assets: {', '.join(missing)}")

    selection_index = json.loads(required["selection-index.json"].read_text(encoding="utf-8"))
    records: dict[str, TemplateRecord] = {}
    for item in selection_index.get("templates", []):
        record = TemplateRecord(**item)
        preview_path = asset_root / record.preview_md
        design_path = asset_root / record.design_md
        if not preview_path.exists():
            raise SkillAssetError(f"Missing preview.md for template {record.slug}: {record.preview_md}")
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
        html_template_path=required["html-template.md"],
        animation_patterns_path=required["animation-patterns.md"],
        selection_index_path=required["selection-index.json"],
        selection_index=selection_index,
        templates=records,
    )
