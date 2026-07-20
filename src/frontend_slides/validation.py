from __future__ import annotations

import re
from pathlib import Path


def validate_html_contract(html: str, expected_slide_count: int, viewport_css: str) -> list[str]:
    errors: list[str] = []
    slide_count = len(re.findall(r"<section\s+class=\"[^\"]*\bslide\b", html))
    if slide_count != expected_slide_count:
        errors.append(f"Expected {expected_slide_count} .slide sections, found {slide_count}.")
    if "tex-svg.js" not in html or "MathJax" not in html:
        errors.append("MathJax configuration is missing.")
    viewport_probe = "FIXED 16:9 STAGE: MANDATORY BASE STYLES"
    if viewport_probe not in html or viewport_probe not in viewport_css:
        errors.append("Full viewport-base.css contents do not appear to be included.")
    if re.search(r"\.slide[^{]*\{[^}]*display\s*:\s*none", html, flags=re.IGNORECASE | re.DOTALL):
        errors.append("Slide switching must not use display:none.")
    if "width: 1920px" not in html or "height: 1080px" not in html:
        errors.append("Fixed 1920x1080 stage dimensions are missing.")
    errors.extend(validate_math_syntax(html))
    return errors


def validate_offline_contract(html: str) -> list[str]:
    errors: list[str] = []
    if re.search(r"(?:src|href)\s*=\s*[\"']https?://", html, flags=re.IGNORECASE):
        errors.append("Offline slides must not load scripts, styles, fonts, or images over HTTP.")
    required = (
        "assets/mathjax/tex-svg.js",
        "assets/fonts/",
    )
    for reference in required:
        if reference not in html:
            errors.append(f"Offline runtime reference is missing: {reference}")
    return errors


_MARKUP_BLOCK_RE = re.compile(r"<script.*?</script>|<style.*?</style>", re.DOTALL | re.IGNORECASE)
_MATH_SPAN_RE = re.compile(r"\\\[(.*?)\\\]|\\\((.*?)\\\)", re.DOTALL)
# Top-level-only environments: MathJax raises "Erroneous nesting" for these inside \[...\].
_BAD_NESTED_ENV_RE = re.compile(r"\\begin\{(align|alignat|flalign|eqnarray|gather|multline|equation)\*?\}")
# Environments that legitimately host & alignment markers inside display math.
_ALIGNMENT_HOST_ENV_RE = re.compile(r"\\begin\{(aligned|alignedat|gathered|cases|array|[A-Za-z]*matrix)\*?\}")
# In rendered HTML the TeX & appears as &amp;.
_UNESCAPED_AMP_ENTITY_RE = re.compile(r"(?<!\\)&amp;")


def validate_math_syntax(html: str) -> list[str]:
    """Statically reject TeX that MathJax is guaranteed to render as an error box."""
    errors: list[str] = []
    visible = _MARKUP_BLOCK_RE.sub("", html)
    for match in _MATH_SPAN_RE.finditer(visible):
        body = match.group(1) or match.group(2) or ""
        excerpt = " ".join(body.split())[:90]
        bad_env = _BAD_NESTED_ENV_RE.search(body)
        if bad_env:
            errors.append(
                f"Math span nests \\begin{{{bad_env.group(1)}}}, which MathJax rejects"
                f" inside \\[...\\]: {excerpt!r}"
            )
        elif _UNESCAPED_AMP_ENTITY_RE.search(body) and not _ALIGNMENT_HOST_ENV_RE.search(body):
            errors.append(
                f"Math span uses '&' alignment without an alignment environment"
                f" (MathJax 'Misplaced &'): {excerpt!r}"
            )
    return errors


def validate_preview_authenticity(html: str) -> list[str]:
    forbidden = [
        "preview.md",
        "generated from",
        "template.html",
        "style option",
        "Option A",
        "Option B",
        "Option C",
    ]
    visibleish = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return [f"Preview contains forbidden workflow label: {word}" for word in forbidden if word.lower() in visibleish.lower()]


def validate_with_playwright(html_path: Path, expected_slide_count: int) -> list[str]:
    """Best-effort visual validation. Returns a skip-style warning if browsers are unavailable."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return [f"Playwright import unavailable: {exc}"]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(html_path.resolve().as_uri())
            page.wait_for_load_state("load")
            try:
                page.wait_for_function("window.__slidesFitted === true", timeout=20000)
            except Exception:
                pass  # older decks without the auto-fit hook; probe re-runs fit itself
            slide_count = page.locator(".slide").count()
            visible_count = page.locator(".slide.visible").count()
            stage_box = page.locator(".deck-stage").bounding_box()
            overflowing = page.evaluate(_OVERFLOW_PROBE_JS)
            math_errors = page.evaluate(_MATHJAX_ERROR_PROBE_JS)
            browser.close()
    except PlaywrightError as exc:
        return [f"Playwright browser unavailable: {exc}"]
    except Exception as exc:
        return [f"Playwright validation failed: {exc}"]

    errors = []
    if slide_count != expected_slide_count:
        errors.append(f"Expected {expected_slide_count} slides in browser, found {slide_count}.")
    if visible_count != 1:
        errors.append(f"Expected one visible slide, found {visible_count}.")
    if not stage_box or stage_box["width"] <= 0 or stage_box["height"] <= 0:
        errors.append("Deck stage did not render with positive dimensions.")
    if overflowing:
        errors.append(
            "Slide content overflows the fixed 1920x1080 stage on slides: "
            + ", ".join(str(index) for index in overflowing)
        )
    for math_error in math_errors:
        errors.append(f"MathJax error on slide {math_error['slide']}: {math_error['message']}")
    return errors


_MATHJAX_ERROR_PROBE_JS = """
() => {
    const seen = [];
    document.querySelectorAll('mjx-merror, [data-mjx-error]').forEach((node) => {
        const slide = node.closest('.slide');
        seen.push({
            slide: slide ? Number(slide.dataset.slideIndex ?? -1) : -1,
            message: node.getAttribute('data-mjx-error') || node.textContent.trim(),
        });
    });
    return seen;
}
"""


_OVERFLOW_PROBE_JS = """
() => {
    if (window.__fitAllSlides) window.__fitAllSlides();
    const overflowing = [];
    document.querySelectorAll('.slide').forEach((slide, index) => {
        const regions = [
            slide.querySelector('.slide-body'),
            slide.querySelector('.slide-content'),
            slide,
        ].filter(Boolean);
        const spills = regions.some(
            (region) =>
                region.scrollHeight - region.clientHeight > 2 ||
                region.scrollWidth - region.clientWidth > 2
        );
        if (spills) overflowing.push(index + 1);
    });
    return overflowing;
}
"""
