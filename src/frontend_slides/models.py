from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ContentElement:
    kind: str
    title: str | None = None
    text: str = ""
    items: list["ListItem"] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    ordered: bool = False
    start: int = 1
    raw: str = ""
    language: str | None = None
    children: list["ContentElement"] = field(default_factory=list)
    image_data_uri: str | None = None
    env: str | None = None


@dataclass
class ListItem:
    text: str
    children: list[ContentElement] = field(default_factory=list)


@dataclass
class BeamerSlide:
    index: int
    title: str
    elements: list[ContentElement]
    raw_tex: str
    is_titlepage: bool = False
    frame_title_argument: str | None = None


@dataclass
class BeamerDeck:
    source_path: Path
    title: str
    slides: list[BeamerSlide]
    metadata: dict[str, str] = field(default_factory=dict)
    unsupported_environments: list[str] = field(default_factory=list)

    @property
    def slide_count(self) -> int:
        return len(self.slides)


@dataclass
class StyleCandidate:
    id: str
    name: str
    source: str
    preset_name: str | None = None
    slug: str | None = None
    visual_thesis: str = ""
    rationale: str = ""
    preview_md: str | None = None
    design_md: str | None = None


@dataclass
class StylePlan:
    deck_title: str
    density: str
    mood: list[str]
    previews: list[StyleCandidate]
    selected_preview_id: str
    reason: str
    raw_agent_response: str | None = None

    @property
    def selected(self) -> StyleCandidate:
        for candidate in self.previews:
            if candidate.id == self.selected_preview_id:
                return candidate
        return self.previews[0]


@dataclass
class RunResult:
    output_dir: Path
    preview_dir: Path
    gallery_path: Path
    presentation_path: Path
    manifest_path: Path
    selected_style: StyleCandidate
    slide_count: int
    warnings: list[str] = field(default_factory=list)
    generated_images: list[dict[str, Any]] = field(default_factory=list)
    provided_images: list[dict[str, Any]] = field(default_factory=list)
    cost_analysis_path: Path | None = None
    inference_time_path: Path | None = None
    pdf_path: Path | None = None
    pptx_path: Path | None = None


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
class CourseSlideStyle:
    schema_version: int
    asset_version: str
    selected_style: SelectedStyle
    presentation_method: PresentationMethod
    ta_guidance: str
    render_theme: RenderTheme
    inventory_sha256: str
    selected_asset_sha256: str


@dataclass(frozen=True)
class ChapterFrontendResult:
    html_path: Path
    latex_pdf_path: Path
    html_pdf_path: Path
    html_pptx_path: Path
    manifest_path: Path
    slide_count: int
    skipped: bool = False


def to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
