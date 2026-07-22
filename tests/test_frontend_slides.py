from __future__ import annotations

import json
import zipfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from pptx import Presentation

from src.frontend_slides import load_assets
from src.frontend_slides import parse_beamer
from src.frontend_slides import FrontendSlidesError
from src.frontend_slides import capture_slide_screenshots, export_html_deck
from src.frontend_slides import MANIFEST_SCHEMA_VERSION, finalize_chapter
from src.frontend_slides import (
    ContentElement,
    ListItem,
)
from src.frontend_slides import render_speaker_notes_markdown
from src.frontend_slides import (
    _split_columns,
    render_course_presentation_html,
)
from src.frontend_slides import prepare_offline_runtime, runtime_asset_root
from src.slide_style import (
    ASSET_VERSION,
    COLOR_KEYS,
    CourseSlideStyle,
    PRESENTATION_DESIGN_FILENAME,
    PresentationMethod,
    RenderTheme,
    SelectedStyle,
    SkillAssetError,
    STYLE_FILENAME,
    STYLE_SOURCE_FILENAME,
    build_style_inventory,
    canonicalize_selection_payload,
    canonicalize_materialization_payload,
    selected_asset_text,
    sha256_file,
    sha256_text,
    slide_gen_asset_root,
    validate_materialization,
    validate_selection,
    write_course_style,
)
from src.slide_style import (
    ensure_course_slide_style,
    load_course_slide_style,
)
from src.frontend_slides import (
    validate_html_contract,
    validate_offline_contract,
)
from src.frontend_slides import element_weight


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


def make_selection_payload(
    *,
    source: str = "bold_template",
    key: str = "cobalt-grid",
    alternatives: list[tuple[str, str]] | None = None,
) -> dict[str, object]:
    if alternatives is None:
        alternatives = [
            ("bold_template", "blue-professional"),
            ("preset", "paper-ink"),
        ]
    return {
        "selected_style": {"source": source, "key": key},
        "presentation_method": {
            "narrative": "Build a visual progression from foundational ideas to applied examples.",
            "pacing": "Alternate concise explanations with guided practice moments.",
            "density": "medium",
            "emphasis": "Prioritize worked examples and visible conceptual relationships.",
            "layout_rotation": ["hero", "split", "top"],
            "engagement": "Use guided questions and short prediction prompts throughout.",
        },
        "selection_evidence": {
            "course_requirements": [
                "Maintain readable hierarchy for explanations and worked examples.",
                "Support multiple layouts for concepts, comparisons, and practice.",
                "Keep the visual treatment coherent across every course chapter.",
            ],
            "alternatives": [
                {
                    "source": alternative_source,
                    "key": alternative_key,
                    "reason_rejected": (
                        "This alternative does not balance the course's explanatory "
                        "density and layout needs as effectively as the selected style."
                    ),
                }
                for alternative_source, alternative_key in alternatives
            ],
            "avoid_for_assessment": (
                "The selected style's avoid-for guidance does not conflict with the "
                "course audience, its instructional activities, or the required tone."
            ),
        },
        "reason": (
            "The selected style directly supports the course's worked examples, varied "
            "chapter structures, and need for a readable hierarchy while remaining "
            "coherent across the complete learning sequence."
        ),
    }


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
    deck = parse_beamer(path)
    (path.parent / "script.md").write_text(
        render_speaker_notes_markdown(
            deck,
            ["Notes for nested concepts.", "Notes for the equation."],
            document_title="Slides Script: Offline Course",
        ),
        encoding="utf-8",
    )


def test_inventory_contains_all_46_styles() -> None:
    inventory, digest = build_style_inventory(load_assets())

    assert len(inventory) == 46
    assert sum(item.source == "preset" for item in inventory) == 12
    assert sum(item.source == "bold_template" for item in inventory) == 34
    assert len(digest) == 64


def test_slide_resources_use_the_root_asset_package() -> None:
    root = slide_gen_asset_root()
    skill_root = root / "skill"

    assert load_assets().root == skill_root
    assert runtime_asset_root() == root / "runtime"
    assert len(list(skill_root.glob("bold-template-pack/templates/*/design.md"))) == 34
    assert not list(skill_root.rglob("preview.md"))
    assert not (skill_root / "html-template.md").exists()
    assert not (skill_root / "animation-patterns.md").exists()


