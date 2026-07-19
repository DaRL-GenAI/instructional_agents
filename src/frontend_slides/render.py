from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from pathlib import Path

from .assets import FrontendSlidesAssets
from .beamer import normalize_display_math
from .models import (
    BeamerDeck,
    BeamerSlide,
    ContentElement,
    CourseSlideStyle,
    ListItem,
    StyleCandidate,
    StylePlan,
)
from .split import expand_units
from .style import renderer_theme
from .weights import element_weight as _element_weight
from .weights import item_weight


PREVIEW_FILENAMES = {
    "style-a": "style-a.html",
    "style-b": "style-b.html",
    "style-c": "style-c.html",
}


def render_previews(
    deck: BeamerDeck,
    style_plan: StylePlan,
    assets: FrontendSlidesAssets,
    preview_dir: Path,
) -> dict[str, Path]:
    preview_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for candidate in style_plan.previews:
        filename = PREVIEW_FILENAMES.get(candidate.id, f"{candidate.id}.html")
        path = preview_dir / filename
        path.write_text(render_preview_html(deck, candidate, assets), encoding="utf-8")
        paths[candidate.id] = path
    gallery_path = preview_dir / "index.html"
    gallery_path.write_text(render_gallery_html(deck, style_plan, paths), encoding="utf-8")
    paths["gallery"] = gallery_path
    return paths


def render_preview_html(deck: BeamerDeck, candidate: StyleCandidate, assets: FrontendSlidesAssets) -> str:
    """Render a style preview as a small excerpt of the real deck.

    The preview reuses the exact presentation renderer so what the user sees in
    the gallery is what the final deck will look like in that style.
    """
    subset = _representative_slides(deck)
    preview_deck = replace(deck, slides=[replace(slide, index=i + 1) for i, slide in enumerate(subset)])
    return render_deck_html(preview_deck, candidate, assets)


def _representative_slides(deck: BeamerDeck) -> list[BeamerSlide]:
    """Pick up to three slides that showcase the style: title, a list slide, an equation slide."""
    picks: list[BeamerSlide] = []

    def add(slide: BeamerSlide | None) -> None:
        if slide is not None and slide not in picks:
            picks.append(slide)

    title = next((slide for slide in deck.slides if slide.is_titlepage), None)
    add(title or (deck.slides[0] if deck.slides else None))
    add(_first_slide_with_kind(deck, "list"))
    add(_first_slide_with_kind(deck, "equation"))
    return picks[:3]


def _first_slide_with_kind(deck: BeamerDeck, kind: str) -> BeamerSlide | None:
    for slide in deck.slides:
        if slide.is_titlepage:
            continue
        # Code slides are rendered from carbon images generated after previews,
        # so previews must not depend on them.
        if _slide_has_kind(slide, "code"):
            continue
        if _slide_has_kind(slide, kind):
            return slide
    return None


def _slide_has_kind(slide: BeamerSlide, kind: str) -> bool:
    def walk(elements: list[ContentElement]) -> bool:
        for element in elements:
            if element.kind == kind:
                return True
            if walk(element.children):
                return True
            for item in element.items:
                if walk(item.children):
                    return True
        return False

    return walk(slide.elements)


