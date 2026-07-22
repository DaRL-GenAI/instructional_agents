from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.ADDIE import ADDIERunner
from src.slide_style import (
    CourseSlideStyle,
    PresentationMethod,
    RenderTheme,
    SelectedStyle,
    ASSET_VERSION,
    STYLE_FILENAME,
    STYLE_SOURCE_FILENAME,
    build_style_inventory,
    selected_asset_text,
    sha256_text,
    write_course_style,
)


def _write_style(output_dir: Path) -> None:
    selected = SelectedStyle("bold_template", "cobalt-grid", "Cobalt Grid")
    source = selected_asset_text(selected)
    _, inventory_hash = build_style_inventory()
    style = CourseSlideStyle(
        schema_version=1,
        asset_version=ASSET_VERSION,
        selected_style=selected,
        presentation_method=PresentationMethod(
            narrative="progressive concepts",
            pacing="measured",
            density="medium",
            emphasis="worked examples",
            layout_rotation=["hero", "split"],
            engagement="guided questions",
        ),
        ta_guidance="Use a clear hierarchy.",
        render_theme=RenderTheme(
            colors={
                "stage_bg": "#111827",
                "background": "#f8f2df",
                "background_alt": "#eee2c9",
                "text": "#1328aa",
                "muted": "#4b5a8a",
                "accent": "#1438ff",
                "accent2": "#111827",
                "surface": "#fffaf0",
                "surface_alt": "#e7ddc6",
                "border": "#1438ff",
                "panel_fill": "#fffaf0",
            },
            display_font="source-serif-4",
            body_font="dm-sans",
            mono_font="ibm-plex-mono",
            title_size=110,
            heading_size=64,
            panel_style="filled",
            border_style="thin",
            shadow_style="soft",
            grid_opacity=0.2,
        ),
        inventory_sha256=inventory_hash,
        selected_asset_sha256=sha256_text(source),
    )
    write_course_style(output_dir / STYLE_FILENAME, style)
    (output_dir / STYLE_SOURCE_FILENAME).write_text(source, encoding="utf-8")


def test_runner_appends_presentation_design_as_seventh_foundation_result(
    tmp_path: Path,
) -> None:
    deliberations = []
    for index in range(6):
        deliberation = SimpleNamespace(
            id=f"foundation_{index}",
            name=f"Foundation {index}",
            output_format="md",
        )
        deliberations.append(deliberation)
        title = deliberation.name
        (tmp_path / f"result_{deliberation.id}.md").write_text(
            f"{title}\n{'=' * len(title)}\n\nResult {index}\n",
            encoding="utf-8",
        )
    (tmp_path / "processed_chapters.json").write_text(
        json.dumps([{"title": "Chapter 1", "description": "Introduction"}]),
        encoding="utf-8",
    )
    _write_style(tmp_path)
    addie = SimpleNamespace(
        course_name="Test Course",
        deliberations=deliberations,
        copilot=False,
        llm=object(),
    )
    runner = ADDIERunner(addie, output_dir=str(tmp_path), resume=True)
    runner.setup()

    runner.run_foundation_deliberations()

    assert len(runner.results) == 8
    assert runner.results[0] == "Test Course"
    assert "## Final Style" in runner.results[7]
    assert "- Key: `cobalt-grid`" in runner.results[7]
