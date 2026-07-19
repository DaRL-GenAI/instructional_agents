from __future__ import annotations

import math
import re

from .models import BeamerSlide, ContentElement, ListItem

# Rough characters per rendered line at body font size; weights approximate line counts.
_CHARS_PER_LINE = 90
_DISPLAY_MATH_RE = re.compile(
    r"\\\[.*?\\\]"
    r"|\\begin\{(?:equation|align|gather|multline)\*?\}.*?"
    r"\\end\{(?:equation|align|gather|multline)\*?\}"
    r"|\$\$.*?\$\$",
    re.DOTALL,
)


def element_weight(element: ContentElement) -> int:
    if element.kind == "list":
        return sum(item_weight(item) for item in element.items)
    if element.kind == "block":
        return 1 + sum(element_weight(child) for child in element.children)
    if element.kind == "table":
        return max(3, len(element.rows))
    if element.kind in {"generated_image", "user_image"}:
        return 4
    if element.kind == "code":
        # Code renders as a carbon-style image card (~480px, the default) or a
        # <pre>. Weight for the image case: splitting a touch too eagerly is
        # safe, letting a tall image overflow is not.
        if element.image_data_uri:
            return 6
        return max(3, min(element.text.count("\n") + 2, 6))
    if element.kind in {"equation", "raw"}:
        return 2
    return max(1, math.ceil(len(element.text) / _CHARS_PER_LINE)) + _display_math_count(
        element.text
    )


def item_weight(item: ListItem) -> int:
    lines = 1 + len(item.text) // _CHARS_PER_LINE
    return (
        lines
        + _display_math_count(item.text)
        + sum(element_weight(child) for child in item.children)
    )


def slide_weight(slide: BeamerSlide) -> int:
    return sum(element_weight(element) for element in slide.elements)


def _display_math_count(text: str) -> int:
    """Account for the vertical box MathJax adds for every display equation."""
    return len(_DISPLAY_MATH_RE.findall(text))
