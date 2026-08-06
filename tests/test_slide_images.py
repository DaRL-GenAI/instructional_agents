from __future__ import annotations

import base64
import io
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from run import build_parser
from src.html_slides import (
    BeamerDeck,
    BeamerSlide,
    ContentElement,
    choose_layout,
    finalize_chapter,
    parse_beamer,
    render_element,
    render_speaker_notes_markdown,
)
from src.html_slides_img import (
    IMAGE_MANIFEST_FILENAME,
    ImageGenerationConfig,
    append_image_statistics,
    augment_deck_with_generated_images,
    commit_image_result,
    configured_from_cli_modes,
    configured_for_invocation,
    effective_cap,
    load_image_generation_config,
    write_image_generation_config,
    _filter_placements,
    _write_prompts,
)
from src.html_slides_style import (
    ASSET_VERSION,
    CourseSlideStyle,
    FrontendSlidesError,
    ImageGuidance,
    PresentationMethod,
    RenderTheme,
    SelectedStyle,
    course_style_from_dict,
    IMAGE_SAFETY_GUIDANCE,
    _with_required_image_safety_guidance,
    sha256_text,
    write_course_style,
)


def _style(
    *, images: bool = True, cap: int | None = 3
) -> CourseSlideStyle:
    return CourseSlideStyle(
        schema_version=1,
        asset_version=ASSET_VERSION,
        selected_style=SelectedStyle("preset", "paper-ink", "Paper & Ink"),
        presentation_method=PresentationMethod(
            narrative="Move from concrete examples toward a connected mental model.",
            pacing="Alternate explanation and application.",
            density="medium",
            emphasis="Show relationships before implementation details.",
            layout_rotation=["split", "top"],
            engagement="Use prediction prompts before revealing each relationship.",
        ),
        ta_guidance="Use a restrained editorial hierarchy with accessible contrast.",
        render_theme=RenderTheme(
            colors={
                "stage_bg": "#111111",
                "background": "#ffffff",
                "background_alt": "#f4f4f4",
                "text": "#111111",
                "muted": "#555555",
                "accent": "#2255cc",
                "accent2": "#cc5522",
                "surface": "#ffffff",
                "surface_alt": "#eeeeee",
                "border": "#2255cc",
                "panel_fill": "#ffffff",
            },
            display_font="source-serif-4",
            body_font="dm-sans",
            mono_font="ibm-plex-mono",
            title_size=96,
            heading_size=58,
            panel_style="filled",
            border_style="thin",
            shadow_style="soft",
            grid_opacity=0.1,
        ),
        inventory_sha256="inventory",
        selected_asset_sha256="asset",
        image_guidance=(
            ImageGuidance(
                enabled=True,
                visual_types=["conceptual-diagram", "process-flow"],
                prompt_style_notes=(
                    "Use simple geometric forms, restrained color, and generous "
                    "negative space suitable for an instructional deck."
                ),
                avoid_notes="Avoid decorative detail that obscures relationships.",
                max_images_per_chapter=cap,
            )
            if images
            else ImageGuidance(False, [], "", "", 0)
        ),
    )


def _deck() -> BeamerDeck:
    return BeamerDeck(
        source_path=Path("slides.tex"),
        title="Systems",
        slides=[
            BeamerSlide(
                index=1,
                title="Systems",
                elements=[],
                raw_tex="",
                is_titlepage=True,
            ),
            BeamerSlide(
                index=2,
                title="Feedback",
                elements=[
                    ContentElement(
                        kind="paragraph",
                        text="Signals move through a loop and change later behavior.",
                    )
                ],
                raw_tex="",
            ),
            BeamerSlide(
                index=3,
                title="Architecture",
                elements=[
                    ContentElement(
                        kind="paragraph",
                        text="Inputs pass through processing and produce observable outputs.",
                    )
                ],
                raw_tex="",
            ),
        ],
    )


def _png_b64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (1536, 864), "#dde6ff").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class _FakeImages:
    def __init__(self, outcomes: list[object] | None = None):
        self.outcomes = list(outcomes or [])
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(
            data=[SimpleNamespace(b64_json=str(outcome))]
        )


def _install_agent_responses(
    monkeypatch: pytest.MonkeyPatch,
    placements: list[dict[str, object]],
) -> None:
    def fake_generate(self, _prompt, stream=False, save_to_history=False):
        if self.name.startswith("Image Scout"):
            payload = {"suggestions": placements}
        elif self.name == "Image Placement Referee":
            payload = {"placements": placements}
        elif self.name == "Image Prompt Writer":
            payload = {
                "prompts": [
                    {
                        "slide_index": entry["slide_index"],
                        "prompt": (
                            "Minimal text-free instructional figure with geometric "
                            "forms and generous negative space."
                        ),
                    }
                    for entry in placements
                ]
            }
        else:
            raise AssertionError(self.name)
        return json.dumps(payload), 0.01, 7

    monkeypatch.setattr(
        "src.html_slides_img.Agent.generate_response", fake_generate
    )


