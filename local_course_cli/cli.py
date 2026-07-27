"""Run foundation work or one chapter without changing the main workflow CLI."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
EXP_ROOT = REPO_ROOT / "exp"
CATALOG_ROOT = REPO_ROOT / "catalog"
ENV_PATH = REPO_ROOT / ".env"
MANIFEST_NAME = ".course_cli.json"
MANIFEST_VERSION = 1

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

FOUNDATION_FILES = (
    "result_instructional_goals.md",
    "result_resource_assessment.md",
    "result_target_audience.md",
    "result_syllabus_design.md",
    "result_assessment_planning.md",
    "result_final_exam_project.md",
    "result_presentation_design.md",
)
CHAPTER_SOURCE_FILES = ("slides.tex", "script.md", "assessment.md")
FRONTEND_CHAPTER_FILES = (
    "html/slides.html",
    "slides-html.pdf",
    "slides-html.pptx",
    "frontend-slides-manifest.json",
)
REQUIRED_CATALOG_SECTIONS = (
    "student_profile",
    "instructor_preferences",
    "course_structure",
    "assessment_design",
    "teaching_constraints",
    "institutional_requirements",
    "prior_feedback",
)


class CliError(RuntimeError):
    """A user-facing CLI error."""


@dataclass(frozen=True)
class CourseConfig:
    """Configuration needed to reconstruct an ADDIE course run."""

    version: int
    course_id: str
    course_name: str
    model: str
    catalog: str | None
    seed: int | None
    temperature: float | None


def load_dotenv(path: Path, environ: dict[str, str] | None = None) -> None:
    """Load a small, conventional subset of dotenv syntax without overriding env."""
    target = os.environ if environ is None else environ
    if not path.is_file():
        return

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise CliError(f"Invalid .env entry at {path}:{line_number}")

        key, value = line.split("=", 1)
        key = key.strip()
        if not ENV_KEY.fullmatch(key):
            raise CliError(f"Invalid .env key at {path}:{line_number}")

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        target.setdefault(key, value)


def validate_safe_name(value: str, label: str) -> str:
    if not SAFE_NAME.fullmatch(value):
        raise CliError(
            f"Invalid {label} {value!r}. Use letters, numbers, '.', '_' or '-', "
            "and start with a letter or number."
        )
    return value


def course_dir(course_id: str) -> Path:
    return EXP_ROOT / validate_safe_name(course_id, "course ID")


def manifest_path(output_dir: Path) -> Path:
    return output_dir / MANIFEST_NAME


def _is_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _expect_type(
    data: Mapping[str, Any],
    key: str,
    expected: type | tuple[type, ...],
    manifest: Path,
) -> Any:
    value = data.get(key)
    if not isinstance(value, expected) or isinstance(value, bool):
        expected_name = (
            "/".join(item.__name__ for item in expected)
            if isinstance(expected, tuple)
            else expected.__name__
        )
        raise CliError(
            f"Malformed manifest {manifest}: {key!r} must be {expected_name}."
        )
    return value


def load_manifest(output_dir: Path) -> CourseConfig:
    path = manifest_path(output_dir)
    if not path.is_file():
        raise CliError(
            f"No course manifest found at {path}. Run the foundation command first."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"Cannot read course manifest {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CliError(f"Malformed manifest {path}: expected a JSON object.")

    version = _expect_type(data, "version", int, path)
    course_id_value = _expect_type(data, "course_id", str, path)
    course_name = _expect_type(data, "course_name", str, path)
    model = _expect_type(data, "model", str, path)
    catalog = data.get("catalog")
    seed = data.get("seed")
    temperature = data.get("temperature")

    if version != MANIFEST_VERSION:
        raise CliError(
            f"Unsupported manifest version {version} in {path}; "
            f"expected {MANIFEST_VERSION}."
        )
    validate_safe_name(course_id_value, "course ID")
    if course_id_value != output_dir.name:
        raise CliError(
            f"Manifest course ID {course_id_value!r} does not match directory "
            f"{output_dir.name!r}."
        )
    if not course_name.strip() or not model.strip():
        raise CliError(f"Malformed manifest {path}: course_name/model cannot be empty.")
    if catalog is not None and not isinstance(catalog, str):
        raise CliError(f"Malformed manifest {path}: 'catalog' must be a string or null.")
    if catalog is not None:
        validate_safe_name(catalog, "catalog name")
    if seed is not None and (not isinstance(seed, int) or isinstance(seed, bool)):
        raise CliError(f"Malformed manifest {path}: 'seed' must be an integer or null.")
    if temperature is not None and (
        not isinstance(temperature, (int, float)) or isinstance(temperature, bool)
    ):
        raise CliError(
            f"Malformed manifest {path}: 'temperature' must be a number or null."
        )

    return CourseConfig(
        version=version,
        course_id=course_id_value,
        course_name=course_name,
        model=model,
        catalog=catalog,
        seed=seed,
        temperature=float(temperature) if temperature is not None else None,
    )


def write_manifest(output_dir: Path, config: CourseConfig) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_path(output_dir)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def load_catalog(catalog_name: str | None) -> dict[str, Any] | None:
    if catalog_name is None:
        return None
    validate_safe_name(catalog_name, "catalog name")
    path = CATALOG_ROOT / f"{catalog_name}.json"
    if not path.is_file():
        raise CliError(
            f"Catalog {catalog_name!r} does not exist at {path}. "
            "Pass the catalog name without '.json'."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"Cannot read catalog {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CliError(f"Catalog {path} must contain a JSON object.")
    missing = [section for section in REQUIRED_CATALOG_SECTIONS if section not in data]
    if missing:
        raise CliError(f"Catalog {path} is missing sections: {', '.join(missing)}")
    return data


def require_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise CliError(
            f"OPENAI_API_KEY is not set. Add it to {ENV_PATH} or export it "
            "before running foundation/chapter generation."
        )


def validate_foundation(output_dir: Path) -> list[dict[str, str]]:
    presentation_result = output_dir / "result_presentation_design.md"
    if not _is_nonempty_file(presentation_result):
        from src.html_slides import FrontendSlidesError
        from src.html_slides_style import STYLE_FILENAME, STYLE_SOURCE_FILENAME
        from src.html_slides_style import (
            load_course_slide_style,
            write_presentation_design_result,
        )

        if all(
            _is_nonempty_file(output_dir / name)
            for name in (STYLE_FILENAME, STYLE_SOURCE_FILENAME)
        ):
            try:
                style = load_course_slide_style(output_dir)
                write_presentation_design_result(output_dir, style)
            except FrontendSlidesError:
                # The standard missing-artifact error below remains the clearest
                # validation result for an unrecoverable legacy foundation.
                pass

    missing = [
        name for name in FOUNDATION_FILES if not _is_nonempty_file(output_dir / name)
    ]
    if missing:
        raise CliError(
            f"Course foundation is incomplete in {output_dir}. Missing or empty: "
            f"{', '.join(missing)}. Run the foundation command to resume it."
        )

    chapters_path = output_dir / "processed_chapters.json"
    if not _is_nonempty_file(chapters_path):
        raise CliError(
            f"Course foundation is incomplete: {chapters_path} is missing or empty."
        )
    try:
        chapters = json.loads(chapters_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"Cannot read processed chapters {chapters_path}: {exc}") from exc
    if not isinstance(chapters, list) or not chapters:
        raise CliError(f"{chapters_path} must contain at least one chapter.")
    for index, chapter in enumerate(chapters, start=1):
        if (
            not isinstance(chapter, dict)
            or not isinstance(chapter.get("title"), str)
            or not chapter["title"].strip()
            or not isinstance(chapter.get("description"), str)
            or not chapter["description"].strip()
        ):
            raise CliError(
                f"Malformed chapter {index} in {chapters_path}; "
                "each chapter needs nonempty title and description strings."
            )
    return chapters


def build_runner(
    config: CourseConfig,
    output_dir: Path,
    resume: bool = True,
    reselect_presentation_design: bool = False,
    image_generation_config: Any | None = None,
) -> Any:
    """Construct the existing workflow runner. Kept as a seam for tests."""
    from src.ADDIE import ADDIE, ADDIERunner

    catalog_data = load_catalog(config.catalog)
    addie = ADDIE(
        course_name=config.course_name,
        model_name=config.model,
        catalog=catalog_data is not None,
        data_catalog=catalog_data or {},
        seed=config.seed,
        temperature=config.temperature,
        resume=resume,
    )
    return ADDIERunner(
        addie,
        output_dir=str(output_dir),
        resume=resume,
        reselect_presentation_design=reselect_presentation_design,
        image_generation_config=image_generation_config,
    )


def _new_or_existing_config(args: argparse.Namespace, output_dir: Path) -> CourseConfig:
    path = manifest_path(output_dir)
    existing = load_manifest(output_dir) if path.exists() else None

    if existing is None and output_dir.exists() and any(output_dir.iterdir()):
        raise CliError(
            f"{output_dir} already contains files but has no {MANIFEST_NAME}. "
            "Choose a new course ID to avoid mixing unrelated outputs."
        )

    config = CourseConfig(
        version=MANIFEST_VERSION,
        course_id=args.course_id,
        course_name=args.course_name.strip(),
        model=args.model or (existing.model if existing else "gpt-4o-mini"),
        catalog=args.catalog if args.catalog is not None else (
            existing.catalog if existing else None
        ),
        seed=args.seed if args.seed is not None else (existing.seed if existing else None),
        temperature=(
            args.temperature
            if args.temperature is not None
            else (existing.temperature if existing else None)
        ),
    )
    if not config.course_name:
        raise CliError("Course name cannot be empty.")
    if not config.model.strip():
        raise CliError("Model name cannot be empty.")
    if config.catalog is not None:
        validate_safe_name(config.catalog, "catalog name")

    if existing is not None and config != existing:
        differences = [
            key
            for key, value in asdict(config).items()
            if value != asdict(existing).get(key)
        ]
        raise CliError(
            f"Course configuration does not match {path}. Changed fields: "
            f"{', '.join(differences)}. Use a new course ID for different settings."
        )
    return config


def run_foundation(args: argparse.Namespace) -> int:
    require_api_key()
    validate_safe_name(args.course_id, "course ID")
    output_dir = course_dir(args.course_id)
    config = _new_or_existing_config(args, output_dir)
    load_catalog(config.catalog)
    write_manifest(output_dir, config)
    reselect = getattr(args, "reselect_presentation_design", False)
    from src.html_slides_img import (
        configured_for_invocation,
        load_image_generation_config,
        style_has_explicit_image_guidance,
        write_image_generation_config,
    )

    enable_images = bool(getattr(args, "enable_image_generation", False))
    replace_images = bool(getattr(args, "replace_images", False))
    if (
        (enable_images or replace_images)
        and (output_dir / "course_slide_style.json").is_file()
        and not style_has_explicit_image_guidance(output_dir)
        and not reselect
    ):
        raise CliError(
            "This legacy course has no image guidance. Rerun foundation using "
            "--reselect-presentation-design --enable-image-generation."
        )
    try:
        stored_images = load_image_generation_config(output_dir)
        max_images = getattr(args, "max_images_per_chapter", None)
        if max_images is not None:
            stored_images = replace(
                stored_images,
                max_images_per_chapter=max_images,
                ai_decides_image_count=False,
            ).validated()
        elif bool(getattr(args, "ai_decides_image_count", False)):
            stored_images = replace(
                stored_images,
                ai_decides_image_count=True,
            ).validated()
        image_config = configured_for_invocation(
            stored_images,
            enable=enable_images,
            replace_images=replace_images,
        )
        write_image_generation_config(output_dir, image_config)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    if reselect:
        preflight_existing_chapters_for_style_change(output_dir)

    runner = build_runner(
        config,
        output_dir,
        resume=True,
        reselect_presentation_design=reselect,
        image_generation_config=image_config,
    )
    runner.setup()
    runner.run_foundation_deliberations()
    chapters = validate_foundation(output_dir)
    if (
        reselect
        or enable_images
        or replace_images
        or max_images is not None
        or bool(getattr(args, "ai_decides_image_count", False))
    ):
        refinalize_existing_chapters(output_dir, runner, force=True)
    assert_course_style_consistency(output_dir)

    print(f"\nFoundation complete for {config.course_name!r}.")
    print(f"Course directory: {output_dir}")
    print(f"Available chapters: {len(chapters)}")
    print(
        f"Next: ./local_course_cli/course chapters --course-id {config.course_id}"
    )
    return 0


def run_chapters(args: argparse.Namespace) -> int:
    output_dir = course_dir(args.course_id)
    config = load_manifest(output_dir)
    chapters = validate_foundation(output_dir)

    print(f"{config.course_name} ({config.course_id})")
    for index, chapter in enumerate(chapters, start=1):
        print(f"{index:>3}. {chapter['title']}")
    return 0


def compile_chapter(chapter_dir: Path) -> None:
    """Compile just one chapter directory using the existing compiler."""
    from src.compile import LaTeXCompiler

    LaTeXCompiler(str(chapter_dir)).compile_all()


def chapter_statistics_name(chapter_number: int) -> str:
    return f"statistics_slides_chapter_{chapter_number}.json"


def validate_chapter_outputs(chapter_dir: Path, chapter_number: int) -> None:
    required = (
        *CHAPTER_SOURCE_FILES,
        "slides.pdf",
        *FRONTEND_CHAPTER_FILES,
        chapter_statistics_name(chapter_number),
    )
    missing = [name for name in required if not _is_nonempty_file(chapter_dir / name)]
    if missing:
        raise CliError(
            f"Chapter {chapter_number} did not finish successfully. Missing or empty: "
            f"{', '.join(missing)}. Generated sources and checkpoints were preserved."
        )
    runtime = chapter_dir / "html" / "assets" / "mathjax" / "tex-svg.js"
    if not _is_nonempty_file(runtime):
        raise CliError(
            f"Chapter {chapter_number} is missing its offline frontend runtime: {runtime}"
        )


def repair_chapter_speaker_notes(chapter_dir: Path) -> Path:
    """Replace only script.md using the exact parsed Beamer slide order."""
    from src.html_slides import parse_beamer
    from src.html_slides import repair_speaker_notes_markdown

    tex_path = chapter_dir / "slides.tex"
    if not _is_nonempty_file(tex_path):
        raise CliError(f"Cannot repair speaker notes without {tex_path}.")
    deck = parse_beamer(tex_path)
    script_path = chapter_dir / "script.md"
    repaired = repair_speaker_notes_markdown(
        deck,
        document_title=f"Slides Script: {deck.title}",
    )
    temporary = script_path.with_suffix(".md.tmp")
    temporary.write_text(repaired, encoding="utf-8")
    os.replace(temporary, script_path)
    return script_path


def completed_chapter_source_dirs(output_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in output_dir.glob("chapter_*")
            if path.is_dir()
            and all(_is_nonempty_file(path / name) for name in CHAPTER_SOURCE_FILES)
        ),
        key=lambda path: (
            int(path.name.removeprefix("chapter_"))
            if path.name.removeprefix("chapter_").isdigit()
            else sys.maxsize,
            path.name,
        ),
    )


def preflight_existing_chapters_for_style_change(output_dir: Path) -> None:
    """Reject a style switch before selection if legacy notes are ambiguous."""
    from src.html_slides import parse_beamer
    from src.html_slides import FrontendSlidesError
    from src.html_slides import upgrade_legacy_script

    for chapter_dir in completed_chapter_source_dirs(output_dir):
        try:
            deck = parse_beamer(chapter_dir / "slides.tex")
            upgrade_legacy_script(
                deck, (chapter_dir / "script.md").read_text(encoding="utf-8")
            )
        except (OSError, FrontendSlidesError) as exc:
            raise CliError(
                f"Cannot reselect presentation design while {chapter_dir.name} has "
                "uncorrelated speaker notes. Run the chapter command with "
                f"--number {chapter_dir.name.removeprefix('chapter_')} --repair-notes "
                f"first. Details: {exc}"
            ) from exc


def refinalize_existing_chapters(
    output_dir: Path,
    runner: Any | None = None,
    *,
    force: bool = False,
) -> None:
    """Bring every completed chapter onto the canonical course presentation."""
    from src.html_slides import FrontendSlidesError
    from src.html_slides import MANIFEST_SCHEMA_VERSION, finalize_chapter
    from src.html_slides_style import STYLE_FILENAME, sha256_file

    for chapter_dir in completed_chapter_source_dirs(output_dir):
        manifest_path = chapter_dir / "frontend-slides-manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        expected = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "source_sha256": sha256_file(chapter_dir / "slides.tex"),
            "script_sha256": sha256_file(chapter_dir / "script.md"),
            "style_sha256": sha256_file(output_dir / STYLE_FILENAME),
        }
        artifacts_complete = all(
            _is_nonempty_file(chapter_dir / name)
            for name in FRONTEND_CHAPTER_FILES
        ) and _is_nonempty_file(
            chapter_dir / "html" / "assets" / "mathjax" / "tex-svg.js"
        )
        if (
            not force
            and isinstance(manifest, dict)
            and artifacts_complete
            and all(manifest.get(key) == value for key, value in expected.items())
        ):
            continue
        try:
            if runner is not None:
                runner.finalize_chapter(str(chapter_dir))
            else:
                finalize_chapter(output_dir, chapter_dir)
        except FrontendSlidesError as exc:
            raise CliError(
                f"Course-wide frontend reconciliation failed for {chapter_dir.name}: {exc}"
            ) from exc


def assert_course_style_consistency(output_dir: Path) -> None:
    """Require all completed frontend manifests to use the root style hash."""
    from src.html_slides_style import STYLE_FILENAME, sha256_file

    style_path = output_dir / STYLE_FILENAME
    expected_hash = sha256_file(style_path)
    mismatched: list[str] = []
    for chapter_dir in completed_chapter_source_dirs(output_dir):
        manifest = chapter_dir / "frontend-slides-manifest.json"
        if not _is_nonempty_file(manifest):
            mismatched.append(chapter_dir.name)
            continue
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mismatched.append(chapter_dir.name)
            continue
        if not isinstance(payload, dict) or payload.get("style_sha256") != expected_hash:
            mismatched.append(chapter_dir.name)
    if mismatched:
        raise CliError(
            "Completed chapters do not share the canonical presentation design: "
            + ", ".join(mismatched)
        )


def run_chapter(args: argparse.Namespace) -> int:
    require_api_key()
    output_dir = course_dir(args.course_id)
    config = load_manifest(output_dir)
    disk_chapters = validate_foundation(output_dir)
    from src.html_slides_img import (
        configured_for_invocation,
        load_image_generation_config,
        style_has_explicit_image_guidance,
        write_image_generation_config,
    )

    enable_images = bool(getattr(args, "enable_image_generation", False))
    replace_images = bool(getattr(args, "replace_images", False))
    if (
        (enable_images or replace_images)
        and not style_has_explicit_image_guidance(output_dir)
    ):
        raise CliError(
            "This legacy course has no image guidance. Rerun foundation using "
            "--reselect-presentation-design --enable-image-generation."
        )
    try:
        stored_images = load_image_generation_config(output_dir)
        image_config = configured_for_invocation(
            stored_images,
            enable=enable_images,
            replace_images=replace_images,
            max_images_override=getattr(args, "max_images_per_chapter", None),
            ai_decides_image_count=(
                True
                if bool(getattr(args, "ai_decides_image_count", False))
                else None
            ),
        )
        if (
            enable_images
            or replace_images
            or bool(getattr(args, "ai_decides_image_count", False))
        ):
            write_image_generation_config(output_dir, image_config)
    except ValueError as exc:
        raise CliError(str(exc)) from exc

    if args.number < 1 or args.number > len(disk_chapters):
        raise CliError(
            f"Chapter {args.number} is out of range for {config.course_name!r}. "
            f"Choose a chapter from 1 to {len(disk_chapters)}."
        )
    from src.html_slides_style import STYLE_FILENAME, STYLE_SOURCE_FILENAME

    missing_style = [
        name
        for name in (STYLE_FILENAME, STYLE_SOURCE_FILENAME)
        if not _is_nonempty_file(output_dir / name)
    ]
    if missing_style:
        raise CliError(
            "Course slide style is missing. Rerun the foundation command to create: "
            + ", ".join(missing_style)
        )

    runner = build_runner(
        config,
        output_dir,
        resume=True,
        image_generation_config=image_config,
    )
    runner.setup()
    # Validation above guarantees every artifact exists, so this reloads them
    # through the workflow's supported resume path without making model calls.
    runner.run_foundation_deliberations()
    if len(runner.chapters) != len(disk_chapters):
        raise CliError(
            "The workflow loaded a different chapter count than processed_chapters.json."
        )

    chapter_index = args.number - 1
    chapter = runner.chapters[chapter_index]
    chapter_dir_path = output_dir / f"chapter_{args.number}"
    sources_complete = all(
        _is_nonempty_file(chapter_dir_path / name)
        for name in CHAPTER_SOURCE_FILES
    )

    if sources_complete:
        print(
            f"Chapter {args.number} source artifacts already exist; "
            "skipping all chapter model calls."
        )
    else:
        chapter_dir_path.mkdir(parents=True, exist_ok=True)
        runner._run_slides_generation_with_retry(
            chapter, chapter_index, str(chapter_dir_path)
        )

    if getattr(args, "repair_notes", False):
        repaired = repair_chapter_speaker_notes(chapter_dir_path)
        print(f"Repaired speaker-note correlation: {repaired}")

    try:
        runner.finalize_chapter(str(chapter_dir_path))
    except Exception as exc:
        raise CliError(f"Chapter frontend finalization failed: {exc}") from exc

    validate_chapter_outputs(chapter_dir_path, args.number)
    if hasattr(runner, "image_generation_config"):
        runner.image_generation_config = replace(
            runner.image_generation_config,
            replace_images=False,
        )
    refinalize_existing_chapters(output_dir, runner)
    assert_course_style_consistency(output_dir)
    print(f"\nChapter {args.number} complete: {chapter['title']}")
    print(f"Chapter directory: {chapter_dir_path}")
    print(
        "Artifacts: slides.tex, slides.pdf, html/slides.html, "
        "slides-html.pdf, slides-html.pptx"
    )
    return 0


def _command_version(command: Sequence[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    text = (result.stdout or result.stderr).strip().splitlines()
    detail = text[0] if text else f"exit {result.returncode}"
    return result.returncode == 0, detail


def _npm_global_package(package: str) -> tuple[bool, str]:
    ok, root = _command_version(("npm", "root", "-g"))
    if not ok:
        return False, root
    package_path = Path(root.strip()) / package
    return package_path.is_dir(), str(package_path)


def run_doctor(args: argparse.Namespace) -> int:
    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "Python 3.11+",
            sys.version_info >= (3, 11),
            f"{sys.version.split()[0]} at {sys.executable}",
        )
    )
    checks.append(
        (
            "OPENAI_API_KEY",
            bool(os.environ.get("OPENAI_API_KEY", "").strip()),
            "loaded (value hidden)"
            if os.environ.get("OPENAI_API_KEY", "").strip()
            else f"missing from environment and {ENV_PATH}",
        )
    )

    for module in ("openai", "pylatexenc", "playwright", "pptx", "src.ADDIE"):
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - depends on local install
            checks.append((f"Python import {module}", False, str(exc)))
        else:
            checks.append((f"Python import {module}", True, "available"))

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except Exception as exc:
        checks.append(("Playwright Chromium", False, str(exc)))
    else:
        checks.append(("Playwright Chromium", True, "launch succeeded"))

    for label, command in (
        ("uv", ("uv", "--version")),
        ("Node.js", ("node", "--version")),
        ("npm", ("npm", "--version")),
        ("pdflatex", ("pdflatex", "--version")),
    ):
        ok, detail = _command_version(command)
        checks.append((label, ok, detail))

    for label, latex_file in (
        ("LaTeX Beamer", "beamer.cls"),
        ("LaTeX TikZ", "tikz.sty"),
    ):
        ok, detail = _command_version(("kpsewhich", latex_file))
        checks.append((label, ok and bool(detail.strip()), detail or "not found"))

    for package in ("pptxgenjs", "react-icons", "react", "react-dom", "sharp"):
        ok, detail = _npm_global_package(package)
        checks.append((f"npm package {package}", ok, detail))

    for catalog_name in ("default_catalog", "mwe_catalog"):
        try:
            load_catalog(catalog_name)
        except CliError as exc:
            checks.append((f"Catalog {catalog_name}", False, str(exc)))
        else:
            checks.append((f"Catalog {catalog_name}", True, "valid JSON schema"))

    if args.live_openai:
        try:
            require_api_key()
            from openai import OpenAI

            OpenAI(api_key=os.environ["OPENAI_API_KEY"]).models.list()
        except Exception as exc:  # pragma: no cover - live network check
            checks.append(("OpenAI connectivity", False, str(exc)))
        else:
            checks.append(
                ("OpenAI connectivity", True, "authenticated; no generation requested")
            )

    failed = False
    print("Local course CLI diagnostics")
    for label, ok, detail in checks:
        failed = failed or not ok
        print(f"[{'ok' if ok else 'FAIL'}] {label}: {detail}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="./local_course_cli/course",
        description=(
            "Run only the foundation phase or one selected chapter of "
            "Instructional Agents."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    foundation = subparsers.add_parser(
        "foundation",
        help="Create or safely resume foundation documents only.",
    )
    foundation.add_argument("course_name", help="Human-readable course name.")
    foundation.add_argument("--course-id", required=True, help="Safe exp/ directory ID.")
    foundation.add_argument(
        "--catalog",
        default=None,
        help="Catalog filename without .json; omit for automatic/no-catalog mode.",
    )
    foundation.add_argument(
        "--model",
        default=None,
        help="OpenAI model (new-course default: gpt-4o-mini).",
    )
    foundation.add_argument("--seed", type=int, default=None)
    foundation.add_argument("--temperature", type=float, default=None)
    foundation.add_argument(
        "--reselect-presentation-design",
        action="store_true",
        help=(
            "Explicitly choose a new course-wide presentation design and rebuild "
            "eligible chapter frontend artifacts."
        ),
    )
    foundation.add_argument(
        "--enable-image-generation",
        action="store_true",
        help="Persist opt-in to dynamic frontend slide image generation.",
    )
    foundation.add_argument(
        "--replace-images",
        action="store_true",
        help="Replace images for all completed chapters; implies enablement.",
    )
    foundation_image_count = foundation.add_mutually_exclusive_group()
    foundation_image_count.add_argument(
        "--max-images-per-chapter",
        type=int,
        choices=range(0, 4),
        default=None,
        metavar="0-3",
        help="Persist the experiment default image cap.",
    )
    foundation_image_count.add_argument(
        "--ai-decides-image-count",
        action="store_true",
        help=(
            "Remove the numeric chapter cap and let the placement AI choose "
            "every strong eligible image opportunity."
        ),
    )
    foundation.set_defaults(handler=run_foundation)

    chapters = subparsers.add_parser(
        "chapters", help="List chapter numbers from a completed foundation."
    )
    chapters.add_argument("--course-id", required=True)
    chapters.set_defaults(handler=run_chapters)

    chapter = subparsers.add_parser(
        "chapter", help="Create or safely resume exactly one chapter."
    )
    chapter.add_argument("--course-id", required=True)
    chapter.add_argument("--number", required=True, type=int)
    chapter.add_argument(
        "--repair-notes",
        action="store_true",
        help=(
            "Replace only script.md with notes derived from the exact saved "
            "slides.tex order before frontend finalization."
        ),
    )
    chapter.add_argument(
        "--enable-image-generation",
        action="store_true",
        help="Persist image generation and apply it to this chapter.",
    )
    chapter.add_argument(
        "--replace-images",
        action="store_true",
        help="Replace generated images for this chapter only; implies enablement.",
    )
    chapter_image_count = chapter.add_mutually_exclusive_group()
    chapter_image_count.add_argument(
        "--max-images-per-chapter",
        type=int,
        choices=range(0, 4),
        default=None,
        metavar="0-3",
        help="Tighten the image cap for this invocation without persisting it.",
    )
    chapter_image_count.add_argument(
        "--ai-decides-image-count",
        action="store_true",
        help=(
            "Remove the numeric cap for this and future chapters and let the "
            "placement AI choose every strong eligible image opportunity."
        ),
    )
    chapter.set_defaults(handler=run_chapter)

    doctor = subparsers.add_parser(
        "doctor", help="Check the isolated Python and host toolchain."
    )
    doctor.add_argument(
        "--live-openai",
        action="store_true",
        help="Authenticate with OpenAI using models.list(); does not generate content.",
    )
    doctor.set_defaults(handler=run_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        load_dotenv(ENV_PATH)
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except CliError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nInterrupted. Existing outputs/checkpoints were preserved.", file=sys.stderr)
        return 130
