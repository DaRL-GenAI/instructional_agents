"""Tests for the isolated local course-phase CLI."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from local_course_cli import cli
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
    sha256_file,
    sha256_text,
    write_course_style,
)


def make_config(
    course_id: str = "test-course",
    *,
    course_name: str = "Test Course",
    model: str = "gpt-4o-mini",
    catalog: str | None = None,
    seed: int | None = None,
    temperature: float | None = None,
) -> cli.CourseConfig:
    return cli.CourseConfig(
        version=cli.MANIFEST_VERSION,
        course_id=course_id,
        course_name=course_name,
        model=model,
        catalog=catalog,
        seed=seed,
        temperature=temperature,
    )


def chapters(count: int = 3) -> list[dict[str, str]]:
    return [
        {
            "title": f"Chapter {index}: Topic {index}",
            "description": f"Description for chapter {index}.",
        }
        for index in range(1, count + 1)
    ]


def write_style(output_dir: Path) -> None:
    selected_style = SelectedStyle("bold_template", "cobalt-grid", "Cobalt Grid")
    source = selected_asset_text(selected_style)
    _, inventory_hash = build_style_inventory()
    style = CourseSlideStyle(
        schema_version=1,
        asset_version=ASSET_VERSION,
        selected_style=selected_style,
        presentation_method=PresentationMethod(
            "progressive concepts",
            "measured",
            "medium",
            "worked examples",
            ["hero", "split", "top"],
            "guided questions",
        ),
        ta_guidance="Use a clear cobalt hierarchy.",
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


def write_foundation(
    output_dir: Path, chapter_count: int = 3, *, with_style: bool = True
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in cli.FOUNDATION_FILES:
        (output_dir / name).write_text(f"content for {name}\n", encoding="utf-8")
    (output_dir / "processed_chapters.json").write_text(
        json.dumps(chapters(chapter_count)), encoding="utf-8"
    )
    if with_style:
        write_style(output_dir)


def write_chapter_sources(output_dir: Path, number: int, *, pdf: bool = False) -> Path:
    target = output_dir / f"chapter_{number}"
    target.mkdir(parents=True, exist_ok=True)
    for name in cli.CHAPTER_SOURCE_FILES:
        (target / name).write_text(f"chapter {number} {name}\n", encoding="utf-8")
    (target / cli.chapter_statistics_name(number)).write_text(
        '{"tokens": 1}\n', encoding="utf-8"
    )
    if pdf:
        (target / "slides.pdf").write_bytes(b"%PDF-test")
    return target


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    exp_root = tmp_path / "exp"
    catalog_root = tmp_path / "catalog"
    catalog_root.mkdir()
    monkeypatch.setattr(cli, "EXP_ROOT", exp_root)
    monkeypatch.setattr(cli, "CATALOG_ROOT", catalog_root)
    monkeypatch.setattr(cli, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    return exp_root


class FakeRunner:
    def __init__(self, output_dir: Path, chapter_count: int = 3):
        self.output_dir = output_dir
        self.chapters = chapters(chapter_count)
        self.setup_calls = 0
        self.foundation_calls = 0
        self.chapter_calls: list[tuple[dict[str, str], int, str]] = []
        self.write_foundation_on_run = False
        self.saw_checkpoint = False
        self.finalize_calls: list[Path] = []

    def setup(self) -> None:
        self.setup_calls += 1

    def run_foundation_deliberations(self) -> None:
        self.foundation_calls += 1
        if self.write_foundation_on_run:
            write_foundation(self.output_dir, len(self.chapters))

    def _run_slides_generation_with_retry(
        self, chapter: dict[str, str], chapter_index: int, chapter_dir: str
    ) -> None:
        target = Path(chapter_dir)
        self.saw_checkpoint = (target / "_checkpoint.json").is_file()
        self.chapter_calls.append((chapter, chapter_index, chapter_dir))
        number = chapter_index + 1
        write_chapter_sources(self.output_dir, number)

    def finalize_chapter(self, chapter_dir: str) -> None:
        target = Path(chapter_dir)
        self.finalize_calls.append(target)
        (target / "slides.pdf").write_bytes(b"%PDF-test")
        for name in cli.FRONTEND_CHAPTER_FILES:
            artifact = target / name
            artifact.parent.mkdir(parents=True, exist_ok=True)
            if name == "frontend-slides-manifest.json":
                artifact.write_text(
                    json.dumps(
                        {
                            "schema_version": 3,
                            "source_sha256": sha256_file(target / "slides.tex"),
                            "script_sha256": sha256_file(target / "script.md"),
                            "style_sha256": sha256_file(
                                self.output_dir / STYLE_FILENAME
                            ),
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                artifact.write_bytes(b"test artifact")
        runtime = target / "html" / "assets" / "mathjax"
        runtime.mkdir(parents=True, exist_ok=True)
        (runtime / "tex-svg.js").write_text("mathjax", encoding="utf-8")


def foundation_args(**overrides: object) -> Namespace:
    values = {
        "course_name": "Test Course",
        "course_id": "test-course",
        "catalog": None,
        "model": None,
        "seed": None,
        "temperature": None,
        "reselect_presentation_design": False,
    }
    values.update(overrides)
    return Namespace(**values)


def test_load_dotenv_preserves_exported_value(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY='from-file'\nexport API_PORT=9000\n", encoding="utf-8"
    )
    environ = {"OPENAI_API_KEY": "already-exported"}

    cli.load_dotenv(env_file, environ)

    assert environ["OPENAI_API_KEY"] == "already-exported"
    assert environ["API_PORT"] == "9000"


@pytest.mark.parametrize("course_id", ("../escape", "/absolute", "has space", ""))
def test_invalid_course_ids_are_rejected(course_id: str) -> None:
    with pytest.raises(cli.CliError, match="Invalid course ID"):
        cli.course_dir(course_id)


def test_missing_and_malformed_catalogs_are_rejected(
    isolated_paths: Path,
) -> None:
    with pytest.raises(cli.CliError, match="does not exist"):
        cli.load_catalog("missing")

    catalog = cli.CATALOG_ROOT / "broken.json"
    catalog.write_text('{"student_profile": {}}', encoding="utf-8")
    with pytest.raises(cli.CliError, match="missing sections"):
        cli.load_catalog("broken")


def test_malformed_manifest_is_rejected(isolated_paths: Path) -> None:
    output_dir = isolated_paths / "test-course"
    output_dir.mkdir(parents=True)
    (output_dir / cli.MANIFEST_NAME).write_text(
        '{"version": 1, "course_id": "test-course"}', encoding="utf-8"
    )

    with pytest.raises(cli.CliError, match="course_name"):
        cli.load_manifest(output_dir)


def test_foundation_runs_only_foundation_phase(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    runner = FakeRunner(output_dir, chapter_count=13)
    runner.write_foundation_on_run = True
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)

    assert cli.run_foundation(foundation_args()) == 0

    assert runner.setup_calls == 1
    assert runner.foundation_calls == 1
    assert not list(output_dir.glob("chapter_*"))
    assert cli.load_manifest(output_dir).course_name == "Test Course"
    assert len(cli.validate_foundation(output_dir)) == 13


def test_foundation_rerun_inherits_existing_optional_settings(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(
        output_dir,
        make_config(model="gpt-4o", seed=42, temperature=0.2),
    )
    write_foundation(output_dir)
    runner = FakeRunner(output_dir)
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)

    assert cli.run_foundation(foundation_args()) == 0
    assert cli.load_manifest(output_dir).model == "gpt-4o"
    assert cli.load_manifest(output_dir).seed == 42


def test_foundation_plumbs_explicit_presentation_reselection(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    runner = FakeRunner(output_dir)
    runner.write_foundation_on_run = True
    seen: dict[str, object] = {}

    def fake_build_runner(*_args, **kwargs):
        seen.update(kwargs)
        return runner

    monkeypatch.setattr(cli, "build_runner", fake_build_runner)

    assert cli.run_foundation(
        foundation_args(reselect_presentation_design=True)
    ) == 0
    assert seen["reselect_presentation_design"] is True


def test_foundation_manifest_mismatch_is_rejected(isolated_paths: Path) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())

    with pytest.raises(cli.CliError, match="Changed fields: model"):
        cli.run_foundation(foundation_args(model="gpt-4o"))


def test_missing_foundation_artifact_is_rejected(isolated_paths: Path) -> None:
    output_dir = isolated_paths / "test-course"
    write_foundation(output_dir)
    (output_dir / cli.FOUNDATION_FILES[2]).unlink()

    with pytest.raises(cli.CliError, match=cli.FOUNDATION_FILES[2]):
        cli.validate_foundation(output_dir)


def test_legacy_foundation_backfills_presentation_design_without_model_calls(
    isolated_paths: Path,
) -> None:
    output_dir = isolated_paths / "test-course"
    write_foundation(output_dir)
    result_path = output_dir / "result_presentation_design.md"
    result_path.unlink()

    assert len(cli.validate_foundation(output_dir)) == 3
    result = result_path.read_text(encoding="utf-8")
    assert result.startswith("Presentation Design\n===================")
    assert "- Key: `cobalt-grid`" in result


def test_malformed_processed_chapters_is_rejected(isolated_paths: Path) -> None:
    output_dir = isolated_paths / "test-course"
    write_foundation(output_dir)
    (output_dir / "processed_chapters.json").write_text(
        '[{"title": "Missing description"}]', encoding="utf-8"
    )

    with pytest.raises(cli.CliError, match="Malformed chapter 1"):
        cli.validate_foundation(output_dir)


def test_chapter_13_maps_to_index_12_and_only_generates_that_chapter(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir, chapter_count=13)
    runner = FakeRunner(output_dir, chapter_count=13)
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)

    assert cli.run_chapter(Namespace(course_id="test-course", number=13)) == 0

    assert len(runner.chapter_calls) == 1
    assert runner.chapter_calls[0][1] == 12
    assert Path(runner.chapter_calls[0][2]).name == "chapter_13"
    assert not (output_dir / "chapter_1").exists()
    cli.validate_chapter_outputs(output_dir / "chapter_13", 13)


@pytest.mark.parametrize("number", (0, 4))
def test_out_of_range_chapter_is_rejected_before_runner_creation(
    isolated_paths: Path,
    monkeypatch: pytest.MonkeyPatch,
    number: int,
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir, chapter_count=3)
    monkeypatch.setattr(
        cli,
        "build_runner",
        lambda *_args, **_kwargs: pytest.fail("runner should not be created"),
    )

    with pytest.raises(cli.CliError, match="out of range"):
        cli.run_chapter(Namespace(course_id="test-course", number=number))


def test_completed_chapter_is_not_regenerated(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir)
    write_chapter_sources(output_dir, 2, pdf=True)
    runner = FakeRunner(output_dir)
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)
    monkeypatch.setattr(
        cli,
        "compile_chapter",
        lambda _target: pytest.fail("compiler should not run"),
    )

    assert cli.run_chapter(Namespace(course_id="test-course", number=2)) == 0
    assert runner.chapter_calls == []
    assert runner.finalize_calls == [output_dir / "chapter_2"]


def test_pdf_only_recompilation_makes_no_chapter_model_calls(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir)
    target = write_chapter_sources(output_dir, 2)
    runner = FakeRunner(output_dir)
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)

    assert cli.run_chapter(Namespace(course_id="test-course", number=2)) == 0
    assert runner.chapter_calls == []
    assert runner.finalize_calls == [target]


def test_partial_chapter_preserves_and_uses_checkpoint(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir)
    target = output_dir / "chapter_2"
    target.mkdir(parents=True)
    (target / "_checkpoint.json").write_text('{"version": 1}', encoding="utf-8")
    runner = FakeRunner(output_dir)
    monkeypatch.setattr(cli, "build_runner", lambda *_args, **_kwargs: runner)
    assert cli.run_chapter(Namespace(course_id="test-course", number=2)) == 0
    assert runner.saw_checkpoint is True
    assert len(runner.chapter_calls) == 1


def test_legacy_course_requires_foundation_style(
    isolated_paths: Path,
) -> None:
    output_dir = isolated_paths / "test-course"
    cli.write_manifest(output_dir, make_config())
    write_foundation(output_dir, with_style=False)

    with pytest.raises(cli.CliError, match="Rerun the foundation command"):
        cli.run_chapter(Namespace(course_id="test-course", number=1))


def test_main_returns_nonzero_for_invalid_course_id(
    isolated_paths: Path,
) -> None:
    result = cli.main(
        ["foundation", "Test Course", "--course-id", "../escape"]
    )
    assert result == 2
