from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyPDF2 import PdfReader, PdfWriter
from pptx import Presentation

from src.frontend_slides.assets import load_assets
from src.frontend_slides.beamer import parse_beamer
from src.frontend_slides.errors import FrontendSlidesError
from src.frontend_slides.export import export_html_deck
from src.frontend_slides.finalize import finalize_chapter
from src.frontend_slides.models import (
    CourseSlideStyle,
    PresentationMethod,
    RenderTheme,
    SelectedStyle,
)
from src.frontend_slides.render import render_course_presentation_html
from src.frontend_slides.runtime import prepare_offline_runtime
from src.frontend_slides.split import split_overloaded_slides
from src.frontend_slides.style import (
    ASSET_VERSION,
    COLOR_KEYS,
    STYLE_FILENAME,
    STYLE_SOURCE_FILENAME,
    build_style_inventory,
    selected_asset_text,
    sha256_file,
    sha256_text,
    validate_materialization,
    write_course_style,
)
from src.frontend_slides.style_workflow import (
    ensure_course_slide_style,
    load_course_slide_style,
)
from src.frontend_slides.validation import (
    validate_html_contract,
    validate_offline_contract,
)


def make_style(source_text: str | None = None) -> CourseSlideStyle:
    selected_style = SelectedStyle("bold_template", "cobalt-grid", "Cobalt Grid")
    source_text = source_text or selected_asset_text(selected_style)
    _, inventory_hash = build_style_inventory()
    return CourseSlideStyle(
        schema_version=1,
        asset_version=ASSET_VERSION,
        selected_style=selected_style,
        presentation_method=PresentationMethod(
            "concept progression",
            "measured",
            "medium",
            "worked examples",
            ["hero", "split", "top"],
            "guided questions",
        ),
        ta_guidance="Use strong cobalt hierarchy and readable worked examples.",
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
        selected_asset_sha256=sha256_text(source_text),
    )


def write_style(course_dir: Path, source_text: str | None = None) -> None:
    source_text = source_text or selected_asset_text(
        SelectedStyle("bold_template", "cobalt-grid", "Cobalt Grid")
    )
    course_dir.mkdir(parents=True, exist_ok=True)
    write_course_style(course_dir / STYLE_FILENAME, make_style(source_text))
    (course_dir / STYLE_SOURCE_FILENAME).write_text(source_text, encoding="utf-8")


def write_beamer(path: Path) -> None:
    path.write_text(
        r"""\documentclass{beamer}
\title{Offline Course}
\begin{document}
\begin{frame}\titlepage\end{frame}
\begin{frame}{Nested Concepts}
\begin{itemize}
\item First idea
\item Second idea with \(x^2 + y^2\)
\begin{itemize}\item Nested explanation\end{itemize}
\end{itemize}
\end{frame}
\begin{frame}{Equation}
\begin{align}
a &= b + c \\
d &= e
\end{align}
\end{frame}
\end{document}
""",
        encoding="utf-8",
    )


def test_inventory_contains_all_46_styles() -> None:
    inventory, digest = build_style_inventory(load_assets())

    assert len(inventory) == 46
    assert sum(item.source == "preset" for item in inventory) == 12
    assert sum(item.source == "bold_template" for item in inventory) == 34
    assert len(digest) == 64


def test_materialization_rejects_arbitrary_css_and_unknown_fonts() -> None:
    style = make_style()
    payload = {
        "ta_guidance": "Safe guidance",
        "render_theme": {
            **asdict(style.render_theme),
            "display_font": "url(javascript:alert(1))",
        },
    }

    with pytest.raises(FrontendSlidesError, match="display_font"):
        validate_materialization(
            payload,
            selected_style=style.selected_style,
            presentation_method=style.presentation_method,
            inventory_sha256="inventory",
            selected_asset_sha256=style.selected_asset_sha256,
        )


def test_offline_renderer_parses_splits_and_has_no_remote_urls(tmp_path: Path) -> None:
    tex = tmp_path / "slides.tex"
    write_beamer(tex)
    deck, _ = split_overloaded_slides(parse_beamer(tex))
    style = make_style()
    _, font_css = prepare_offline_runtime(tmp_path, style)

    html = render_course_presentation_html(
        deck, style, load_assets(), font_css=font_css
    )

    assert validate_html_contract(html, deck.slide_count, load_assets().viewport_css) == []
    assert validate_offline_contract(html) == []
    assert "frontend-assets/mathjax/tex-svg.js" in html
    assert "https://" not in html


