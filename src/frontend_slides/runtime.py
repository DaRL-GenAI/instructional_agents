from __future__ import annotations

import shutil
from pathlib import Path

from .errors import FrontendSlidesError
from .models import CourseSlideStyle
from .style import FONT_FAMILIES


def runtime_asset_root() -> Path:
    return Path(__file__).resolve().parent / "runtime_assets"


def prepare_offline_runtime(
    chapter_dir: Path, style: CourseSlideStyle
) -> tuple[Path, str]:
    """Copy only the selected runtime assets and return their @font-face CSS."""
    source_root = runtime_asset_root()
    output_root = chapter_dir / "frontend-assets"
    if output_root.exists():
        shutil.rmtree(output_root)
    math_output = output_root / "mathjax"
    font_output = output_root / "fonts"
    license_output = output_root / "licenses"
    math_output.mkdir(parents=True, exist_ok=True)
    font_output.mkdir(parents=True, exist_ok=True)
    license_output.mkdir(parents=True, exist_ok=True)

    math_source = source_root / "mathjax" / "tex-svg.js"
    if not math_source.is_file():
        raise FrontendSlidesError(f"Offline MathJax runtime is missing: {math_source}")
    shutil.copy2(math_source, math_output / math_source.name)
    math_license = source_root / "licenses" / "MATHJAX-LICENSE.txt"
    if math_license.is_file():
        shutil.copy2(math_license, license_output / math_license.name)

    selected_fonts = {
        style.render_theme.display_font,
        style.render_theme.body_font,
        style.render_theme.mono_font,
    }
    css_blocks: list[str] = []
    for font_id in sorted(selected_fonts):
        try:
            family, stem = FONT_FAMILIES[font_id]
        except KeyError as exc:
            raise FrontendSlidesError(f"Unsupported packaged font: {font_id}") from exc
        for weight in (400, 700):
            filename = f"{stem}-{weight}.woff2"
            source = source_root / "fonts" / filename
            if not source.is_file():
                raise FrontendSlidesError(f"Packaged font file is missing: {source}")
            shutil.copy2(source, font_output / filename)
            css_blocks.append(
                "@font-face {"
                f"font-family:'{family}';"
                f"src:url('frontend-assets/fonts/{filename}') format('woff2');"
                f"font-style:normal;font-weight:{weight};font-display:swap;"
                "}"
            )

        license_key = {
            "archivo": "OFL-ARCHIVO.txt",
            "dm-sans": "OFL-DM-SANS.txt",
            "source-serif-4": "OFL-SOURCE-SERIF-4.txt",
            "space-grotesk": "OFL-SPACE-GROTESK.txt",
            "ibm-plex-mono": "OFL-IBM-PLEX-MONO.txt",
        }[font_id]
        license_source = source_root / "licenses" / license_key
        if license_source.is_file():
            shutil.copy2(license_source, license_output / license_source.name)

    return output_root, "<style>\n" + "\n".join(css_blocks) + "\n</style>"


def offline_runtime_complete(chapter_dir: Path, style: CourseSlideStyle) -> bool:
    """Return whether every runtime file referenced by this course style exists."""
    output_root = chapter_dir / "frontend-assets"
    required = [output_root / "mathjax" / "tex-svg.js"]
    selected_fonts = {
        style.render_theme.display_font,
        style.render_theme.body_font,
        style.render_theme.mono_font,
    }
    for font_id in selected_fonts:
        try:
            _, stem = FONT_FAMILIES[font_id]
        except KeyError:
            return False
        required.extend(
            output_root / "fonts" / f"{stem}-{weight}.woff2"
            for weight in (400, 700)
        )
    return all(path.is_file() and path.stat().st_size > 0 for path in required)
