import base64
import json
import subprocess
from pathlib import Path

import pytest

from src import html_slides_code
from src.html_slides import BeamerDeck, BeamerSlide, ContentElement, ListItem
from src.html_slides_code import (
    CARBON_NOW_PACKAGE,
    CodeImageConfig,
    attach_code_images,
    carbon_cache_version_is_current,
    configured_for_invocation,
    load_code_image_config,
    write_code_image_config,
)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAusB9Wl2ZQAAAABJRU5ErkJggg=="
)
THEME = {
    "carbon_theme": "nord",
    "carbon_background": "rgba(0,0,0,0)",
}


def _code(text: str = 'print("hi")', language: str | None = "python") -> ContentElement:
    return ContentElement(kind="code", text=text, language=language)


def _deck(elements: list[ContentElement]) -> BeamerDeck:
    return BeamerDeck(
        source_path=Path("slides.tex"),
        title="Code",
        slides=[BeamerSlide(index=1, title="Code", elements=elements, raw_tex="")],
    )


def _successful_carbon_run(
    calls: list[list[str]],
    *,
    version: str = "2.1.0",
):
    def run(command, **kwargs):
        command = [str(part) for part in command]
        calls.append(command)
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, stdout=version, stderr="")
        output_dir = Path(command[command.index("--save-to") + 1])
        output_name = command[command.index("--save-as") + 1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{output_name}.png").write_bytes(PNG_BYTES)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return run


def test_code_image_config_defaults_persists_and_merges(tmp_path: Path) -> None:
    assert load_code_image_config(tmp_path) == CodeImageConfig(enabled=False)
    enabled = configured_for_invocation(CodeImageConfig(), True)
    path = write_code_image_config(tmp_path, enabled)
    assert load_code_image_config(tmp_path) == CodeImageConfig(enabled=True)
    assert configured_for_invocation(enabled, None) == enabled
    assert configured_for_invocation(enabled, False) == CodeImageConfig(enabled=False)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "enabled": True,
        "schema_version": 1,
    }


def test_disabled_and_no_code_decks_never_probe_or_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("No executable lookup or subprocess is allowed")

    monkeypatch.setattr(html_slides_code.shutil, "which", fail)
    monkeypatch.setattr(html_slides_code.subprocess, "run", fail)

    disabled = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=False),
        request_fingerprint="disabled",
    )
    no_code = attach_code_images(
        _deck([ContentElement(kind="text", text="No code")]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="no-code",
    )

    assert disabled.code_blocks == 1 and disabled.rendered == 0
    assert no_code.code_blocks == 0 and no_code.install_attempted is False


def test_missing_npm_warns_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(html_slides_code.shutil, "which", lambda _: None)
    element = _code()
    result = attach_code_images(
        _deck([element]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="missing",
    )

    assert result.install_attempted is True
    assert result.fallbacks == 1
    assert result.complete is False
    assert "npm is unavailable" in result.warnings[0]
    assert element.image_data_uri is None


def test_missing_carbon_installs_pinned_cli_and_renders_all_nested_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = False
    calls: list[list[str]] = []

    def which(command: str) -> str | None:
        if command == "npm":
            return "/usr/bin/npm"
        if command == "carbon-now":
            return "/usr/bin/carbon-now" if installed else None
        return None

    def run(command, **kwargs):
        nonlocal installed
        command = [str(part) for part in command]
        if command[:3] == ["/usr/bin/npm", "install", "--global"]:
            calls.append(command)
            installed = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return _successful_carbon_run(calls)(command, **kwargs)

    monkeypatch.setattr(html_slides_code.shutil, "which", which)
    monkeypatch.setattr(html_slides_code.subprocess, "run", run)

    top = _code()
    duplicate = _code()
    nested = _code("const answer = 42", "javascript")
    deck = _deck(
        [
            top,
            ContentElement(
                kind="list",
                items=[
                    ListItem(
                        text="Nested",
                        children=[
                            duplicate,
                            ContentElement(
                                kind="block", title="Example", children=[nested]
                            ),
                        ],
                    )
                ],
            ),
        ]
    )
    result = attach_code_images(
        deck,
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="enabled",
    )

    assert result.install_attempted is True
    assert result.install_succeeded is True
    assert calls[0] == ["/usr/bin/npm", "install", "--global", CARBON_NOW_PACKAGE]
    render_calls = [command for command in calls if "--save-to" in command]
    assert len(render_calls) == 2
    assert result.code_blocks == 3
    assert result.unique_snippets == 2
    assert result.rendered == 3
    assert result.fallbacks == 0
    assert all(
        element.image_data_uri
        and element.image_data_uri.startswith("data:image/png;base64,")
        for element in (top, duplicate, nested)
    )


def test_cache_hits_skip_render_and_carbon_version_changes_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "2.1.0"
    calls: list[list[str]] = []
    monkeypatch.setattr(
        html_slides_code.shutil,
        "which",
        lambda command: "/usr/bin/carbon-now" if command == "carbon-now" else None,
    )

    def run(command, **kwargs):
        return _successful_carbon_run(calls, version=version)(command, **kwargs)

    monkeypatch.setattr(html_slides_code.subprocess, "run", run)

    first = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="same",
    )
    second = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="same",
    )
    version = "2.2.0"
    third = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="same",
    )

    assert first.cache_hits == 0
    assert second.cache_hits == 1
    assert third.cache_hits == 0
    assert len([command for command in calls if "--save-to" in command]) == 2
    assert len(list(tmp_path.glob("*.png"))) == 2