def test_load_assets_rejects_an_incomplete_override(tmp_path: Path) -> None:
    with pytest.raises(SkillAssetError, match="Missing required frontend-slides assets"):
        load_assets(tmp_path)


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


def test_materialization_canonicalizes_rgba_and_known_font_aliases() -> None:
    style = make_style()
    payload = {
        "ta_guidance": "Use Space Grotesk headings and Inter body text.",
        "render_theme": {
            **asdict(style.render_theme),
            "colors": {
                **style.render_theme.colors,
                "background": "#fdfae7",
                "border": "rgba(30, 43, 250, 0.2)",
                "panel_fill": "rgba(30, 43, 250, 0.04)",
            },
            "body_font": "inter",
        },
    }

    normalized, notes = canonicalize_materialization_payload(payload)
    result = validate_materialization(
        normalized,
        selected_style=style.selected_style,
        presentation_method=style.presentation_method,
        inventory_sha256="inventory",
        selected_asset_sha256=style.selected_asset_sha256,
    )

    assert result.render_theme.colors["border"] == "#d0d1eb"
    assert result.render_theme.colors["panel_fill"] == "#f4f2e8"
    assert result.render_theme.body_font == "dm-sans"
    assert "DM Sans body text" in result.ta_guidance
    assert len(notes) == 3


def test_style_selection_rejects_placeholder_presentation_text() -> None:
    inventory, _ = build_style_inventory(load_assets())
    payload = make_selection_payload()
    payload["presentation_method"]["narrative"] = "course-wide narrative approach"

    with pytest.raises(FrontendSlidesError, match="placeholder text"):
        validate_selection(payload, inventory)


@pytest.mark.parametrize("failure", ["selected", "duplicate", "unknown"])
def test_style_selection_rejects_invalid_alternatives(failure: str) -> None:
    inventory, _ = build_style_inventory(load_assets())
    payload = make_selection_payload()
    alternatives = payload["selection_evidence"]["alternatives"]
    if failure == "selected":
        alternatives[0]["source"] = "bold_template"
        alternatives[0]["key"] = "cobalt-grid"
    elif failure == "duplicate":
        alternatives[1] = dict(alternatives[0])
    else:
        alternatives[0]["source"] = "preset"
        alternatives[0]["key"] = "not-a-style"

    with pytest.raises(FrontendSlidesError, match="alternative"):
        validate_selection(payload, inventory)


def test_style_selection_canonicalizes_full_page_layout() -> None:
    inventory, _ = build_style_inventory(load_assets())
    payload = make_selection_payload()
    payload["presentation_method"]["layout_rotation"] = ["full-page", "split"]

    normalized, notes = canonicalize_selection_payload(payload, inventory)
    _, method, _, _ = validate_selection(normalized, inventory)

    assert method.layout_rotation == ["hero", "split"]
    assert any("full-page->hero" in note for note in notes)


def test_playful_course_evidence_can_select_daisy_days() -> None:
    inventory, _ = build_style_inventory(load_assets())
    payload = make_selection_payload(
        key="daisy-days",
        alternatives=[
            ("bold_template", "playful"),
            ("preset", "split-pastel"),
        ],
    )
    payload["selection_evidence"]["course_requirements"] = [
        "Use a cheerful visual register appropriate for children ages five to seven.",
        "Support picture-book storytelling, puppetry, movement, and collaborative art.",
        "Keep text concise and approachable for emerging readers and active learners.",
    ]
    payload["selection_evidence"]["avoid_for_assessment"] = (
        "Daisy Days warns against precision-first authoritative contexts, while this "
        "course is intentionally playful, child-facing, creative, and informal."
    )
    payload["reason"] = (
        "Daisy Days matches the five-to-seven-year-old audience through its cheerful, "
        "soft visual language and directly supports picture-book storytelling, puppet "
        "making, movement, and collaborative art without imposing corporate polish."
    )

    selected, _, _, evidence = validate_selection(payload, inventory)

    assert selected.key == "daisy-days"
    assert len(evidence["alternatives"]) == 2


def test_offline_renderer_preserves_frames_and_has_no_remote_urls(tmp_path: Path) -> None:
    tex = tmp_path / "slides.tex"
    write_beamer(tex)
    deck = parse_beamer(tex)
    style = make_style()
    _, font_css = prepare_offline_runtime(tmp_path, style)

    html = render_course_presentation_html(
        deck, style, load_assets(), font_css=font_css
    )

    assert validate_html_contract(html, deck.slide_count, load_assets().viewport_css) == []
    assert validate_offline_contract(html) == []
    assert "assets/mathjax/tex-svg.js" in html
    assert "https://" not in html