def _placement(index: int) -> dict[str, object]:
    return {
        "slide_index": index,
        "rationale": "The relationship is easier to understand as a spatial model.",
        "image_concept": "A loop of connected components exchanging signals.",
        "visual_type": "conceptual-diagram",
        "labels": ["Input", "Feedback"],
    }


def test_missing_config_is_disabled_and_replace_persists_enablement(
    tmp_path: Path,
) -> None:
    assert load_image_generation_config(tmp_path) == ImageGenerationConfig()
    invocation = configured_for_invocation(
        ImageGenerationConfig(),
        replace_images=True,
        max_images_override=1,
    )
    assert invocation.enabled is True
    assert invocation.replace_images is True
    assert invocation.effective_operator_cap == 1

    path = write_image_generation_config(tmp_path, invocation)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["enabled"] is True
    assert "replace_images" not in payload
    assert load_image_generation_config(tmp_path).enabled is True
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        load_image_generation_config(tmp_path)


def test_ai_decides_image_count_persists_without_a_numeric_cap(
    tmp_path: Path,
) -> None:
    invocation = configured_for_invocation(
        ImageGenerationConfig(),
        enable=True,
        ai_decides_image_count=True,
    )
    assert invocation.ai_decides_image_count is True
    assert invocation.effective_operator_cap is None

    path = write_image_generation_config(tmp_path, invocation)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ai_decides_image_count"] is True
    loaded = load_image_generation_config(tmp_path)
    assert loaded.ai_decides_image_count is True
    assert loaded.effective_operator_cap is None


def test_legacy_style_normalizes_to_disabled_image_guidance() -> None:
    payload = asdict(_style(images=True))
    payload.pop("image_guidance")
    loaded = course_style_from_dict(payload)
    assert loaded.image_guidance.enabled is False
    assert loaded.image_guidance.max_images_per_chapter == 0


def test_uncapped_style_guidance_requires_an_explicit_null_budget() -> None:
    payload = asdict(_style(images=True))
    payload["image_guidance"]["max_images_per_chapter"] = None
    loaded = course_style_from_dict(payload)
    assert loaded.image_guidance.max_images_per_chapter is None

    del payload["image_guidance"]["max_images_per_chapter"]
    with pytest.raises(
        FrontendSlidesError,
        match="max_images_per_chapter is required",
    ):
        course_style_from_dict(payload)


def test_effective_cap_only_tightens() -> None:
    config = ImageGenerationConfig(
        enabled=True,
        max_images_per_chapter=3,
        max_images_override=1,
    )
    assert effective_cap(config, _style(cap=2).image_guidance) == 1
    assert (
        effective_cap(
            ImageGenerationConfig(
                enabled=True,
                ai_decides_image_count=True,
            ),
            _style(cap=1).image_guidance,
        )
        is None
    )
    assert (
        effective_cap(
            ImageGenerationConfig(enabled=True, max_images_per_chapter=2),
            _style(cap=None).image_guidance,
        )
        == 2
    )


def test_placement_filter_excludes_title_and_technically_dominated_slides() -> None:
    deck = _deck()
    deck.slides[2].elements = [
        ContentElement(kind="code", text="\n".join(["print(value)"] * 12))
    ]
    filtered, warnings = _filter_placements(
        [_placement(1), _placement(2), _placement(3)],
        deck,
        _style().image_guidance,
    )
    assert [entry["slide_index"] for entry in filtered] == [2]
    assert any("title-slide" in warning for warning in warnings)
    assert any("technically dominated" in warning for warning in warnings)


def test_mandatory_safety_guidance_survives_truncation() -> None:
    guidance = _style().image_guidance
    style = _style()
    style = CourseSlideStyle(
        **{
            **asdict(style),
            "selected_style": style.selected_style,
            "presentation_method": style.presentation_method,
            "render_theme": style.render_theme,
            "image_guidance": ImageGuidance(
                **{
                    **asdict(guidance),
                    "avoid_notes": "x" * 600,
                }
            ),
        }
    )
    upgraded = _with_required_image_safety_guidance(style)
    assert IMAGE_SAFETY_GUIDANCE in upgraded.image_guidance.avoid_notes
    assert len(upgraded.image_guidance.avoid_notes) <= 600