def render_gallery_html(deck: BeamerDeck, style_plan: StylePlan, paths: dict[str, Path]) -> str:
    cards = []
    for candidate in style_plan.previews:
        path = paths[candidate.id].name
        selected = " selected" if candidate.id == style_plan.selected_preview_id else ""
        label = _style_label(candidate.id)
        cards.append(
            f"""
            <article class="style-card{selected}">
                <div class="card-head">
                    <div>
                        <p>{html.escape(label)}</p>
                        <h2>{html.escape(candidate.name)}</h2>
                    </div>
                    <span>{html.escape(candidate.source.replace('_', ' '))}</span>
                </div>
                <iframe src="{html.escape(path)}" title="{html.escape(label)}"></iframe>
                <p class="rationale">{html.escape(candidate.rationale or candidate.visual_thesis)}</p>
            </article>
            """
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Style Gallery</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            min-height: 100vh;
            background: #111418;
            color: #f4f1ea;
            font-family: ui-sans-serif, system-ui, sans-serif;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            gap: 24px;
            align-items: end;
            padding: 28px 32px 10px;
        }}
        h1 {{ margin: 0; font-size: 28px; letter-spacing: 0; }}
        header p {{ margin: 8px 0 0; color: #aeb5bf; max-width: 900px; line-height: 1.45; }}
        .auto-pick {{
            border: 1px solid #c8a870;
            color: #f2dfac;
            padding: 10px 14px;
            white-space: nowrap;
        }}
        main {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 22px;
            padding: 22px 32px 34px;
        }}
        .style-card {{
            border: 1px solid rgba(255,255,255,0.18);
            background: #171b21;
            padding: 14px;
        }}
        .style-card.selected {{ border-color: #c8a870; box-shadow: 0 0 0 1px #c8a870 inset; }}
        .card-head {{ display: flex; justify-content: space-between; gap: 16px; align-items: start; margin-bottom: 12px; }}
        .card-head p {{ margin: 0 0 4px; color: #9aa3ad; font-size: 12px; text-transform: uppercase; letter-spacing: 0.12em; }}
        .card-head h2 {{ margin: 0; font-size: 19px; }}
        .card-head span {{ color: #9aa3ad; font-size: 12px; text-transform: uppercase; }}
        iframe {{
            width: 100%;
            aspect-ratio: 16 / 9;
            border: 0;
            background: #000;
            pointer-events: none;
        }}
        .rationale {{ color: #c4cbd2; font-size: 14px; line-height: 1.45; }}
        @media (max-width: 1100px) {{ main {{ grid-template-columns: 1fr; }} header {{ display: block; }} .auto-pick {{ display: inline-block; margin-top: 16px; }} }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>{html.escape(deck.title)}</h1>
            <p>Three visual directions for the Beamer source, each previewed with real slides from the deck. The workflow auto-selected the strongest fit for the final deck while keeping all {deck.slide_count} slides.</p>
        </div>
        <div class="auto-pick">Selected: {html.escape(style_plan.selected.name)}</div>
    </header>
    <main>
        {''.join(cards)}
    </main>
</body>
</html>
"""


def render_presentation_html(
    deck: BeamerDeck,
    style_plan: StylePlan,
    assets: FrontendSlidesAssets,
    selected_design_md: str | None = None,
) -> str:
    return render_deck_html(deck, style_plan.selected, assets, selected_design_md)


def render_course_presentation_html(
    deck: BeamerDeck,
    style: CourseSlideStyle,
    assets: FrontendSlidesAssets,
    *,
    font_css: str,
    mathjax_src: str = "frontend-assets/mathjax/tex-svg.js",
) -> str:
    """Render a complete offline deck from a validated course-wide style."""
    candidate = StyleCandidate(
        id="course-style",
        name=style.selected_style.name,
        source=style.selected_style.source,
        preset_name=(
            style.selected_style.name
            if style.selected_style.source == "preset"
            else None
        ),
        slug=(
            style.selected_style.key
            if style.selected_style.source == "bold_template"
            else None
        ),
        visual_thesis=style.presentation_method.narrative,
    )
    return render_deck_html(
        deck,
        candidate,
        assets,
        theme_override=renderer_theme(style),
        font_css=font_css,
        mathjax_src=mathjax_src,
        layout_rotation=style.presentation_method.layout_rotation,
    )


def render_deck_html(
    deck: BeamerDeck,
    candidate: StyleCandidate,
    assets: FrontendSlidesAssets,
    selected_design_md: str | None = None,
    *,
    theme_override: dict[str, str] | None = None,
    font_css: str | None = None,
    mathjax_src: str = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js",
    layout_rotation: list[str] | None = None,
) -> str:
    theme = theme_override or theme_for_candidate(candidate)
    slides = "\n".join(
        render_slide(deck, slide, theme, layout_rotation) for slide in deck.slides
    )
    manifest_for_page = {
        "title": deck.title,
        "slideCount": deck.slide_count,
        "style": candidate.name,
        "source": str(deck.source_path),
    }
    design_note = _design_note(selected_design_md, candidate)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(deck.title)}</title>
    {font_css if font_css is not None else _font_links(theme)}
    <script>
        window.MathJax = {{
            tex: {{ inlineMath: [['\\\\(', '\\\\)'], ['$', '$']], displayMath: [['\\\\[', '\\\\]']] }},
            svg: {{ fontCache: 'global' }}
        }};
    </script>
    <script defer src="{html.escape(mathjax_src)}"></script>
    <style>
        /* === CSS CUSTOM PROPERTIES (THEME) === */
        :root {{
            --stage-bg: {theme['stage_bg']};
            --slide-bg: {theme['background']};
            --text-primary: {theme['text']};
            --text-secondary: {theme['muted']};
            --accent: {theme['accent']};
            --accent-2: {theme['accent2']};
            --surface: {theme['surface']};
            --surface-alt: {theme['surface_alt']};
            --border: {theme['border']};
            --font-display: {theme['display_font']};
            --font-body: {theme['body_font']};
            --font-mono: {theme['mono_font']};
            --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
        }}

        /* === RESET === */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}

{_indent(assets.viewport_css, 8)}

        /* === PRESENTATION THEME === */
        body {{ color: var(--text-primary); font-family: var(--font-body); }}
        .slide {{
            background:
                radial-gradient(circle at 86% 12%, {theme['glow']} 0, transparent 330px),
                linear-gradient(135deg, {theme['background']} 0%, {theme['background_alt']} 100%);
            color: var(--text-primary);
        }}
        .slide::before {{
            content: "";
            position: absolute;
            inset: 0;
            background-image:
                linear-gradient({theme['grid']} 1px, transparent 1px),
                linear-gradient(90deg, {theme['grid']} 1px, transparent 1px);
            background-size: 80px 80px;
            opacity: {theme['grid_opacity']};
            pointer-events: none;
        }}
        .slide-frame {{
            position: absolute;
            inset: 52px 64px;
            display: grid;
            grid-template-rows: 48px minmax(0, 1fr) 40px;
            gap: 34px;
        }}
        .slide-topline,
        .slide-footline {{
            position: relative;
            z-index: 1;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: var(--text-secondary);
            border-color: var(--border);
            font-family: var(--font-mono);
            font-size: 18px;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .slide-topline {{ border-bottom: 1px solid var(--border); padding-bottom: 16px; }}
        .slide-footline {{ border-top: 1px solid var(--border); padding-top: 14px; }}

        /* === SLIDE CONTENT + LAYOUT VARIANTS === */
        .slide-content {{
            --fit-scale: 1;
            --density: {theme.get('course_density', '1')};
            position: relative;
            z-index: 1;
            display: grid;
            min-height: 0;
            overflow: hidden;
        }}
        .slide-content.compact {{ --density: 0.92; }}
        .layout-hero {{ grid-template-columns: 1fr; align-content: end; }}
        .layout-split {{
            grid-template-columns: minmax(0, 0.85fr) minmax(0, 1.15fr);
            gap: 76px;
            align-items: stretch;
        }}
        .layout-split .slide-head {{ align-self: center; }}
        .layout-top,
        .layout-top-cols,
        .layout-math {{
            grid-template-rows: auto minmax(0, 1fr);
            gap: 42px;
            align-content: start;
        }}
        .layout-top .slide-body {{ max-width: 1560px; }}
        .layout-top-cols .slide-body {{ grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px 68px; }}
        .layout-top-cols .col {{ align-content: start; }}
        .layout-math .slide-body {{ grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr); gap: 76px; }}

        /* === SLIDE HEADER === */
        .slide-head .kicker {{
            margin-bottom: 18px;
            display: inline-flex;
            align-items: center;
            gap: 14px;
            color: var(--accent);
            font-family: var(--font-mono);
            font-size: 20px;
            letter-spacing: 0.2em;
            text-transform: uppercase;
        }}
        .slide-head .kicker::before {{ content: ""; width: 40px; height: 2px; background: var(--accent); }}
        h1,
        h2 {{
            font-family: var(--font-display);
            letter-spacing: 0;
            color: var(--text-primary);
        }}
        h1 {{ font-size: {theme['title_size']}; line-height: 0.94; }}
        h2 {{ font-size: {theme['heading_size']}; line-height: 1.04; max-width: 1520px; }}
        .layout-split h2 {{ max-width: 640px; }}
        .title-lockup {{
            max-width: 1280px;
            padding-bottom: 40px;
        }}
        .title-subtitle {{
            margin-top: 30px;
            max-width: 940px;
            color: var(--text-secondary);
            font-size: 34px;
            line-height: 1.35;
        }}

        /* === SLIDE BODY (open flow, no nested boxes) === */
        .slide-body {{
            display: grid;
            gap: calc(30px * var(--fit-scale));
            align-content: safe center;
            min-height: 0;
            overflow: hidden;
        }}
        .col {{
            display: grid;
            gap: calc(30px * var(--fit-scale));
            align-content: safe center;
            min-height: 0;
        }}
        p,
        li,
        td,
        th {{
            color: var(--text-primary);
            font-size: calc(26px * var(--density) * var(--fit-scale));
            line-height: 1.45;
        }}
        .text-item {{ color: var(--text-secondary); max-width: 1400px; }}

        /* Open lists with custom accent markers */
        .blist {{ list-style: none; padding: 0; display: grid; gap: calc(18px * var(--fit-scale)); }}
        ol.blist {{ counter-reset: bitem; }}
        ol.blist > li {{ position: relative; padding-left: 2.4em; counter-increment: bitem; }}
        ol.blist > li::before {{
            content: counter(bitem, decimal-leading-zero) ".";
            position: absolute;
            left: 0;
            top: 0;
            color: var(--accent);
            font-family: var(--font-mono);
            font-weight: 700;
        }}
        ul.blist > li {{ position: relative; padding-left: 38px; }}
        ul.blist > li::before {{
            content: "";
            position: absolute;
            left: 2px;
            top: 0.42em;
            width: 12px;
            height: 12px;
            border: 2px solid var(--accent);
            transform: rotate(45deg);
        }}
        li .blist {{ margin-top: calc(12px * var(--fit-scale)); gap: calc(11px * var(--fit-scale)); }}
        li ul.blist {{ padding-left: 4px; }}
        li ul.blist > li {{ padding-left: 30px; }}
        li ul.blist > li::before {{
            left: 4px;
            top: 0.5em;
            width: 8px;
            height: 8px;
            border-color: var(--accent-2);
            border-radius: 2px;
            transform: none;
        }}
        li ol.blist > li {{ padding-left: 1.7em; }}
        li ol.blist > li::before {{ content: counter(bitem) "."; }}
        li li {{ font-size: 0.86em; color: var(--text-secondary); }}
        strong {{ color: var(--accent); font-weight: 800; }}
        mark {{ background: color-mix(in srgb, var(--accent) 35%, transparent); color: inherit; padding: 0 0.15em; }}

        /* Beamer block: accent-edged section, not a box of boxes */
        .content-block {{
            border-left: 4px solid var(--accent);
            padding: 8px 0 8px 30px;
            display: grid;
            gap: calc(18px * var(--fit-scale));
        }}
        .content-block h3 {{
            color: var(--accent);
            font-family: var(--font-display);
            font-size: calc(31px * var(--density) * var(--fit-scale));
            line-height: 1.12;
        }}

        /* Cards: only equations, code, tables and raw LaTeX earn a surface */
        .formula,
        .code-card,
        .table-card,
        .raw-card {{
            background: {theme['panel_fill']};
            border: {theme['panel_border']};
            box-shadow: {theme['shadow']};
            padding: calc(26px * var(--fit-scale)) calc(34px * var(--fit-scale));
            overflow: hidden;
        }}
        .formula {{
            border-left: 4px solid var(--accent);
            color: var(--text-primary);
            font-size: calc(27px * var(--density) * var(--fit-scale));
        }}
        .code-card--image {{
            background: transparent;
            border: 0;
            box-shadow: none;
            padding: 0;
        }}
        .code-card--image img {{
            display: block;
            margin: 0 auto;
            max-width: 100%;
            max-height: calc(480px * var(--fit-scale));
            width: auto;
            height: auto;
            object-fit: contain;
        }}
        .gen-image-card {{ margin: 0; }}
        .gen-image-card img {{
            display: block;
            margin: 0 auto;
            max-width: 100%;
            max-height: calc(460px * var(--fit-scale));
            width: auto;
            height: auto;
            object-fit: contain;
            border-radius: 14px;
            border: 1px solid var(--border);
            box-shadow: {theme['shadow']};
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }}
        th,
        td {{
            border-bottom: 1px solid var(--border);
            padding: 12px 10px;
            text-align: left;
            vertical-align: top;
            overflow-wrap: anywhere;
        }}
        tr:last-child td {{ border-bottom: 0; }}
        pre {{
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            color: var(--text-primary);
            font-family: var(--font-mono);
            font-size: calc(19px * var(--density) * var(--fit-scale));
            line-height: 1.4;
        }}
        .raw-card h3 {{
            margin-bottom: 12px;
            color: var(--accent);
            font-family: var(--font-mono);
            font-size: calc(18px * var(--fit-scale));
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }}
        .raw-card pre {{ color: var(--text-secondary); }}
        .slide-progress {{
            position: fixed;
            left: 50%;
            bottom: 22px;
            transform: translateX(-50%);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px;
            border-radius: 999px;
            background: rgba(0, 0, 0, 0.72);
            color: #fff;
            font: 13px/1 var(--font-mono);
            letter-spacing: 0.02em;
            opacity: 0;
            pointer-events: none;
            transition: opacity 220ms ease;
        }}
        .slide-progress.visible {{ opacity: 1; }}
        .edit-hotzone {{
            position: fixed;
            top: 0;
            left: 0;
            width: 80px;
            height: 80px;
            z-index: 10000;
        }}
        .edit-toggle {{
            position: fixed;
            top: 18px;
            left: 18px;
            z-index: 10001;
            width: 42px;
            height: 42px;
            border: 1px solid rgba(255,255,255,0.3);
            border-radius: 999px;
            background: rgba(0,0,0,0.78);
            color: #fff;
            opacity: 0;
            pointer-events: none;
            transition: opacity 180ms ease;
        }}
        .edit-toggle.show,
        .edit-toggle.active {{
            opacity: 1;
            pointer-events: auto;
        }}
        body.editing [data-editable] {{
            outline: 2px dashed var(--accent);
            outline-offset: 5px;
            cursor: text;
        }}

        /* === ENTRANCE ANIMATIONS === */
        .reveal {{
            opacity: 0;
            transform: translateY(26px);
            transition: opacity 620ms var(--ease-out-expo), transform 620ms var(--ease-out-expo);
        }}
        .slide.visible .reveal {{
            opacity: 1;
            transform: translateY(0);
        }}
        .slide.visible .reveal:nth-child(1) {{ transition-delay: 80ms; }}
        .slide.visible .reveal:nth-child(2) {{ transition-delay: 150ms; }}
        .slide.visible .reveal:nth-child(3) {{ transition-delay: 220ms; }}
        .slide.visible .reveal:nth-child(4) {{ transition-delay: 290ms; }}
        .slide.visible .reveal:nth-child(5) {{ transition-delay: 360ms; }}
        .slide.visible .reveal:nth-child(6) {{ transition-delay: 430ms; }}
        .slide.visible .reveal:nth-child(n+7) {{ transition-delay: 500ms; }}
    </style>
</head>
<body>
    <!-- Design recipe: {html.escape(design_note)} -->
    <div class="deck-viewport">
        <main class="deck-stage" id="deckStage" aria-label="{html.escape(deck.title)}">
{slides}
        </main>
    </div>
    <div class="slide-progress" id="slideProgress" aria-live="polite"></div>
    <div class="edit-hotzone" aria-hidden="true"></div>
    <button class="edit-toggle" id="editToggle" type="button" title="Edit mode (E)" aria-label="Toggle edit mode">E</button>
    <script type="application/json" id="deck-manifest">{html.escape(json.dumps(manifest_for_page))}</script>
    <script>
        /* === SLIDE PRESENTATION CONTROLLER === */
        class SlidePresentation {{
            constructor() {{
                this.slides = Array.from(document.querySelectorAll('.slide'));
                this.currentSlide = 0;
                this.stage = document.getElementById('deckStage');
                this.progress = document.getElementById('slideProgress');
                this.wheelLock = false;
                this.hideTimer = null;
                this.setupStageScale();
                this.setupKeyboardNav();
                this.setupTouchNav();
                this.setupWheelNav();
                this.showSlide(0);
            }}
            setupStageScale() {{
                const scale = () => {{
                    const factor = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
                    const x = (window.innerWidth - 1920 * factor) / 2;
                    const y = (window.innerHeight - 1080 * factor) / 2;
                    this.stage.style.transform = `translate(${{x}}px, ${{y}}px) scale(${{factor}})`;
                }};
                scale();
                window.addEventListener('resize', scale);
            }}
            setupKeyboardNav() {{
                document.addEventListener('keydown', (event) => {{
                    if (event.target && event.target.isContentEditable) return;
                    if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') {{
                        event.preventDefault();
                        this.next();
                    }} else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {{
                        event.preventDefault();
                        this.prev();
                    }} else if (event.key === 'Home') {{
                        event.preventDefault();
                        this.showSlide(0);
                    }} else if (event.key === 'End') {{
                        event.preventDefault();
                        this.showSlide(this.slides.length - 1);
                    }}
                }});
            }}
            setupTouchNav() {{
                let startX = 0;
                document.addEventListener('touchstart', (event) => {{
                    startX = event.changedTouches[0].clientX;
                }}, {{ passive: true }});
                document.addEventListener('touchend', (event) => {{
                    const delta = event.changedTouches[0].clientX - startX;
                    if (Math.abs(delta) > 48) delta < 0 ? this.next() : this.prev();
                }}, {{ passive: true }});
            }}
            setupWheelNav() {{
                document.addEventListener('wheel', (event) => {{
                    if (this.wheelLock || Math.abs(event.deltaY) < 42) return;
                    this.wheelLock = true;
                    event.deltaY > 0 ? this.next() : this.prev();
                    setTimeout(() => {{ this.wheelLock = false; }}, 420);
                }}, {{ passive: true }});
            }}
            showSlide(index) {{
                this.currentSlide = Math.max(0, Math.min(index, this.slides.length - 1));
                this.slides.forEach((slide, i) => {{
                    slide.classList.toggle('active', i === this.currentSlide);
                    slide.classList.toggle('visible', i === this.currentSlide);
                }});
                this.progress.textContent = `${{this.currentSlide + 1}} / ${{this.slides.length}}`;
                this.progress.classList.add('visible');
                clearTimeout(this.hideTimer);
                this.hideTimer = setTimeout(() => this.progress.classList.remove('visible'), 1400);
                const slide = this.slides[this.currentSlide];
                if (window.MathJax && window.MathJax.typesetPromise) {{
                    window.MathJax.typesetPromise([slide]).then(() => fitSlide(slide)).catch(() => {{}});
                }}
            }}
            next() {{ this.showSlide(this.currentSlide + 1); }}
            prev() {{ this.showSlide(this.currentSlide - 1); }}
        }}

        /* === INLINE EDITING CONTROLLER === */
        class InlineEditor {{
            constructor() {{
                this.isActive = false;
                this.key = `agentic-slides:${{location.pathname}}`;
                this.toggle = document.getElementById('editToggle');
                this.hotzone = document.querySelector('.edit-hotzone');
                this.hideTimeout = null;
                this.load();
                this.setup();
            }}
            setup() {{
                this.toggle.addEventListener('click', () => this.toggleEditMode());
                this.hotzone.addEventListener('mouseenter', () => {{
                    clearTimeout(this.hideTimeout);
                    this.toggle.classList.add('show');
                }});
                this.hotzone.addEventListener('mouseleave', () => {{
                    this.hideTimeout = setTimeout(() => {{
                        if (!this.isActive) this.toggle.classList.remove('show');
                    }}, 400);
                }});
                this.toggle.addEventListener('mouseenter', () => clearTimeout(this.hideTimeout));
                this.toggle.addEventListener('mouseleave', () => {{
                    this.hideTimeout = setTimeout(() => {{
                        if (!this.isActive) this.toggle.classList.remove('show');
                    }}, 400);
                }});
                document.addEventListener('keydown', (event) => {{
                    if ((event.key === 'e' || event.key === 'E') && !(event.target && event.target.isContentEditable)) {{
                        this.toggleEditMode();
                    }}
                    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {{
                        event.preventDefault();
                        this.save();
                    }}
                }});
                document.addEventListener('input', (event) => {{
                    if (event.target && event.target.matches('[data-editable]')) this.save();
                }});
            }}
            toggleEditMode() {{
                this.isActive = !this.isActive;
                document.body.classList.toggle('editing', this.isActive);
                this.toggle.classList.toggle('active', this.isActive);
                this.toggle.classList.add('show');
                document.querySelectorAll('[data-editable]').forEach((node) => {{
                    node.contentEditable = this.isActive ? 'true' : 'false';
                }});
            }}
            save() {{
                const values = Array.from(document.querySelectorAll('[data-editable]')).map((node) => node.innerHTML);
                localStorage.setItem(this.key, JSON.stringify(values));
            }}
            load() {{
                try {{
                    const values = JSON.parse(localStorage.getItem(this.key) || '[]');
                    document.querySelectorAll('[data-editable]').forEach((node, index) => {{
                        if (values[index]) node.innerHTML = values[index];
                    }});
                }} catch (error) {{}}
            }}
        }}

        /* === OVERFLOW AUTO-FIT ===
           Overloaded frames are split into multiple slides at build time, so this
           only needs to absorb small residual overflows. The 0.80 floor keeps body
           text at readable size (roughly 19-21px minimum). */
        function fitSlide(slide) {{
            const content = slide.querySelector('.slide-content');
            const body = slide.querySelector('.slide-body');
            if (!content || !body) return;
            content.style.removeProperty('--fit-scale');
            const images = slide.querySelectorAll('.gen-image-card img');
            images.forEach((img) => img.style.removeProperty('max-height'));
            let scale = 1;
            const overflowing = () =>
                body.scrollHeight - body.clientHeight > 2 ||
                content.scrollHeight - content.clientHeight > 2;
            while (overflowing() && scale > 0.8) {{
                scale = Math.round((scale - 0.04) * 100) / 100;
                content.style.setProperty('--fit-scale', scale);
            }}
            /* Text stops at the readability floor; attached figures are
               supplementary, so they keep shrinking to absorb the rest. */
            let imageMax = 460 * scale;
            while (overflowing() && images.length && imageMax > 160) {{
                imageMax -= 20;
                images.forEach((img) => {{ img.style.maxHeight = imageMax + 'px'; }});
            }}
        }}
        function fitAllSlides() {{
            document.querySelectorAll('.slide').forEach(fitSlide);
        }}
        window.__fitAllSlides = fitAllSlides;

        window.presentation = new SlidePresentation();
        window.inlineEditor = new InlineEditor();

        window.addEventListener('load', () => {{
            const run = () => {{
                fitAllSlides();
                window.__slidesFitted = true;
            }};
            const fonts = document.fonts ? document.fonts.ready : Promise.resolve();
            fonts.then(() => {{
                if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) {{
                    window.MathJax.startup.promise
                        .then(() => window.MathJax.typesetPromise())
                        .then(run)
                        .catch(run);
                }} else {{
                    run();
                }}
            }}).catch(run);
        }});
    </script>
</body>
</html>
"""


def render_slide(
    deck: BeamerDeck,
    slide: BeamerSlide,
    theme: dict[str, str],
    layout_rotation: list[str] | None = None,
) -> str:
    if slide.is_titlepage:
        subtitle = _preview_subtitle(deck)
        return f"""            <section class="slide title-slide active visible" data-slide-index="{slide.index}">
                <div class="slide-frame">
                    <div class="slide-topline reveal"><span>{html.escape(_deck_chrome(deck))}</span><span>{deck.slide_count:02d} slides</span></div>
                    <div class="slide-content layout-hero">
                        <div class="title-lockup">
                            <h1 class="reveal" data-editable>{html.escape(deck.title)}</h1>
                            <p class="title-subtitle reveal" data-editable>{html.escape(subtitle)}</p>
                        </div>
                    </div>
                    <div class="slide-footline reveal"><span>{html.escape(_short_kicker(deck))}</span><span>{slide.index:02d} / {deck.slide_count:02d}</span></div>
                </div>
            </section>"""

    layout = choose_layout(slide, layout_rotation)
    compact = _is_compact_slide(slide)
    content_class = f"slide-content layout-{layout}" + (" compact" if compact else "")
    body = _render_body(slide, layout)
    return f"""            <section class="slide content-slide" data-slide-index="{slide.index}">
                <div class="slide-frame">
                    <div class="slide-topline reveal"><span>{html.escape(_deck_chrome(deck))}</span><span>{slide.index:02d} / {deck.slide_count:02d}</span></div>
                    <div class="{content_class}">
                        {_render_head(slide)}
                        {body}
                    </div>
                    <div class="slide-footline reveal"><span>{html.escape(_short_kicker(deck))}</span><span>{html.escape(deck.title[:36])}</span></div>
                </div>
            </section>"""


def choose_layout(
    slide: BeamerSlide, layout_rotation: list[str] | None = None
) -> str:
    """Pick a per-slide layout so the deck has visual rhythm instead of one template.

    - "split": light slides keep the title-left / content-right look.
    - "math": slides with top-level equations put prose left, formulas right.
    - "top-cols": dense slides get a full-width header and a two-column body.
    - "top": everything in between - full-width header, single column below.
    """
    weight = sum(_element_weight(element) for element in slide.elements)
    main, equations = _partition_equations(slide.elements)
    if equations and main and sum(_element_weight(element) for element in main) <= 12:
        natural = "math"
    elif weight <= 5 and len(slide.elements) <= 2:
        natural = "split"
    elif weight > 9 or len(slide.elements) > 3 or _dominant_list_size(slide) >= 4:
        natural = "top-cols"
    else:
        natural = "top"
    if not layout_rotation:
        return natural
    allowed = [
        {"columns": "top-cols"}.get(layout, layout)
        for layout in layout_rotation
        if layout != "hero"
    ]
    if natural in allowed:
        return natural
    for fallback in ("top", "top-cols", "split", "math"):
        if fallback in allowed:
            return fallback
    return natural


def _partition_equations(elements: list[ContentElement]) -> tuple[list[ContentElement], list[ContentElement]]:
    """Hoist equations that sit at the top level or directly inside top-level blocks.

    Deeply nested equations (inside list items) stay in place so content order is preserved.
    """
    main: list[ContentElement] = []
    equations: list[ContentElement] = []
    for element in elements:
        if element.kind == "equation":
            equations.append(element)
        elif element.kind == "block" and any(child.kind == "equation" for child in element.children):
            kept = [child for child in element.children if child.kind != "equation"]
            equations.extend(child for child in element.children if child.kind == "equation")
            if kept or element.title:
                main.append(replace(element, children=kept))
        else:
            main.append(element)
    return main, equations


def _dominant_list_size(slide: BeamerSlide) -> int:
    return max((len(element.items) for element in slide.elements if element.kind == "list"), default=0)


def _render_head(slide: BeamerSlide) -> str:
    kicker, title = _split_title(slide.title or f"Slide {slide.index}")
    kicker_html = f'<p class="kicker" data-editable>{html.escape(kicker)}</p>' if kicker else ""
    return f"""<header class="slide-head reveal">
                            {kicker_html}
                            <h2 data-editable>{html.escape(title)}</h2>
                        </header>"""


def _split_title(title: str) -> tuple[str, str]:
    parts = re.split(r"\s+[-–—]\s+", title, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return "", title


def _render_body(slide: BeamerSlide, layout: str) -> str:
    elements = slide.elements
    if not elements:
        return '<div class="slide-body reveal"><p data-editable></p></div>'
    if layout == "math":
        main, aside = _partition_equations(elements)
        return (
            '<div class="slide-body">'
            f'<div class="col reveal">{_render_elements(main)}</div>'
            f'<div class="col col-aside reveal">{_render_elements(aside)}</div>'
            "</div>"
        )
    if layout == "top-cols":
        left, right = _split_columns(elements)
        return (
            '<div class="slide-body">'
            f'<div class="col reveal">{_render_elements(left)}</div>'
            f'<div class="col reveal">{_render_elements(right)}</div>'
            "</div>"
        )
    rendered = "\n".join(f'<div class="reveal">{render_element(element)}</div>' for element in elements)
    return f'<div class="slide-body">{rendered}</div>'


def _render_elements(elements: list[ContentElement]) -> str:
    return "\n".join(render_element(element) for element in elements)


def _split_columns(elements: list[ContentElement]) -> tuple[list[ContentElement], list[ContentElement]]:
    """Distribute elements over two columns, splitting a dominant list by items."""
    if len(elements) == 1 and elements[0].kind == "list" and len(elements[0].items) >= 2:
        return _split_list(elements[0])
    if len(elements) == 1:
        # A lone block (or similar) would leave the second column empty; break it
        # into its constituent pieces so both columns carry content.
        expanded = expand_units(elements[0])
        if len(expanded) >= 2:
            elements = expanded
    weights = [_element_weight(element) for element in elements]
    total = sum(weights)
    best_index, best_gap = 1, total
    for index in range(1, len(elements)):
        gap = abs(sum(weights[:index]) - sum(weights[index:]))
        if gap < best_gap:
            best_index, best_gap = index, gap
    left, right = elements[:best_index], elements[best_index:]
    if len(left) == 1 and left[0].kind == "list" and len(left[0].items) >= 4 and not right:
        return _split_list(left[0])
    if not right:
        return _split_columns_fallback(elements)
    return left, right


def _split_list(element: ContentElement) -> tuple[list[ContentElement], list[ContentElement]]:
    items = element.items
    weights = [item_weight(item) for item in items]
    total = sum(weights)
    mid, best_gap, running = 1, total, 0
    for index in range(1, len(items)):
        running += weights[index - 1]
        gap = abs(running - (total - running))
        if gap < best_gap:
            mid, best_gap = index, gap
    first = replace(element, items=items[:mid])
    second = replace(element, items=items[mid:], start=element.start + mid if element.ordered else 1)
    return [first], [second]


def _split_columns_fallback(elements: list[ContentElement]) -> tuple[list[ContentElement], list[ContentElement]]:
    mid = (len(elements) + 1) // 2
    return elements[:mid], elements[mid:]


_ALIGNMENT_SAFE_ENV_RE = re.compile(r"\\begin\{(aligned|alignedat|gathered|cases|array|[A-Za-z]*matrix)\*?\}")
_UNESCAPED_AMP_RE = re.compile(r"(?<!\\)&")


def _display_wrapper_for(env: str | None, body: str) -> str | None:
    """Pick the env needed to make an equation body valid inside \\[...\\] display math."""
    base = (env or "").rstrip("*")
    if base in {"align", "alignat", "flalign", "eqnarray"}:
        return "aligned"
    if base in {"gather", "multline"}:
        return "gathered"
    if _UNESCAPED_AMP_RE.search(body) and not _ALIGNMENT_SAFE_ENV_RE.search(body):
        # Alignment markers with no alignment environment would raise "Misplaced &".
        return "aligned"
    return None


def render_element(element: ContentElement) -> str:
    if element.kind == "text":
        return f'<p class="text-item" data-editable>{_inline_html(element.text)}</p>'
    if element.kind == "block":
        title = f"<h3 data-editable>{html.escape(element.title or 'Note')}</h3>"
        children = "\n".join(render_element(child) for child in element.children)
        if not children and element.raw:
            children = f"<p data-editable>{_inline_html(element.raw)}</p>"
        return f'<section class="content-block">{title}{children}</section>'
    if element.kind == "list":
        tag = "ol" if element.ordered else "ul"
        start = ""
        if element.ordered and element.start > 1:
            start = f' start="{element.start}" style="counter-reset: bitem {element.start - 1}"'
        return f'<{tag} class="blist"{start}>{_render_items(element.items)}</{tag}>'
    if element.kind == "equation":
        body = normalize_display_math(element.text.strip())
        wrapper = _display_wrapper_for(element.env, body)
        equation = html.escape(body)
        if wrapper:
            equation = f"\\begin{{{wrapper}}}{equation}\\end{{{wrapper}}}"
        return f'<div class="formula" data-editable>\\[{equation}\\]</div>'
    if element.kind == "table":
        return f'<div class="table-card">{_render_table(element.rows)}</div>'
    if element.kind == "code":
        if element.image_data_uri:
            label = html.escape(element.language or "code")
            return f'<figure class="code-card code-card--image"><img src="{element.image_data_uri}" alt="{label} snippet"></figure>'
        language = f" data-language=\"{html.escape(element.language)}\"" if element.language else ""
        return f'<div class="code-card"><pre{language} data-editable><code>{html.escape(element.text)}</code></pre></div>'
    if element.kind == "raw":
        label = html.escape(element.title or "LaTeX")
        return f'<div class="raw-card"><h3>{label}</h3><pre data-editable>{html.escape(element.raw)}</pre></div>'
    if element.kind in {"generated_image", "user_image"}:
        if not element.image_data_uri:
            return ""
        fallback = "Generated illustration" if element.kind == "generated_image" else "Provided image"
        alt = html.escape(element.title or fallback)
        return f'<figure class="gen-image-card"><img src="{element.image_data_uri}" alt="{alt}"></figure>'
    return f'<div class="raw-card"><pre data-editable>{html.escape(element.raw or element.text)}</pre></div>'


def theme_for_candidate(candidate: StyleCandidate) -> dict[str, str]:
    name_key = (candidate.slug or candidate.preset_name or candidate.name).lower()
    base = {
        "stage_bg": "#0c1016",
        "background": "#121821",
        "background_alt": "#1a2431",
        "text": "#f3efe6",
        "muted": "#aeb7c4",
        "accent": "#c8a870",
        "accent2": "#73d2de",
        "surface": "#f0ece3",
        "surface_alt": "#242f3f",
        "border": "rgba(232, 224, 210, 0.22)",
        "glow": "rgba(200, 168, 112, 0.23)",
        "grid": "rgba(255,255,255,0.05)",
        "grid_opacity": "0.55",
        "display_font": "'Source Serif 4', serif",
        "body_font": "'DM Sans', sans-serif",
        "mono_font": "'IBM Plex Mono', monospace",
        "title_size": "118px",
        "heading_size": "68px",
        "panel_border": "1px solid var(--border)",
        "panel_fill": "rgba(240, 236, 227, 0.08)",
        "shadow": "none",
        "carbon_theme": "nord",
        "carbon_background": "rgba(0,0,0,0)",
    }
    if "swiss" in name_key:
        base.update(
            background="#fbfaf7",
            background_alt="#f1f0ea",
            stage_bg="#e6e2d7",
            text="#101010",
            muted="#555b64",
            accent="#ff3300",
            accent2="#111111",
            surface="#ffffff",
            surface_alt="#ece9de",
            border="#111111",
            glow="rgba(255, 51, 0, 0.18)",
            grid="rgba(0,0,0,0.06)",
            display_font="'Archivo', sans-serif",
            body_font="'Nunito', sans-serif",
            mono_font="'IBM Plex Mono', monospace",
            panel_border="2px solid var(--border)",
            panel_fill="#ffffff",
            carbon_theme="one-light",
            carbon_background="rgba(255,255,255,1)",
        )
    elif "paper" in name_key or "cartesian" in name_key or "vellum" in name_key:
        base.update(
            background="#faf7ef",
            background_alt="#ece4d5",
            stage_bg="#161616",
            text="#1f1b17",
            muted="#6c6255",
            accent="#9e1f2f",
            accent2="#184e77",
            surface="#fffdf7",
            surface_alt="#efe7d6",
            border="#c9bda8",
            glow="rgba(158, 31, 47, 0.12)",
            grid="rgba(31,27,23,0.07)",
            display_font="'Cormorant Garamond', serif",
            body_font="'Source Serif 4', serif",
            mono_font="'IBM Plex Mono', monospace",
            panel_border="1px solid var(--border)",
            panel_fill="rgba(255, 253, 247, 0.88)",
            title_size="112px",
            heading_size="64px",
            carbon_theme="solarized light",
            carbon_background="rgba(0,0,0,0)",
        )
    elif "cobalt" in name_key:
        base.update(
            background="#f7f0df",
            background_alt="#eee2c9",
            stage_bg="#14171d",
            text="#1438ff",
            muted="#3b50a0",
            accent="#1438ff",
            accent2="#0b0d18",
            surface="#fffaf0",
            surface_alt="#e7ddc6",
            border="rgba(20, 56, 255, 0.36)",
            glow="rgba(20, 56, 255, 0.12)",
            grid="rgba(20,56,255,0.16)",
            display_font="'Playfair Display', serif",
            body_font="'IBM Plex Sans', sans-serif",
            mono_font="'IBM Plex Mono', monospace",
            panel_border="1px solid var(--border)",
            panel_fill="rgba(255, 250, 240, 0.84)",
            carbon_theme="cobalt",
            carbon_background="rgba(255,250,240,1)",
        )
    elif "block" in name_key or "neo-grid" in name_key or "raw-grid" in name_key:
        base.update(
            background="#fffdf5",
            background_alt="#f8f0d0",
            stage_bg="#111111",
            text="#000000",
            muted="#303030",
            accent="#fe90e8",
            accent2="#1438ff",
            surface="#f7cb46",
            surface_alt="#c0f7fe",
            border="#000000",
            glow="rgba(254, 144, 232, 0.2)",
            grid="rgba(0,0,0,0.08)",
            display_font="'Archivo Black', sans-serif",
            body_font="'Space Grotesk', sans-serif",
            mono_font="'Space Grotesk', monospace",
            panel_border="3px solid var(--border)",
            panel_fill="#ffffff",
            shadow="8px 8px 0 #000",
            title_size="106px",
            heading_size="62px",
            carbon_theme="one-light",
            carbon_background="rgba(255,255,255,1)",
        )
    elif "studio" in name_key or "bold signal" in name_key:
        base.update(
            background="#050505",
            background_alt="#191919",
            stage_bg="#000000",
            text="#f4f1e8",
            muted="#a9a9a0",
            accent="#eaff00",
            accent2="#ff5722",
            surface="#eaff00",
            surface_alt="#202020",
            border="rgba(234, 255, 0, 0.32)",
            glow="rgba(234, 255, 0, 0.2)",
            grid="rgba(234,255,0,0.08)",
            display_font="'Archivo Black', sans-serif",
            body_font="'Space Grotesk', sans-serif",
            mono_font="'IBM Plex Mono', monospace",
            carbon_theme="seti",
            carbon_background="rgba(0,0,0,0)",
        )
    elif "chalkboard" in name_key or "vector" in name_key:
        base.update(
            background="#14231b",
            background_alt="#0d1812",
            stage_bg="#080f0b",
            text="#f2f5ee",
            muted="#a8bcab",
            accent="#ffd66b",
            accent2="#8fd0ff",
            surface="#1b2f24",
            surface_alt="#22392c",
            border="rgba(242, 245, 238, 0.28)",
            glow="rgba(255, 214, 107, 0.16)",
            grid="rgba(242,245,238,0.07)",
            display_font="'Space Grotesk', sans-serif",
            body_font="'Nunito', sans-serif",
            mono_font="'IBM Plex Mono', monospace",
            panel_border="1px dashed var(--border)",
            panel_fill="rgba(242, 245, 238, 0.06)",
            carbon_theme="nord",
            carbon_background="rgba(0,0,0,0)",
        )
    return base


def _font_links(theme: dict[str, str]) -> str:
    return (
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '    <link href="https://fonts.googleapis.com/css2?'
        'family=Archivo:wght@700;800;900&family=Archivo+Black&family=Cormorant+Garamond:wght@400;600;700&'
        'family=DM+Sans:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;700&family=IBM+Plex+Sans:wght@400;500;700&'
        'family=Nunito:wght@400;500;700&family=Playfair+Display:wght@600;700&family=Source+Serif+4:wght@400;600;700&'
        'family=Space+Grotesk:wght@400;500;700&display=swap" rel="stylesheet">'
    )


def _render_items(items: list[ListItem]) -> str:
    rendered = []
    for item in items:
        children = "\n".join(render_element(child) for child in item.children)
        rendered.append(f"<li data-editable>{_inline_html(item.text)}{children}</li>")
    return "\n".join(rendered)


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return "<pre data-editable></pre>"
    body = []
    for row in rows:
        cells = "".join(f"<td data-editable>{_inline_html(cell)}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table>{''.join(body)}</table>"


_INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)|\\\[(.+?)\\\]", re.DOTALL)
_INLINE_MATH_TOKEN_RE = re.compile("(\\d+)")


def _inline_html(text: str) -> str:
    # Protect MathJax spans so escaping and the markdown-ish regexes below
    # cannot mangle TeX such as `x^*` or `a * b`.
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        spans.append(match.group(0))
        return f"{len(spans) - 1}"

    text = _INLINE_MATH_RE.sub(stash, text)
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    escaped = escaped.replace("\n", "<br>")
    return _INLINE_MATH_TOKEN_RE.sub(lambda match: html.escape(spans[int(match.group(1))]), escaped)


def _is_compact_slide(slide: BeamerSlide) -> bool:
    total = sum(_element_weight(element) for element in slide.elements)
    return total > 9 or len(slide.elements) > 3


def _preview_subtitle(deck: BeamerDeck) -> str:
    for slide in deck.slides:
        if slide.is_titlepage:
            continue
        if slide.title and slide.title != deck.title:
            return slide.title
    return "A faithful interactive HTML version of the source Beamer deck"


def _short_kicker(deck: BeamerDeck) -> str:
    stem = deck.source_path.stem.replace("-", " ").title()
    return stem[:32]


def _deck_chrome(deck: BeamerDeck) -> str:
    return deck.metadata.get("author") or deck.source_path.stem.replace("-", " ").title()


def _style_label(candidate_id: str) -> str:
    return {"style-a": "Style A", "style-b": "Style B", "style-c": "Style C"}.get(candidate_id, candidate_id)


def _design_note(selected_design_md: str | None, candidate: StyleCandidate) -> str:
    if selected_design_md:
        first_line = next((line.strip("#- ") for line in selected_design_md.splitlines() if line.strip()), "")
        return f"{candidate.name}; selected bold template design doc loaded; {first_line[:120]}"
    return f"{candidate.name}; generated/custom style recipe"


def _indent(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else "" for line in text.splitlines())