@pytest.mark.parametrize(
    ("previous", "installed", "expected"),
    [
        ("2.1.0", "2.1.0", True),
        ("2.1.0", "2.2.0", False),
        ("unknown", "2.1.0", False),
        ("unknown", None, False),
        (None, "2.1.0", False),
    ],
)
def test_carbon_cache_requires_matching_known_versions(
    previous: object,
    installed: str | None,
    expected: bool,
) -> None:
    assert carbon_cache_version_is_current(previous, installed) is expected


def test_install_and_malformed_png_failures_are_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = False

    def which(command: str) -> str | None:
        if command == "npm":
            return "/usr/bin/npm"
        if command == "carbon-now" and installed:
            return "/usr/bin/carbon-now"
        return None

    def failed_install(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="denied")

    monkeypatch.setattr(html_slides_code.shutil, "which", which)
    monkeypatch.setattr(html_slides_code.subprocess, "run", failed_install)
    install_result = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="install-failure",
    )
    assert install_result.fallbacks == 1
    assert "denied" in install_result.warnings[0]

    installed = True

    def malformed(command, **kwargs):
        command = [str(part) for part in command]
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, stdout="2.1.0", stderr="")
        output_dir = Path(command[command.index("--save-to") + 1])
        output_name = command[command.index("--save-as") + 1]
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{output_name}.png").write_bytes(b"not a png")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(html_slides_code.subprocess, "run", malformed)
    malformed_result = attach_code_images(
        _deck([_code("secret = 1")]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="malformed",
    )
    assert malformed_result.fallbacks == 1
    assert malformed_result.complete is False
    assert not list(tmp_path.glob("*.png"))


def test_install_timeout_warns_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        html_slides_code.shutil,
        "which",
        lambda command: "/usr/bin/npm" if command == "npm" else None,
    )

    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=1)

    monkeypatch.setattr(html_slides_code.subprocess, "run", timeout)
    result = attach_code_images(
        _deck([_code()]),
        THEME,
        tmp_path,
        config=CodeImageConfig(enabled=True),
        request_fingerprint="timeout",
        install_timeout_seconds=1,
    )

    assert result.fallbacks == 1
    assert result.complete is False
    assert "timed out" in result.warnings[0]