def test_dense_nested_list_balances_with_a_short_preamble() -> None:
    def technique(name: str, code: str) -> ListItem:
        return ListItem(
            name,
            children=[
                ContentElement(
                    kind="list",
                    items=[
                        ListItem("Describe the transformation."),
                        ListItem(
                            "Show the formula.",
                            children=[
                                ContentElement(
                                    kind="equation",
                                    text=r"x' = \frac{x-a}{b-a}",
                                )
                            ],
                        ),
                        ListItem(
                            "Run the example.",
                            children=[
                                ContentElement(
                                    kind="code",
                                    text=code,
                                    language="Python",
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

    preamble = ContentElement(
        kind="text",
        text=(
            "Guide to using Scikit-learn for normalization, standardization, "
            "and encoding categorical variables in a reproducible workflow."
        ),
    )
    dense_list = ContentElement(
        kind="list",
        items=[
            ListItem(
                "Importance of Data Preprocessing",
                children=[
                    ContentElement(
                        kind="list",
                        items=[
                            ListItem("Prepare raw data for models."),
                            ListItem("Improve model performance."),
                        ],
                    )
                ],
            ),
            ListItem(
                "Key Techniques",
                children=[
                    ContentElement(
                        kind="list",
                        items=[
                            technique(
                                "Normalization",
                                "scaler = MinMaxScaler()\n"
                                "normalized = scaler.fit_transform(data)",
                            ),
                            technique(
                                "Standardization",
                                "scaler = StandardScaler()\n"
                                "standardized = scaler.fit_transform(data)",
                            ),
                            ListItem(
                                "Encoding Categorical Variables",
                                children=[
                                    ContentElement(
                                        kind="list",
                                        items=[
                                            ListItem("Convert categories to numbers."),
                                            ListItem("Choose label or one-hot encoding."),
                                            ListItem(
                                                "Run the encoder.",
                                                children=[
                                                    ContentElement(
                                                        kind="code",
                                                        text=(
                                                            "encoder = LabelEncoder()\n"
                                                            "labels = encoder.fit_transform(data)"
                                                        ),
                                                        language="Python",
                                                    )
                                                ],
                                            ),
                                        ],
                                    )
                                ],
                            ),
                        ],
                    )
                ],
            ),
        ],
    )

    left, right = _split_columns([preamble, dense_list])
    left_weight = sum(element_weight(element) for element in left)
    right_weight = sum(element_weight(element) for element in right)

    assert max(left_weight, right_weight) <= 18
    assert abs(left_weight - right_weight) <= 2
    assert left[-1].items[0].text == "Normalization"
    assert right[0].items[0].text == "Standardization"
    assert right[1].items[0].text == "Encoding Categorical Variables"


def test_style_workflow_uses_foundational_roles_and_selected_asset_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    style_preferences = {
        "preferred_visual_direction": (
            "STYLE-PREFERENCE-SENTINEL: restrained editorial instruction"
        ),
        "accessibility_requirements": "High contrast and readable type sizes.",
    }
    selection = json.dumps(make_selection_payload())
    materialization = json.dumps(
        {
            "ta_guidance": "Use cobalt hierarchy.",
            "render_theme": asdict(make_style().render_theme),
        }
    )

    def fake_deliberation_run(self):
        seen["deliberation_calls"] = int(seen.get("deliberation_calls", 0)) + 1
        seen["max_rounds"] = self.max_rounds
        seen["instruction_prompt"] = self.instruction_prompt
        seen["selection_constraint"] = self.summary_agent.output_constraint
        seen["roles"] = [agent.name for agent in self.agents] + [self.summary_agent.name]
        seen["instructional_designer_prompt"] = next(
            agent.system_prompt
            for agent in self.agents
            if agent.name == "Instructional Designer"
        )
        self.discussion_history = [{"agent": "Teaching Faculty", "content": "Discussion"}]
        return selection, 1.0, 10

    def fake_generate(self, prompt, stream=True, save_to_history=False):
        if self.name == "Instructional Designer" and "Selected style asset" in prompt:
            seen["materializer"] = self.name
            seen["materialization_prompt"] = prompt
            return materialization, 1.0, 10
        raise AssertionError(f"Unexpected repair call for {self.name}")

    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        fake_deliberation_run,
    )
    monkeypatch.setattr(
        "src.slide_style.Agent.generate_response",
        fake_generate,
    )
    addie = SimpleNamespace(
        course_name="Test Course",
        llm=object(),
        catalog_dict={"presentation_style_preferences": style_preferences},
    )

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
        "Summarizer",
    ]
    assert seen["materializer"] == "Instructional Designer"
    assert "Beamer content" in str(seen["instructional_designer_prompt"])
    assert "1920x1080 HTML rendering" in str(
        seen["instructional_designer_prompt"]
    )
    assert seen["deliberation_calls"] == 1
    assert seen["max_rounds"] == 1
    assert "compare at least three exact inventory candidates" in str(
        seen["instruction_prompt"]
    )
    assert "Best for and Avoid for guidance" in str(seen["instruction_prompt"])
    assert "STYLE-PREFERENCE-SENTINEL" in str(seen["instruction_prompt"])
    assert "more specific than the legacy" in str(seen["instruction_prompt"])
    assert "prioritize accessibility, readability, course suitability" in str(
        seen["instruction_prompt"]
    )
    assert "explain honored and unmet preferences" in str(
        seen["instruction_prompt"]
    )
    contract_shape = str(seen["selection_constraint"]).split(
        "ALLOWED_STYLE_PAIRS:", 1
    )[0]
    assert "when non-empty catalog_style_preferences are supplied" in contract_shape
    assert '"key": "cobalt-grid"' not in contract_shape
    assert '"key": "paper-ink"' not in contract_shape
    prompt = str(seen["materialization_prompt"])
    assert "Cobalt Grid" in prompt
    assert "Complete style inventory" not in prompt
    assert "STYLE-PREFERENCE-SENTINEL" not in prompt
    assert style.selected_style.key == "cobalt-grid"
    assert load_course_slide_style(tmp_path) == style
    presentation_result = (
        tmp_path / PRESENTATION_DESIGN_FILENAME
    ).read_text(encoding="utf-8")
    assert presentation_result.startswith("Presentation Design\n===================")
    assert "- Key: `cobalt-grid`" in presentation_result
    assert "## Selection Rationale" in presentation_result
    assert "## Course Visual Requirements" in presentation_result
    assert "## Alternatives Considered" in presentation_result
    assert "## Selected-Style Conflict Check" in presentation_result
    assert "## Presentation Method" in presentation_result
    assert "## Palette" in presentation_result
    assert "## Typography" in presentation_result
    assert "transparent backgrounds" in presentation_result
    assert "decorative cards" in style.ta_guidance
    stats = json.loads(
        (tmp_path / "statistics_slide_style.json").read_text(encoding="utf-8")
    )
    assert stats["participating_agents"] == [
        "Teaching Faculty",
        "Instructional Designer",
        "Course Coordinator",
        "Summarizer",
    ]
    assert "Teaching Assistant" not in stats["participating_agents"]
    assert stats["catalog_style_preferences"] == style_preferences
    assert len(stats["selection_evidence"]["course_requirements"]) == 3
    assert len(stats["selection_evidence"]["alternatives"]) == 2
    resumed = ensure_course_slide_style(addie, tmp_path, [], [])
    assert resumed == style
    assert (
        tmp_path / PRESENTATION_DESIGN_FILENAME
    ).read_text(encoding="utf-8") == presentation_result


def test_style_resume_makes_no_agent_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_style(tmp_path)
    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        lambda _self: pytest.fail("style deliberation should be skipped"),
    )

    style = ensure_course_slide_style(
        SimpleNamespace(course_name="Test", llm=object()),
        tmp_path,
        [],
        [],
    )

    assert style.selected_style.key == "cobalt-grid"
    assert (tmp_path / PRESENTATION_DESIGN_FILENAME).is_file()
    assert "decorative cards" in style.ta_guidance


def test_style_resume_uses_frozen_authority_when_inventory_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_style(tmp_path)
    monkeypatch.setattr(
        "src.slide_style.build_style_inventory",
        lambda *_args, **_kwargs: pytest.fail(
            "ordinary resume must not consult inventory or reselect"
        ),
    )
    monkeypatch.setattr(
        "src.slide_style.selected_asset_text",
        lambda *_args, **_kwargs: pytest.fail(
            "ordinary resume must use the frozen source snapshot"
        ),
    )
    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        lambda _self: pytest.fail("style deliberation should be skipped"),
    )

    style = ensure_course_slide_style(
        SimpleNamespace(course_name="Test", llm=object()),
        tmp_path,
        [],
        [],
    )

    assert style.selected_style.key == "cobalt-grid"
    assert (tmp_path / PRESENTATION_DESIGN_FILENAME).is_file()


def test_invalid_frozen_style_requires_explicit_reselection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_style(tmp_path)
    (tmp_path / STYLE_SOURCE_FILENAME).write_text("tampered", encoding="utf-8")
    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        lambda _self: pytest.fail("invalid authority must not be silently reselected"),
    )

    with pytest.raises(
        FrontendSlidesError, match="--reselect-presentation-design"
    ):
        ensure_course_slide_style(
            SimpleNamespace(course_name="Test", llm=object()),
            tmp_path,
            [],
            [],
        )


def test_explicit_reselection_replaces_existing_style(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_style(tmp_path)
    selection = json.dumps(
        make_selection_payload(
            key="blue-professional",
            alternatives=[
                ("bold_template", "cobalt-grid"),
                ("bold_template", "signal"),
            ],
        )
    )
    materialization = json.dumps(
        {
            "ta_guidance": "Use a restrained professional hierarchy.",
            "render_theme": asdict(make_style().render_theme),
        }
    )
    calls = 0

    def fake_deliberation_run(_self):
        nonlocal calls
        calls += 1
        return selection, 1.0, 10

    def fake_generate(self, _prompt, stream=True, save_to_history=False):
        assert self.name == "Instructional Designer"
        return materialization, 1.0, 10

    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        fake_deliberation_run,
    )
    monkeypatch.setattr(
        "src.slide_style.Agent.generate_response",
        fake_generate,
    )

    style = ensure_course_slide_style(
        SimpleNamespace(course_name="Test", llm=object()),
        tmp_path,
        ["Test", "Foundation"],
        [{"title": "One", "description": "Chapter"}],
        reselect=True,
    )

    assert calls == 1
    assert style.selected_style.key == "blue-professional"
    assert "- Key: `blue-professional`" in (
        tmp_path / PRESENTATION_DESIGN_FILENAME
    ).read_text(encoding="utf-8")


def test_style_selection_canonicalizes_literal_union_slug_and_layout_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bad_selection = make_selection_payload(
        key="blue-professional",
        alternatives=[
            ("bold_template", "cobalt-grid"),
            ("bold_template", "signal"),
        ],
    )
    bad_selection["selected_style"] = {
        "source": "preset|bold_template",
        "key": "blue_professional",
    }
    bad_selection["presentation_method"]["layout_rotation"] = [
        "overview",
        "content",
    ]
    materialization = json.dumps(
        {
            "ta_guidance": "Use a clear professional hierarchy.",
            "render_theme": asdict(make_style().render_theme),
        }
    )
    seen: dict[str, object] = {"repair_calls": 0}

    def fake_deliberation_run(self):
        seen["constraint"] = self.summary_agent.output_constraint
        self.discussion_history = [
            {"agent": "Teaching Faculty", "content": "Choose Blue Professional."}
        ]
        return json.dumps(bad_selection), 1.0, 10

    def fake_generate(self, prompt, stream=True, save_to_history=False):
        if self.name == "Summarizer":
            raise AssertionError("Unambiguous aliases should not require an LLM repair")
        if self.name == "Instructional Designer":
            return materialization, 1.0, 10
        raise AssertionError(f"Unexpected agent call for {self.name}")

    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        fake_deliberation_run,
    )
    monkeypatch.setattr(
        "src.slide_style.Agent.generate_response",
        fake_generate,
    )

    style = ensure_course_slide_style(
        SimpleNamespace(course_name="Differential Equations", llm=object()),
        tmp_path,
        ["Differential Equations", "Foundation"],
        [{"title": "First-order ODEs", "description": "Introduction"}],
    )

    assert seen["repair_calls"] == 0
    assert '"source": "preset|bold_template"' not in str(seen["constraint"])
    assert style.selected_style.source == "bold_template"
    assert style.selected_style.key == "blue-professional"
    assert style.presentation_method.layout_rotation == ["hero", "top"]
    stats = json.loads(
        (tmp_path / "statistics_slide_style.json").read_text(encoding="utf-8")
    )
    assert len(stats["selection_normalizations"]) == 2


def test_invalid_style_selection_retries_twice_then_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repair_calls = 0
    monkeypatch.setattr(
        "src.slide_style.Deliberation.run",
        lambda _self: ('{"selected_style":{"source":"preset","key":"missing"}}', 1.0, 5),
    )

    def invalid_repair(self, prompt, stream=True, save_to_history=False):
        nonlocal repair_calls
        repair_calls += 1
        return "not json", 1.0, 5

    monkeypatch.setattr(
        "src.slide_style.Agent.generate_response",
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
    html_path = chapter / "html" / "slides.html"
    html_path.parent.mkdir()
    html_path.write_text("<html>existing</html>", encoding="utf-8")
    (chapter / "slides-html.pdf").write_bytes(b"%PDF-html")
    (chapter / "slide-splits.json").write_text("{}", encoding="utf-8")
    prepare_offline_runtime(chapter, make_style())
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "source_sha256": sha256_file(chapter / "slides.tex"),
        "script_sha256": sha256_file(chapter / "script.md"),
        "style_sha256": sha256_file(course / STYLE_FILENAME),
        "slide_count": 3,
    }
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    calls: list[tuple[Path | None, Path | None]] = []

    monkeypatch.setattr(
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("LaTeX should not recompile"),
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        calls.append((pdf_path, pptx_path))
        assert pdf_path is None
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr("src.frontend_slides.export_html_deck", fake_export)

    result = finalize_chapter(course, chapter)

    assert len(calls) == 1
    assert calls[0][0] is None
    assert result.html_pptx_path.read_bytes() == b"pptx"
    written_manifest = json.loads(
        (chapter / "frontend-slides-manifest.json").read_text(encoding="utf-8")
    )
    assert written_manifest["runtime"] == "html/assets"
    assert written_manifest["artifacts"]["html"] == "html/slides.html"
    assert not (chapter / "slide-splits.json").exists()


def test_schema_two_layout_migrates_without_recompiling_latex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    (chapter / "slides.html").write_text("<html>legacy</html>", encoding="utf-8")
    legacy_runtime = chapter / "frontend-assets" / "mathjax"
    legacy_runtime.mkdir(parents=True)
    (legacy_runtime / "tex-svg.js").write_text("legacy", encoding="utf-8")
    (chapter / "slides-html.pdf").write_bytes(b"%PDF-legacy")
    (chapter / "slides-html.pptx").write_bytes(b"pptx-legacy")
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "source_sha256": sha256_file(chapter / "slides.tex"),
                "style_sha256": sha256_file(course / STYLE_FILENAME),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A layout migration must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: [],
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        pdf_path.write_bytes(b"%PDF-html")
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.frontend_slides.export_html_deck", fake_export
    )

    result = finalize_chapter(course, chapter)

    assert result.html_path == chapter / "html" / "slides.html"
    assert "assets/mathjax/tex-svg.js" in result.html_path.read_text(encoding="utf-8")
    assert (chapter / "html" / "assets" / "mathjax" / "tex-svg.js").is_file()
    assert not (chapter / "slides.html").exists()
    assert not (chapter / "frontend-assets").exists()
    assert (chapter / "slides.pdf").read_bytes() == b"%PDF-latex"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["script"] == "script.md"
    assert manifest["script_sha256"] == sha256_file(chapter / "script.md")
    assert [entry["id"] for entry in manifest["speaker_notes"]] == [
        "slide-001",
        "slide-002",
        "slide-003",
    ]


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
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: chapter / "slides.pdf",
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        "src.frontend_slides.export_html_deck",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("capture failed")),
    )

    with pytest.raises(FrontendSlidesError, match="successful artifacts were preserved"):
        finalize_chapter(course, chapter)

    assert (chapter / "slides.pdf").read_bytes() == b"%PDF-latex"
    assert (chapter / "html" / "slides.html").is_file()
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
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: chapter / "slides.pdf",
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: [],
    )

    def partial_export(_html, *, pdf_path, pptx_path):
        writer = PdfWriter()
        writer.add_blank_page(width=1920, height=1080)
        with pdf_path.open("wb") as handle:
            writer.write(handle)
        raise RuntimeError("PPTX failed")

    monkeypatch.setattr(
        "src.frontend_slides.export_html_deck", partial_export
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
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A style-only change must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: [],
    )

    def fake_export(_html, *, pdf_path, pptx_path):
        pdf_path.write_bytes(b"%PDF-html")
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.frontend_slides.export_html_deck", fake_export
    )

    result = finalize_chapter(course, chapter)

    assert result.slide_count == 3
    assert (chapter / "slides.pdf").read_bytes() == b"%PDF-latex"


