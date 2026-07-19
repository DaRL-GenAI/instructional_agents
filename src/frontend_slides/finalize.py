from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.compile import LaTeXCompiler

from .assets import load_assets
from .beamer import parse_beamer
from .errors import FrontendSlidesError
from .export import export_html_deck
from .models import ChapterFrontendResult
from .render import render_course_presentation_html
from .runtime import offline_runtime_complete, prepare_offline_runtime
from .split import split_overloaded_slides, write_split_report
from .style import STYLE_FILENAME, sha256_file
from .style_workflow import load_course_slide_style
from .validation import (
    validate_html_contract,
    validate_offline_contract,
    validate_with_playwright,
)


MANIFEST_FILENAME = "frontend-slides-manifest.json"


def finalize_chapter(
    course_dir: Path | str,
    chapter_dir: Path | str,
) -> ChapterFrontendResult:
    """Compile LaTeX and deterministically create resumable offline frontend artifacts."""
    course_path = Path(course_dir)
    chapter_path = Path(chapter_dir)
    tex_path = chapter_path / "slides.tex"
    latex_pdf_path = chapter_path / "slides.pdf"
    html_path = chapter_path / "slides.html"
    html_pdf_path = chapter_path / "slides-html.pdf"
    html_pptx_path = chapter_path / "slides-html.pptx"
    manifest_path = chapter_path / MANIFEST_FILENAME
    split_report_path = chapter_path / "slide-splits.json"

    if not tex_path.is_file() or tex_path.stat().st_size == 0:
        raise FrontendSlidesError(f"Chapter LaTeX source is missing or empty: {tex_path}")
    style = load_course_slide_style(course_path)
    style_path = course_path / STYLE_FILENAME
    source_hash = sha256_file(tex_path)
    style_hash = sha256_file(style_path)
    previous = _read_manifest(manifest_path)
    source_matches = previous.get("source_sha256") == source_hash
    style_matches = previous.get("style_sha256") == style_hash
    inputs_match = source_matches and style_matches

    if not source_matches or not _nonempty(latex_pdf_path):
        try:
            LaTeXCompiler(str(chapter_path)).compile_one(tex_path)
        except Exception as exc:
            raise FrontendSlidesError(f"LaTeX PDF compilation failed: {exc}") from exc
    if not _nonempty(latex_pdf_path):
        raise FrontendSlidesError(f"LaTeX compilation did not produce {latex_pdf_path}.")

    runtime_ok = offline_runtime_complete(chapter_path, style)
    complete = all(
        _nonempty(path)
        for path in (
            html_path,
            html_pdf_path,
            html_pptx_path,
            manifest_path,
            split_report_path,
        )
    )
    if inputs_match and runtime_ok and complete:
        return ChapterFrontendResult(
            html_path=html_path,
            latex_pdf_path=latex_pdf_path,
            html_pdf_path=html_pdf_path,
            html_pptx_path=html_pptx_path,
            manifest_path=manifest_path,
            split_report_path=split_report_path,
            slide_count=int(previous.get("slide_count", 0)),
            skipped=True,
        )

    assets = load_assets()
    deck = parse_beamer(tex_path)
    original_frame_count = deck.slide_count
    deck, split_records = split_overloaded_slides(deck)

    html_stale = not inputs_match or not _nonempty(html_path) or not runtime_ok
    if html_stale:
        _, font_css = prepare_offline_runtime(chapter_path, style)
        html = render_course_presentation_html(
            deck,
            style,
            assets,
            font_css=font_css,
        )
        errors = validate_html_contract(html, deck.slide_count, assets.viewport_css)
        errors.extend(validate_offline_contract(html))
        if errors:
            raise FrontendSlidesError("; ".join(errors))
        html_temporary = chapter_path / "slides.tmp.html"
        try:
            html_temporary.write_text(html, encoding="utf-8")
            visual_errors = validate_with_playwright(
                html_temporary, deck.slide_count
            )
            if visual_errors:
                raise FrontendSlidesError("; ".join(visual_errors))
            html_temporary.replace(html_path)
        finally:
            if html_temporary.exists():
                html_temporary.unlink()
        write_split_report(
            split_records, deck, original_frame_count, chapter_path
        )
    elif not _nonempty(split_report_path):
        write_split_report(
            split_records, deck, original_frame_count, chapter_path
        )

    need_pdf = html_stale or not _nonempty(html_pdf_path)
    need_pptx = html_stale or not _nonempty(html_pptx_path)
    pdf_temporary = (
        chapter_path / "slides-html.tmp.pdf" if need_pdf else None
    )
    pptx_temporary = (
        chapter_path / "slides-html.tmp.pptx" if need_pptx else None
    )
    try:
        export_html_deck(
            html_path,
            pdf_path=pdf_temporary,
            pptx_path=pptx_temporary,
        )
        if pdf_temporary is not None:
            if not _nonempty(pdf_temporary):
                raise FrontendSlidesError("HTML PDF exporter produced no output.")
            pdf_temporary.replace(html_pdf_path)
        if pptx_temporary is not None:
            if not _nonempty(pptx_temporary):
                raise FrontendSlidesError("HTML PPTX exporter produced no output.")
            pptx_temporary.replace(html_pptx_path)
    except Exception as exc:
        # The exporters write complete files before returning. Preserve any
        # independently completed output even if the sibling export failed.
        if pdf_temporary is not None and _valid_pdf(pdf_temporary):
            pdf_temporary.replace(html_pdf_path)
        if pptx_temporary is not None and _valid_pptx(pptx_temporary):
            pptx_temporary.replace(html_pptx_path)
        raise FrontendSlidesError(
            f"Frontend export failed; successful artifacts were preserved: {exc}"
        ) from exc

    warnings = []
    if deck.unsupported_environments:
        warnings.append(
            "Unsupported LaTeX environments were preserved as source cards: "
            + ", ".join(deck.unsupported_environments)
        )
    manifest = {
        "schema_version": 1,
        "source": tex_path.name,
        "source_sha256": source_hash,
        "style_sha256": style_hash,
        "selected_style": asdict(style.selected_style),
        "original_frame_count": original_frame_count,
        "slide_count": deck.slide_count,
        "offline": True,
        "runtime": "frontend-assets",
        "split_report": split_report_path.name,
        "warnings": warnings,
        "artifacts": {
            "latex_pdf": latex_pdf_path.name,
            "html": html_path.name,
            "html_pdf": html_pdf_path.name,
            "html_pptx": html_pptx_path.name,
        },
        "artifact_sha256": {
            "latex_pdf": sha256_file(latex_pdf_path),
            "html": sha256_file(html_path),
            "html_pdf": sha256_file(html_pdf_path),
            "html_pptx": sha256_file(html_pptx_path),
        },
    }
    _atomic_write(
        manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return ChapterFrontendResult(
        html_path=html_path,
        latex_pdf_path=latex_pdf_path,
        html_pdf_path=html_pdf_path,
        html_pptx_path=html_pptx_path,
        manifest_path=manifest_path,
        split_report_path=split_report_path,
        slide_count=deck.slide_count,
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _valid_pdf(path: Path) -> bool:
    if not _nonempty(path):
        return False
    try:
        from PyPDF2 import PdfReader

        return len(PdfReader(str(path)).pages) > 0
    except Exception:
        return False


def _valid_pptx(path: Path) -> bool:
    if not _nonempty(path):
        return False
    try:
        from pptx import Presentation

        return len(Presentation(str(path)).slides) > 0
    except Exception:
        return False


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