def test_style_workflow_uses_five_roles_and_selected_asset_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    selection = json.dumps(
        {
            "selected_style": {
                "source": "bold_template",
                "key": "cobalt-grid",
            },
            "presentation_method": {
                "narrative": "concept progression",
                "pacing": "measured",
                "density": "medium",
                "emphasis": "worked examples",
                "layout_rotation": ["hero", "split", "top"],
                "engagement": "guided questions",
            },
            "reason": "Fits the course.",
        }
    )
    materialization = json.dumps(
        {
            "ta_guidance": "Use cobalt hierarchy.",
            "render_theme": asdict(make_style().render_theme),
        }
    )

    def fake_deliberation_run(self):
        seen["roles"] = [agent.name for agent in self.agents] + [self.summary_agent.name]
        self.discussion_history = [{"agent": "Teaching Faculty", "content": "Discussion"}]
        return selection, 1.0, 10

    def fake_generate(self, prompt, stream=True, save_to_history=False):
        if self.name == "Teaching Assistant" and "Selected style asset" in prompt:
            seen["materialization_prompt"] = prompt
            return materialization, 1.0, 10
        raise AssertionError(f"Unexpected repair call for {self.name}")

    monkeypatch.setattr(
        "src.frontend_slides.style_workflow.Deliberation.run",
        fake_deliberation_run,
    )
    monkeypatch.setattr(
        "src.frontend_slides.style_workflow.Agent.generate_response",
        fake_generate,
    )
    addie = SimpleNamespace(course_name="Test Course", llm=object())

    style = ensure_course_slide_style(
        addie,
        tmp_path,
        ["Test Course", "Foundation document"],
        [{"title": "Chapter 1", "description": "Intro"}],
    )

    assert seen["roles"] == [
        "Teaching Faculty",
        "Instructional Designer",
        "Course Coordinator",
        "Teaching Assistant",
        "Summarizer",
    ]
    prompt = str(seen["materialization_prompt"])
    assert "Cobalt Grid" in prompt
    assert "Complete style inventory" not in prompt
    assert style.selected_style.key == "cobalt-grid"
    assert load_course_slide_style(tmp_path) == style


def test_style_resume_makes_no_agent_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_style(tmp_path)
    monkeypatch.setattr(
        "src.frontend_slides.style_workflow.Deliberation.run",
        lambda _self: pytest.fail("style deliberation should be skipped"),
    )

    style = ensure_course_slide_style(
        SimpleNamespace(course_name="Test", llm=object()),
        tmp_path,
        [],
        [],
    )

    assert style.selected_style.key == "cobalt-grid"


def test_invalid_style_selection_retries_twice_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair_calls = 0
    monkeypatch.setattr(
        "src.frontend_slides.style_workflow.Deliberation.run",
        lambda _self: ('{"selected_style":{"source":"preset","key":"missing"}}', 1.0, 5),
    )

    def invalid_repair(self, prompt, stream=True, save_to_history=False):
        nonlocal repair_calls
        repair_calls += 1
        return "not json", 1.0, 5

    monkeypatch.setattr(
        "src.frontend_slides.style_workflow.Agent.generate_response",
        invalid_repair,
    )

    with pytest.raises(FrontendSlidesError, match="after retries"):
        ensure_course_slide_style(
            SimpleNamespace(course_name="Test", llm=object()),
            tmp_path,
            ["Test", "Foundation"],
            [{"title": "One", "description": "Chapter"}],
        )

    assert repair_calls == 2
    assert not (tmp_path / STYLE_FILENAME).exists()