def test_script_change_regenerates_html_without_recompiling_latex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    course = tmp_path / "course"
    chapter = course / "chapter_1"
    chapter.mkdir(parents=True)
    write_style(course)
    write_beamer(chapter / "slides.tex")
    (chapter / "slides.pdf").write_bytes(b"%PDF-latex")
    (chapter / "frontend-slides-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "source_sha256": sha256_file(chapter / "slides.tex"),
                "script_sha256": sha256_file(chapter / "script.md"),
                "style_sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A notes-only change must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: [],
    )
    exports = 0

    def fake_export(_html, *, pdf_path, pptx_path):
        nonlocal exports
        exports += 1
        pdf_path.write_bytes(b"%PDF-html")
        pptx_path.write_bytes(b"pptx")

    monkeypatch.setattr(
        "src.frontend_slides.export_html_deck", fake_export
    )

    finalize_chapter(course, chapter)
    script_path = chapter / "script.md"
    script_path.write_text(
        script_path.read_text(encoding="utf-8").replace(
            "Notes for the equation.", "Updated equation notes."
        ),
        encoding="utf-8",
    )
    result = finalize_chapter(course, chapter)

    assert exports == 2
    assert "Updated equation notes." in result.html_path.read_text(encoding="utf-8")
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["script_sha256"] == sha256_file(script_path)
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
    html_path = chapter / "html" / "slides.html"
    html_path.parent.mkdir()
    html_path.write_text(previous_html, encoding="utf-8")
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
        "src.frontend_slides.LaTeXCompiler.compile_one",
        lambda *_args: pytest.fail("A style-only change must not recompile LaTeX"),
    )
    monkeypatch.setattr(
        "src.frontend_slides.validate_with_playwright",
        lambda *_args: ["synthetic overflow"],
    )

    with pytest.raises(FrontendSlidesError, match="synthetic overflow"):
        finalize_chapter(course, chapter)

    assert html_path.read_text(encoding="utf-8") == previous_html
    assert not (chapter / "html" / "slides.tmp.html").exists()