def test_prompt_writer_failure_uses_text_free_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.html_slides_img.Agent.generate_response",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("writer unavailable")
        ),
    )
    prompts, tokens, warnings = _write_prompts(
        [_placement(2)],
        style=_style(),
        llm=SimpleNamespace(),
    )
    assert tokens == 0
    assert "absolutely no text" in prompts[0]["prompt"]
    assert "#2255cc" in prompts[0]["prompt"]
    assert any("fallback" in warning for warning in warnings)


def test_disabled_boundary_makes_no_agent_or_image_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "src.html_slides_img.Agent.generate_response",
        lambda *_args, **_kwargs: pytest.fail("agent call was not expected"),
    )
    images = _FakeImages([])
    llm = SimpleNamespace(client=SimpleNamespace(images=images))
    result = augment_deck_with_generated_images(
        _deck(),
        chapter_path=tmp_path,
        style=_style(images=False),
        chapter={"title": "Systems", "description": "Introduction"},
        llm=llm,
        config=ImageGenerationConfig(enabled=True),
        source_sha256="source",
        style_sha256="style",
    )
    assert result.generated == 0
    assert images.calls == []


def test_generation_commits_provenance_and_normal_rerun_reuses_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    placements = [_placement(2)]
    _install_agent_responses(monkeypatch, placements)
    images = _FakeImages([_png_b64()])
    llm = SimpleNamespace(client=SimpleNamespace(images=images))
    config = ImageGenerationConfig(enabled=True)
    chapter = {"title": "Systems", "description": "Introduction"}

    first_deck = _deck()
    first = augment_deck_with_generated_images(
        first_deck,
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=llm,
        config=config,
        source_sha256="source",
        style_sha256="style",
    )
    assert first.generated == 1
    assert first.slides == [2]
    assert first.token_usage == 28
    assert first.estimated_cost_usd == pytest.approx(0.06)
    assert len(images.calls) == 1
    assert images.calls[0]["model"] == "gpt-image-2"
    assert images.calls[0]["size"] == "1536x864"
    commit_image_result(tmp_path, first)

    manifest_path = tmp_path / "html" / "images" / IMAGE_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest["placements"][0]
    assert record["slide_index"] == 2
    assert record["labels"] == ["Input", "Feedback"]
    assert record["prompt_sha256"]
    assert "absolutely no text" in record["prompt"]
    assert (manifest_path.parent / record["file"]).is_file()

    monkeypatch.setattr(
        "src.html_slides_img.Agent.generate_response",
        lambda *_args, **_kwargs: pytest.fail("cache reuse called an agent"),
    )
    cached_images = _FakeImages([])
    second_deck = _deck()
    second = augment_deck_with_generated_images(
        second_deck,
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=SimpleNamespace(client=SimpleNamespace(images=cached_images)),
        config=config,
        source_sha256="source",
        style_sha256="style",
    )
    assert second.reused_from_cache is True
    assert second.generated == 1
    assert cached_images.calls == []
    assert choose_layout(second_deck.slides[1]) == "media"


def test_ai_decides_mode_keeps_all_strong_eligible_placements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deck = _deck()
    for index in range(4, 8):
        deck.slides.append(
            BeamerSlide(
                index=index,
                title=f"System relationship {index}",
                elements=[
                    ContentElement(
                        kind="paragraph",
                        text="Connected components exchange signals over time.",
                    )
                ],
                raw_tex="",
            )
        )
    placements = [_placement(index) for index in range(2, 8)]
    _install_agent_responses(monkeypatch, placements)
    images = _FakeImages([_png_b64() for _ in placements])
    result = augment_deck_with_generated_images(
        deck,
        chapter_path=tmp_path,
        style=_style(cap=1),
        chapter={"title": "Systems", "description": "Introduction"},
        llm=SimpleNamespace(client=SimpleNamespace(images=images)),
        config=ImageGenerationConfig(
            enabled=True,
            ai_decides_image_count=True,
        ),
        source_sha256="source",
        style_sha256="style",
    )
    assert result.generated == 6
    assert result.slides == [2, 3, 4, 5, 6, 7]
    assert len(images.calls) == 6


