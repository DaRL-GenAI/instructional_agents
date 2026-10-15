"""Opt-in Carbon code-image rendering for frontend slide artifacts."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from src.slide_io import atomic_write as _atomic_write
from src.slide_io import valid_png_file as _valid_png


CODE_IMAGE_CONFIG_FILENAME = "course_code_images.json"
CODE_IMAGE_CONFIG_SCHEMA_VERSION = 1
CODE_IMAGE_PIPELINE_VERSION = "carbon-code-images-2026-07-v1"
CARBON_NOW_PACKAGE = "carbon-now-cli@2.1.0"

_LANGUAGE_EXTENSIONS = {
    "python": ".py",
    "r": ".r",
    "java": ".java",
    "c": ".c",
    "c++": ".cpp",
    "cpp": ".cpp",
    "javascript": ".js",
    "typescript": ".ts",
    "sql": ".sql",
    "bash": ".sh",
    "sh": ".sh",
    "matlab": ".m",
    "julia": ".jl",
}

_FIXED_SETTINGS: dict[str, object] = {
    "windowTheme": "none",
    "windowControls": False,
    "fontFamily": "Hack",
    "fontSize": "18px",
    "lineNumbers": False,
    "dropShadow": False,
    "paddingVertical": "16px",
    "paddingHorizontal": "16px",
    "exportSize": "2x",
    "type": "png",
    "watermark": False,
    "widthAdjustment": True,
}


@dataclass(frozen=True)
class CodeImageConfig:
    enabled: bool = False

    def validated(self) -> "CodeImageConfig":
        if not isinstance(self.enabled, bool):
            raise ValueError("Code-image enablement must be a boolean.")
        return self


@dataclass
class CodeImageResult:
    requested: bool = False
    code_blocks: int = 0
    unique_snippets: int = 0
    rendered: int = 0
    fallbacks: int = 0
    cache_hits: int = 0
    carbon_version: str | None = None
    install_attempted: bool = False
    install_succeeded: bool = False
    request_fingerprint: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not self.requested or self.code_blocks == 0 or self.fallbacks == 0

    @property
    def effective(self) -> bool:
        return self.rendered > 0

    def manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "enabled": self.requested,
                "effective": self.effective,
                "complete": self.complete,
                "pipeline_version": CODE_IMAGE_PIPELINE_VERSION,
                "package": CARBON_NOW_PACKAGE,
            }
        )
        return payload


def load_code_image_config(course_dir: Path | str) -> CodeImageConfig:
    path = Path(course_dir) / CODE_IMAGE_CONFIG_FILENAME
    if not path.is_file():
        return CodeImageConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("configuration must be a JSON object")
        unknown = sorted(set(raw) - {"schema_version", "enabled"})
        if unknown:
            raise ValueError(
                "unsupported code-image configuration fields: " + ", ".join(unknown)
            )
        if raw.get("schema_version") != CODE_IMAGE_CONFIG_SCHEMA_VERSION:
            raise ValueError("unsupported code-image configuration schema")
        return CodeImageConfig(enabled=raw.get("enabled", False)).validated()
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Cannot load {path}: {exc}") from exc


def write_code_image_config(
    course_dir: Path | str,
    config: CodeImageConfig,
) -> Path:
    config = config.validated()
    path = Path(course_dir) / CODE_IMAGE_CONFIG_FILENAME
    payload = {
        "schema_version": CODE_IMAGE_CONFIG_SCHEMA_VERSION,
        "enabled": config.enabled,
    }
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def configured_for_invocation(
    stored: CodeImageConfig,
    requested: bool | None,
) -> CodeImageConfig:
    stored = stored.validated()
    if requested is None:
        return stored
    return replace(stored, enabled=requested).validated()


def code_image_request_fingerprint(
    *,
    source_sha256: str,
    style_sha256: str,
    config: CodeImageConfig,
) -> str:
    payload = {
        "pipeline_version": CODE_IMAGE_PIPELINE_VERSION,
        "package": CARBON_NOW_PACKAGE,
        "source_sha256": source_sha256,
        "style_sha256": style_sha256,
        "enabled": config.validated().enabled,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def carbon_settings_for_theme(theme: dict[str, str]) -> dict[str, object]:
    settings = dict(_FIXED_SETTINGS)
    settings["theme"] = theme.get("carbon_theme", "nord")
    settings["backgroundColor"] = theme.get(
        "carbon_background", "rgba(0,0,0,0)"
    )
    return settings


def detect_carbon_version(binary: str | None = None) -> str | None:
    resolved = binary or shutil.which("carbon-now")
    if not resolved:
        return None
    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    lines = (completed.stdout or completed.stderr).strip().splitlines()
    return lines[0].strip() if lines else None


def carbon_cache_version_is_current(
    previous_version: object,
    installed_version: str | None,
) -> bool:
    """Require two known, equal versions before reusing Carbon output."""
    return (
        installed_version is not None
        and previous_version not in {None, "unknown"}
        and installed_version == previous_version
    )


def attach_code_images(
    deck: Any,
    theme: dict[str, str],
    cache_dir: Path,
    *,
    config: CodeImageConfig,
    request_fingerprint: str,
    install_timeout_seconds: int = 300,
    render_timeout_seconds: int = 120,
) -> CodeImageResult:
    config = config.validated()
    elements = [
        element
        for slide in deck.slides
        for element in _walk_code_elements(slide.elements)
    ]
    result = CodeImageResult(
        requested=config.enabled,
        code_blocks=len(elements),
        unique_snippets=len(
            {(element.text, element.language) for element in elements}
        ),
        request_fingerprint=request_fingerprint,
    )
    if not config.enabled or not elements:
        return result

    binary = shutil.which("carbon-now")
    if binary is None:
        result.install_attempted = True
        npm = shutil.which("npm")
        if npm is None:
            result.fallbacks = len(elements)
            result.warnings.append(
                "Code images were enabled, but npm is unavailable; "
                "code blocks fall back to styled <pre> rendering."
            )
            return result
        try:
            completed = subprocess.run(
                [npm, "install", "--global", CARBON_NOW_PACKAGE],
                capture_output=True,
                text=True,
                timeout=install_timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            result.fallbacks = len(elements)
            result.warnings.append(
                "Could not install carbon-now-cli; code blocks fall back to "
                f"styled <pre> rendering: {_brief_error(exc)}"
            )
            return result
        binary = shutil.which("carbon-now")
        result.install_succeeded = completed.returncode == 0 and binary is not None
        if not result.install_succeeded:
            result.fallbacks = len(elements)
            detail = _subprocess_detail(completed)
            result.warnings.append(
                "Could not install or locate carbon-now-cli; code blocks fall "
                f"back to styled <pre> rendering: {detail}"
            )
            return result

    result.carbon_version = detect_carbon_version(binary) or "unknown"
    settings = carbon_settings_for_theme(theme)
    rendered: dict[str, tuple[str | None, bool]] = {}
    for element in elements:
        key = _cache_key(
            element.text,
            element.language,
            settings,
            result.carbon_version,
        )
        if key not in rendered:
            rendered[key] = code_image_data_uri(
                element.text,
                element.language,
                settings,
                cache_dir,
                binary=binary,
                carbon_version=result.carbon_version,
                timeout_seconds=render_timeout_seconds,
            )
        data_uri, cache_hit = rendered[key]
        if data_uri is None:
            result.fallbacks += 1
            first_line = next(
                (line.strip() for line in element.text.splitlines() if line.strip()),
                "empty snippet",
            )
            result.warnings.append(
                "carbon-now failed for a code block; it falls back to styled "
                f"<pre> rendering: {first_line[:60]}"
            )
            continue
        element.image_data_uri = data_uri
        result.rendered += 1
        if cache_hit:
            result.cache_hits += 1
    return result


def code_image_data_uri(
    code: str,
    language: str | None,
    settings: dict[str, object],
    cache_dir: Path,
    *,
    binary: str,
    carbon_version: str,
    timeout_seconds: int = 120,
) -> tuple[str | None, bool]:
    key = _cache_key(code, language, settings, carbon_version)
    image_path = cache_dir / f"{key}.png"
    if _valid_png(image_path):
        return _to_data_uri(image_path), True
    image_path.unlink(missing_ok=True)
    extension = _LANGUAGE_EXTENSIONS.get((language or "").lower(), ".txt")
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            snippet_path = Path(tmpdir) / f"snippet{extension}"
            snippet_path.write_text(code, encoding="utf-8")
            completed = subprocess.run(
                [
                    binary,
                    str(snippet_path),
                    "--save-to",
                    str(cache_dir),
                    "--save-as",
                    key,
                    "--skip-display",
                    "--settings",
                    json.dumps(settings),
                ],
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                start_new_session=True,
            )
        if completed.returncode != 0 or not _valid_png(image_path):
            image_path.unlink(missing_ok=True)
            return None, False
        return _to_data_uri(image_path), False
    except (OSError, subprocess.SubprocessError):
        image_path.unlink(missing_ok=True)
        return None, False


def _walk_code_elements(elements: list[Any]) -> list[Any]:
    found: list[Any] = []
    for element in elements:
        if element.kind == "code" and element.text.strip():
            found.append(element)
        found.extend(_walk_code_elements(element.children))
        for item in element.items:
            found.extend(_walk_code_elements(item.children))
    return found


def _cache_key(
    code: str,
    language: str | None,
    settings: dict[str, object],
    carbon_version: str,
) -> str:
    payload = {
        "pipeline_version": CODE_IMAGE_PIPELINE_VERSION,
        "carbon_version": carbon_version,
        "language": language or "",
        "settings": settings,
        "code": code,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _to_data_uri(image_path: Path) -> str:
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _subprocess_detail(completed: subprocess.CompletedProcess[Any]) -> str:
    output = completed.stderr or completed.stdout or f"exit {completed.returncode}"
    lines = str(output).strip().splitlines()
    return (lines[-1] if lines else f"exit {completed.returncode}")[:240]


def _brief_error(exc: BaseException) -> str:
    return str(exc).strip().splitlines()[0][:240] or exc.__class__.__name__