@pytest.mark.playwright
def test_static_export_smoke(tmp_path: Path) -> None:
    tex = tmp_path / "slides.tex"
    write_beamer(tex)
    deck = parse_beamer(tex)
    style = make_style()
    _, font_css = prepare_offline_runtime(tmp_path, style)
    html_path = tmp_path / "html" / "slides.html"
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


@pytest.mark.playwright
def test_static_capture_freezes_slide_and_reveal_transitions(tmp_path: Path) -> None:
    html_path = tmp_path / "animated.html"
    html_path.write_text(
        """<!doctype html>
<html><head><style>
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; }
.deck-stage { position: relative; width: 1920px; height: 1080px; }
.slide {
  position: absolute; inset: 0; visibility: hidden; opacity: 0;
  transition: opacity 620ms ease; background: white;
}
.slide.visible { visibility: visible; opacity: 1; }
.reveal {
  position: absolute; inset: 0; opacity: 0;
  transition: opacity 620ms ease 500ms; background: #12ab34;
}
.slide.visible .reveal { opacity: 1; }
.slide-progress {
  position: fixed; left: 900px; bottom: 0; z-index: 1000;
  width: 120px; height: 80px; background: #ff0000;
}
</style></head><body>
<main class="deck-stage">
  <section class="slide active visible"><div class="reveal"></div></section>
  <section class="slide"><div class="reveal"></div></section>
</main>
<div class="slide-progress">transient overlay</div>
<script>
window.__slidesFitted = true;
window.presentation = {
  showSlide(index) {
    document.querySelectorAll('.slide').forEach((slide, current) => {
      slide.classList.toggle('active', current === index);
      slide.classList.toggle('visible', current === index);
    });
  }
};
</script></body></html>""",
        encoding="utf-8",
    )
    screenshot_dir = tmp_path / "screenshots"
    screenshot_dir.mkdir()
    screenshots = capture_slide_screenshots(html_path, screenshot_dir)

    with Image.open(screenshots[1]) as image:
        assert image.size == (1920, 1080)
        rgb = image.convert("RGB")
        assert rgb.getpixel((960, 540)) == (18, 171, 52)
        assert rgb.getpixel((960, 1050)) == (18, 171, 52)