def test_incomplete_replacement_retains_prior_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapter = {"title": "Systems", "description": "Introduction"}
    _install_agent_responses(monkeypatch, [_placement(2)])
    initial_images = _FakeImages([_png_b64()])
    initial = augment_deck_with_generated_images(
        _deck(),
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=SimpleNamespace(client=SimpleNamespace(images=initial_images)),
        config=ImageGenerationConfig(enabled=True),
        source_sha256="source",
        style_sha256="style",
    )
    commit_image_result(tmp_path, initial)
    old_file = initial.images[0].file

    placements = [_placement(2), _placement(3)]
    _install_agent_responses(monkeypatch, placements)
    replacement_images = _FakeImages([_png_b64(), RuntimeError("quota")])
    replacement_deck = _deck()
    replacement = augment_deck_with_generated_images(
        replacement_deck,
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=SimpleNamespace(client=SimpleNamespace(images=replacement_images)),
        config=ImageGenerationConfig(enabled=True, replace_images=True),
        source_sha256="source",
        style_sha256="style",
    )
    assert replacement.reused_from_cache is True
    assert replacement.pending_manifest is None
    assert [record.file for record in replacement.images] == [old_file]
    assert any("retained the previous image set" in item for item in replacement.warnings)
    manifest = json.loads(
        (
            tmp_path / "html" / "images" / IMAGE_MANIFEST_FILENAME
        ).read_text(encoding="utf-8")
    )
    assert manifest["placements"][0]["file"] == old_file


def test_valid_empty_replacement_removes_the_old_set_after_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chapter = {"title": "Systems", "description": "Introduction"}
    _install_agent_responses(monkeypatch, [_placement(2)])
    initial = augment_deck_with_generated_images(
        _deck(),
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=SimpleNamespace(
            client=SimpleNamespace(images=_FakeImages([_png_b64()]))
        ),
        config=ImageGenerationConfig(enabled=True),
        source_sha256="source",
        style_sha256="style",
    )
    commit_image_result(tmp_path, initial)
    old_path = tmp_path / "html" / "images" / initial.images[0].file
    assert old_path.is_file()

    _install_agent_responses(monkeypatch, [])
    empty = augment_deck_with_generated_images(
        _deck(),
        chapter_path=tmp_path,
        style=_style(),
        chapter=chapter,
        llm=SimpleNamespace(client=SimpleNamespace(images=_FakeImages([]))),
        config=ImageGenerationConfig(enabled=True, replace_images=True),
        source_sha256="source",
        style_sha256="style",
    )
    assert empty.pending_manifest is not None
    assert empty.images == []
    commit_image_result(tmp_path, empty)
    assert not old_path.exists()
    manifest = json.loads(
        (
            tmp_path / "html" / "images" / IMAGE_MANIFEST_FILENAME
        ).read_text(encoding="utf-8")
    )
    assert manifest["placements"] == []


def test_generated_figure_uses_native_accessible_labels() -> None:
    rendered = render_element(
        ContentElement(
            kind="generated_image",
            title="Feedback loop",
            image_data_uri="data:image/png;base64,AAAA",
            image_labels=["Input", "Output"],
        )
    )
    assert 'alt="Feedback loop"' in rendered
    assert "<figcaption>Feedback loop</figcaption>" in rendered
    assert 'aria-label="Figure labels"' in rendered
    assert "<li>Input</li>" in rendered