def test_finalizer_regenerates_only_missing_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-existing")
    (chapter / "slides.html").write_text("<html>existing</html>", encoding="utf-8")
    (chapter / "slides-html.pdf").write_bytes(b"%PDF-html")
    (chapter / "slide-splits.json").write_text("{}", encoding="utf-8")
    prepare_offline_runtime(chapter, make_style())
    manifest = {
        "source_sha256": sha256_file(chapter / "slides.tex"),
        "style_sha256": sha256_file(course / STYLE_FILENAME),
        "slide_count": 3,
    }
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    calls: list[tuple[Path | None, Path | None]] = []

    monkeypatch.setattr(
        "src.frontend_slides.finalize.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("LaTeX should not recompile"),
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        calls.append((pdf_path, pptx_path))
        assert pdf_path is None
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr("src.frontend_slides.finalize.export_html_deck", fake_export)

    result = finalize_chapter(course, chapter)

    assert len(calls) == 1
    assert calls[0][0] is None
    assert result.html_pptx_path.read_bytes() == b"pptx"


def test_export_failure_preserves_successful_and_previous_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    (chapter / "slides-html.pdf").write_bytes(b"%PDF-previous")
    monkeypatch.setattr(
        "src.frontend_slides.finalize.LaTeXCompiler.compile_one",
        lambda *_args: chapter / "slides.pdf",
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.validate_with_playwright",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.export_html_deck",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("capture failed")),
    )

    with pytest.raises(FrontendSlidesError, match="successful artifacts were preserved"):
        finalize_chapter(course, chapter)

    assert (chapter / "slides.pdf").read_bytes() == b"%PDF-latex"
    assert (chapter / "slides.html").is_file()
    assert (chapter / "slides-html.pdf").read_bytes() == b"%PDF-previous"
    assert not (chapter / "frontend-slides-manifest.json").exists()


def test_export_failure_promotes_a_completed_sibling_export(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    monkeypatch.setattr(
        "src.frontend_slides.finalize.LaTeXCompiler.compile_one",
        lambda *_args: chapter / "slides.pdf",
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.validate_with_playwright",
        lambda *_args: [],
    )

    def partial_export(_html, *, pdf_path, pptx_path):
        writer = PdfWriter()
        writer.add_blank_page(width=1920, height=1080)
        with pdf_path.open("wb") as handle:
            writer.write(handle)
        raise RuntimeError("PPTX failed")

    monkeypatch.setattr(
        "src.frontend_slides.finalize.export_html_deck", partial_export
    )

    with pytest.raises(FrontendSlidesError, match="successful artifacts were preserved"):
        finalize_chapter(course, chapter)

    assert len(PdfReader(str(chapter / "slides-html.pdf")).pages) == 1
    assert not (chapter / "slides-html.pptx").exists()


def test_style_change_does_not_recompile_latex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    previous_style_hash = "0" * 64
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": sha256_file(chapter / "slides.tex"),
                "style_sha256": previous_style_hash,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A style-only change must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.validate_with_playwright",
        lambda *_args: [],
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        pdf_path.write_bytes(b"%PDF-html")
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.frontend_slides.finalize.export_html_deck", fake_export
    )

    result = finalize_chapter(course, chapter)

    assert result.slide_count == 3
    assert (chapter / "slides.pdf").read_bytes() == b"%PDF-latex"


def test_failed_html_validation_preserves_previous_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    previous_html = "<html>previous validated deck</html>"
    (chapter / "slides.html").write_text(previous_html, encoding="utf-8")
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(
            {
                "source_sha256": sha256_file(chapter / "slides.tex"),
                "style_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A style-only change must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.finalize.validate_with_playwright",
        lambda *_args: ["synthetic overflow"],
    )

    with pytest.raises(FrontendSlidesError, match="synthetic overflow"):
        finalize_chapter(course, chapter)

    assert (chapter / "slides.html").read_text(encoding="utf-8") == previous_html
    assert not (chapter / "slides.tmp.html").exists()


@pytest.mark.playwright
def test_static_export_smoke(tmp_path: Path) -> None:
    tex = tmp_path / "slides.tex"
    write_beamer(tex)
    deck, _ = split_overloaded_slides(parse_beamer(tex))
    style = make_style()
    _, font_css = prepare_offline_runtime(tmp_path, style)
    html_path = tmp_path / "slides.html"
    html_path.write_text(
        render_course_presentation_html(
            deck, style, load_assets(), font_css=font_css
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "slides-html.pdf"
    pptx_path = tmp_path / "slides-html.pptx"

    export_html_deck(html_path, pdf_path=pdf_path, pptx_path=pptx_path)

    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert zipfile.is_zipfile(pptx_path)
    assert len(PdfReader(str(pdf_path)).pages) == deck.slide_count
    assert len(Presentation(str(pptx_path)).slides) == deck.slide_count