def test_finalizer_generates_when_enabled_then_early_returns_on_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter_path = course / "chapter_1"
    chapter_path.mkdir(parents=True)
    style_source = "test selected style source"
    style = _style()
    style = CourseSlideStyle(
        **{
            **asdict(style),
            "selected_style": style.selected_style,
            "presentation_method": style.presentation_method,
            "render_theme": style.render_theme,
            "image_guidance": style.image_guidance,
            "selected_asset_sha256": sha256_text(style_source),
        }
    )
    write_course_style(course / "course_slide_style.json", style)
    (course / "course_slide_style_source.md").write_text(
        style_source, encoding="utf-8"
    )
    tex_path = chapter_path / "slides.tex"
    tex_path.write_text(
        r"""\documentclass{beamer}
\title{Systems}
\begin{document}
\begin{frame}\titlepage\end{frame}
\begin{frame}{Feedback}
Signals move through a loop and change later behavior.
\end{frame}
\end{document}
""",
        encoding="utf-8",
    )
    deck = parse_beamer(tex_path)
    (chapter_path / "script.md").write_text(
        render_speaker_notes_markdown(
            deck,
            ["Explain how delayed feedback changes the system."],
            document_title="Slides Script: Systems",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.html_slides.LaTeXCompiler.compile_one",
        lambda *_args: (chapter_path / "slides.pdf").write_bytes(b"%PDF"),
    )
    monkeypatch.setattr(
        "src.html_slides.validate_with_playwright",
        lambda *_args: [],
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        if pdf_path is not None:
            pdf_path.write_bytes(b"%PDF-html")
        if pptx_path is not None:
            pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr("src.html_slides.export_html_deck", fake_export)
    _install_agent_responses(monkeypatch, [_placement(2)])
    image_client = _FakeImages([_png_b64()])
    config = ImageGenerationConfig(enabled=True)
    chapter = {"title": "Systems", "description": "Feedback systems"}
    first = finalize_chapter(
        course,
        chapter_path,
        llm=SimpleNamespace(client=SimpleNamespace(images=image_client)),
        chapter=chapter,
        image_config=config,
    )
    assert first.skipped is False
    manifest = json.loads(
        (chapter_path / "frontend-slides-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["images"]["generated"] == 1
    assert manifest["images"]["slide_indexes"] == [2]
    assert "gen-image-card" in (
        chapter_path / "html" / "slides.html"
    ).read_text(encoding="utf-8")

    monkeypatch.setattr(
        "src.html_slides_img.Agent.generate_response",
        lambda *_args, **_kwargs: pytest.fail("cache path called an agent"),
    )
    second = finalize_chapter(
        course,
        chapter_path,
        llm=SimpleNamespace(client=SimpleNamespace(images=_FakeImages([]))),
        chapter=chapter,
        image_config=config,
    )
    assert second.skipped is True


def test_statistics_are_an_append_only_invocation_ledger(
    tmp_path: Path,
) -> None:
    from src.html_slides_img import ChapterImageResult

    append_image_statistics(
        tmp_path,
        ChapterImageResult(generated=1, estimated_cost_usd=0.06),
    )
    append_image_statistics(
        tmp_path,
        ChapterImageResult(generated=1, reused_from_cache=True),
    )
    payload = json.loads(
        (tmp_path / "statistics_slide_images.json").read_text(encoding="utf-8")
    )
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["generated"] == 1
    assert payload["runs"][1]["generated"] == 0
    assert payload["runs"][1]["current_image_count"] == 1


def test_run_cli_media_flags() -> None:
    args = build_parser().parse_args(
        [
            "Systems",
            "--image-generation",
            "replace",
            "--image-count",
            "on",
            "--code-images",
            "on",
        ]
    )
    assert args.image_generation == "replace"
    assert args.image_count == "on"
    assert args.code_images == "on"

    disabled = build_parser().parse_args(
        [
            "Systems",
            "--image-generation",
            "off",
            "--image-count",
            "off",
            "--code-images",
            "off",
        ]
    )
    assert disabled.image_generation == "off"
    assert disabled.image_count == "off"
    assert disabled.code_images == "off"

    with pytest.raises(SystemExit):
        build_parser().parse_args(["Systems", "--image-count", "auto"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["Systems", "--enable-image-generation"])


def test_consolidated_image_modes_preserve_fixed_cap() -> None:
    stored = ImageGenerationConfig(
        enabled=True,
        max_images_per_chapter=2,
        ai_decides_image_count=False,
    )
    automatic = configured_from_cli_modes(
        stored,
        image_generation="on",
        image_count="on",
    )
    assert automatic.enabled is True
    assert automatic.ai_decides_image_count is True
    assert automatic.effective_operator_cap is None

    fixed = configured_from_cli_modes(automatic, image_count="off")
    assert fixed.enabled is True
    assert fixed.ai_decides_image_count is False
    assert fixed.effective_operator_cap == 2

    disabled = configured_from_cli_modes(fixed, image_generation="off")
    assert disabled.enabled is False
    replacement = configured_from_cli_modes(disabled, image_generation="replace")
    assert replacement.enabled is True
    assert replacement.replace_images is True


def test_api_request_validates_image_fields() -> None:
    from pydantic import ValidationError

    from api_server import CourseRequest

    request = CourseRequest(
        course_name="Systems",
        enable_image_generation=True,
        replace_images=True,
        max_images_per_chapter=2,
    )
    assert request.enable_image_generation is True
    assert request.replace_images is True
    assert request.max_images_per_chapter == 2
    uncapped = CourseRequest(
        course_name="Systems",
        enable_image_generation=True,
        ai_decides_image_count=True,
    )
    assert uncapped.ai_decides_image_count is True
    assert uncapped.max_images_per_chapter is None
    code_images = CourseRequest(course_name="Systems", code_images=True)
    assert code_images.code_images is True
    assert CourseRequest(course_name="Systems").code_images is None
    with pytest.raises(ValidationError):
        CourseRequest(
            course_name="Systems",
            max_images_per_chapter=4,
        )
    with pytest.raises(ValidationError):
        CourseRequest(
            course_name="Systems",
            max_images_per_chapter=2,
            ai_decides_image_count=True,
        )
