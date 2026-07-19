from __future__ import annotations

import re
import textwrap
from pathlib import Path

from pylatexenc.latex2text import LatexNodes2Text

from .models import BeamerDeck, BeamerSlide, ContentElement, ListItem


FRAME_RE = re.compile(r"\\begin\{frame\}|\\frame(?![A-Za-z@])")
ENV_RE = re.compile(r"\\begin\{([A-Za-z*]+)\}")
ITEM_TOKEN_RE = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}|\\item(?:\[[^\]]*\])?")
# Wrapper environments with no content semantics of their own: parse straight through them.
TRANSPARENT_ENVS = {
    "center",
    "centering",
    "columns",
    "column",
    "minipage",
    "adjustbox",
    "small",
    "footnotesize",
    "scriptsize",
    "normalsize",
    "large",
    "Large",
}
MATH_ENVS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "alignat",
    "alignat*",
    "gather",
    "gather*",
    "eqnarray",
    "eqnarray*",
    "multline",
    "multline*",
}
# Environments whose \begin takes mandatory {...} arguments that are not content.
ENV_REQUIRED_ARG_COUNTS = {
    "minipage": 1,
    "column": 1,
    "adjustbox": 1,
    "alignat": 1,
    "alignat*": 1,
    "tabular": 1,
}
RESIZEBOX_RE = re.compile(r"\\resizebox\*?\s*(?=\{)")
MATH_SPAN_RE = re.compile(
    r"\\\[(?P<display>.+?)\\\]"
    r"|\\\((?P<inline>.+?)\\\)"
    r"|(?<!\\)\$\$(?P<dollars2>[^$]+?)\$\$"
    r"|(?<!\\)\$(?P<dollars>[^$]+?)(?<!\\)\$",
    re.DOTALL,
)
_MATH_TOKEN = "MATHSPAN{index}ENDSPAN"
_MATH_TOKEN_RE = re.compile(r"MATHSPAN(\d+)ENDSPAN")


def parse_beamer(path: Path | str) -> BeamerDeck:
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    metadata = _parse_metadata(source)
    document = _document_body(source)
    slides: list[BeamerSlide] = []
    unsupported: list[str] = []

    pos = 0
    while True:
        match = FRAME_RE.search(document, pos)
        if not match:
            break
        if match.group(0).startswith(r"\begin"):
            slide, pos = _parse_frame_environment(document, match.start(), len(slides) + 1)
        else:
            slide, pos = _parse_frame_command(document, match.start(), len(slides) + 1)
        slides.append(slide)
        unsupported.extend(_find_unsupported(slide.elements))

    title = _clean_text(metadata.get("title", "")) or _infer_title_from_slides(slides) or source_path.stem
    return BeamerDeck(
        source_path=source_path,
        title=title,
        slides=slides,
        metadata=metadata,
        unsupported_environments=sorted(set(unsupported)),
    )


def apply_prompt_title(deck: BeamerDeck, prompt: str) -> BeamerDeck:
    if deck.metadata.get("title"):
        return deck
    inferred = _infer_title_from_slides(deck.slides)
    if inferred:
        deck.title = inferred
        return deck
    compact_prompt = " ".join(prompt.strip().split())
    if compact_prompt and len(compact_prompt) <= 90:
        deck.title = compact_prompt
    return deck


def summarize_deck(deck: BeamerDeck, max_slides: int = 12) -> str:
    lines = [f"Deck title: {deck.title}", f"Slide count: {deck.slide_count}"]
    for slide in deck.slides[:max_slides]:
        label = slide.title or ("Title page" if slide.is_titlepage else "Untitled")
        lines.append(f"{slide.index}. {label} ({_element_summary(slide.elements)})")
    if deck.slide_count > max_slides:
        lines.append(f"... {deck.slide_count - max_slides} more slides")
    return "\n".join(lines)


def _parse_metadata(source: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key in ("title", "subtitle", "author", "institute", "date"):
        match = re.search(rf"\\{key}(?:\[[^\]]*\])?\s*\{{", source)
        if not match:
            continue
        group = _parse_group(source, match.end() - 1, "{", "}")
        if group:
            metadata[key] = _clean_text(group[0])
    return metadata


def _document_body(source: str) -> str:
    begin = source.find(r"\begin{document}")
    end = source.rfind(r"\end{document}")
    if begin == -1:
        return source
    begin += len(r"\begin{document}")
    if end == -1 or end <= begin:
        return source[begin:]
    return source[begin:end]


def _parse_frame_environment(source: str, start: int, index: int) -> tuple[BeamerSlide, int]:
    command_end = start + len(r"\begin{frame}")
    cursor = _skip_ws(source, command_end)
    while cursor < len(source) and source[cursor] == "[":
        group = _parse_group(source, cursor, "[", "]")
        if not group:
            break
        cursor = _skip_ws(source, group[1])

    frame_title_argument = None
    if cursor < len(source) and source[cursor] == "{":
        group = _parse_group(source, cursor, "{", "}")
        if group:
            frame_title_argument = _clean_text(group[0])
            cursor = _skip_ws(source, group[1])

    end_start = source.find(r"\end{frame}", cursor)
    if end_start == -1:
        end_start = len(source)
        end_cursor = len(source)
    else:
        end_cursor = end_start + len(r"\end{frame}")

    body = source[cursor:end_start]
    explicit_title, body_without_title = _extract_frame_title(body)
    title = explicit_title or frame_title_argument or ""
    is_titlepage = r"\titlepage" in body_without_title
    elements = [] if is_titlepage else _parse_elements(body_without_title)
    slide = BeamerSlide(
        index=index,
        title=title,
        elements=elements,
        raw_tex=source[start:end_cursor],
        is_titlepage=is_titlepage,
        frame_title_argument=frame_title_argument,
    )
    return slide, end_cursor


def _parse_frame_command(source: str, start: int, index: int) -> tuple[BeamerSlide, int]:
    cursor = _skip_ws(source, start + len(r"\frame"))
    while cursor < len(source) and source[cursor] == "[":
        group = _parse_group(source, cursor, "[", "]")
        if not group:
            break
        cursor = _skip_ws(source, group[1])
    group = _parse_group(source, cursor, "{", "}")
    if not group:
        body = ""
        end_cursor = cursor
    else:
        body, end_cursor = group
    explicit_title, body_without_title = _extract_frame_title(body)
    is_titlepage = r"\titlepage" in body_without_title
    slide = BeamerSlide(
        index=index,
        title=explicit_title,
        elements=[] if is_titlepage else _parse_elements(body_without_title),
        raw_tex=source[start:end_cursor],
        is_titlepage=is_titlepage,
    )
    return slide, end_cursor


def _extract_frame_title(body: str) -> tuple[str, str]:
    match = re.search(r"\\frametitle\s*\{", body)
    if not match:
        return "", body
    group = _parse_group(body, match.end() - 1, "{", "}")
    if not group:
        return "", body
    title, end = group
    return _clean_text(title), body[: match.start()] + body[end:]


def _parse_elements(source: str) -> list[ContentElement]:
    source = _strip_comments(source)
    source = _strip_resizebox(source)
    elements: list[ContentElement] = []
    pos = 0
    while pos < len(source):
        match = ENV_RE.search(source, pos)
        if not match:
            _append_text_element(elements, source[pos:])
            break

        _append_text_element(elements, source[pos : match.start()])
        env = match.group(1)
        cursor = match.end()
        option_text = None
        if cursor < len(source) and source[cursor] == "[":
            option = _parse_group(source, cursor, "[", "]")
            if option:
                option_text, cursor = option

        block_title = None
        if env == "block":
            cursor = _skip_ws(source, cursor)
            if cursor < len(source) and source[cursor] == "{":
                group = _parse_group(source, cursor, "{", "}")
                if group:
                    block_title, cursor = _clean_text(group[0]), group[1]

        for _ in range(ENV_REQUIRED_ARG_COUNTS.get(env, 0)):
            cursor = _skip_ws(source, cursor)
            group = _parse_group(source, cursor, "{", "}")
            if not group:
                break
            cursor = group[1]

        end_range = _find_matching_environment(source, env, cursor)
        if not end_range:
            _append_text_element(elements, source[match.start() :])
            break
        inner = source[cursor : end_range[0]]
        pos = end_range[1]

        if env == "block":
            elements.append(
                ContentElement(kind="block", title=block_title, children=_parse_elements(inner), raw=inner)
            )
        elif env in {"itemize", "enumerate"}:
            elements.append(
                ContentElement(
                    kind="list",
                    ordered=env == "enumerate",
                    items=_parse_list_items(inner),
                    raw=inner,
                )
            )
        elif env in MATH_ENVS:
            elements.append(
                ContentElement(kind="equation", text=_strip_math_labels(inner).strip(), raw=inner, env=env)
            )
        elif env in {"table", "tabular"}:
            elements.append(ContentElement(kind="table", rows=_parse_table_rows(inner), raw=inner, env=env))
        elif env == "lstlisting":
            elements.append(
                ContentElement(
                    kind="code",
                    text=textwrap.dedent(inner).strip("\n"),
                    raw=inner,
                    language=_language_from_option(option_text),
                )
            )
        elif env == "verbatim":
            elements.append(
                ContentElement(kind="code", text=textwrap.dedent(inner).strip("\n"), raw=inner, language=None)
            )
        elif env in TRANSPARENT_ENVS:
            elements.extend(_parse_elements(inner))
        elif env not in {"tikzpicture", "axis"} and r"\begin{tabular}" in inner:
            # Safety net: never let a real table reach the raw-LaTeX fallback.
            elements.extend(_parse_elements(inner))
        else:
            elements.append(ContentElement(kind="raw", title=env, raw=inner.strip()))
    return [element for element in elements if _element_has_content(element)]


def _parse_list_items(source: str) -> list[ListItem]:
    spans: list[tuple[int, int]] = []
    depth = 0
    for token in ITEM_TOKEN_RE.finditer(source):
        if token.group(0).startswith(r"\begin"):
            depth += 1
        elif token.group(0).startswith(r"\end"):
            depth = max(0, depth - 1)
        elif depth == 0:
            spans.append((token.start(), token.end()))
    items: list[ListItem] = []
    for i, (_, start) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(source)
        segment = source[start:end]
        nested = ENV_RE.search(segment)
        if nested:
            text_part = segment[: nested.start()]
            child_part = segment[nested.start() :]
            children = _parse_elements(child_part)
        else:
            text_part = segment
            children = []
        text = _clean_text(text_part)
        if text or children:
            items.append(ListItem(text=text, children=children))
    return items


def _parse_table_rows(source: str) -> list[list[str]]:
    tabular = re.search(r"\\begin\{tabular\}(?:\{[^}]*\})?", source)
    if tabular:
        end = source.find(r"\end{tabular}", tabular.end())
        if end != -1:
            source = source[tabular.end() : end]
    source = re.sub(r"\\(hline|toprule|midrule|bottomrule)\b", "", source)
    source = re.sub(r"\\cline\s*\{[^}]*\}", "", source)
    # Flatten \multicolumn{n}{fmt}{body} to its body; the braces around the
    # body are removed later by _clean_text.
    source = re.sub(r"\\multicolumn\s*\{[^}]*\}\s*\{[^}]*\}", "", source)
    rows: list[list[str]] = []
    for raw_row in re.split(r"\\\\", source):
        # Keep empty cells so columns stay aligned; drop rows that are entirely empty.
        cells = [_clean_text(cell) for cell in re.split(r"(?<!\\)&", raw_row)]
        if any(cells):
            rows.append(cells)
    return rows


def _append_text_element(elements: list[ContentElement], source: str) -> None:
    text = _clean_text(source)
    if text:
        elements.append(ContentElement(kind="text", text=text, raw=source))


def _element_has_content(element: ContentElement) -> bool:
    return bool(element.text or element.items or element.rows or element.raw or element.children)


def _find_matching_environment(source: str, env: str, start: int) -> tuple[int, int] | None:
    pattern = re.compile(rf"\\(begin|end)\{{{re.escape(env)}\}}")
    depth = 1
    for match in pattern.finditer(source, start):
        if match.group(1) == "begin":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return match.start(), match.end()
    return None


def _parse_group(source: str, start: int, opener: str, closer: str) -> tuple[str, int] | None:
    if start >= len(source) or source[start] != opener:
        return None
    depth = 1
    cursor = start + 1
    while cursor < len(source):
        char = source[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return source[start + 1 : cursor], cursor + 1
        cursor += 1
    return None


def _skip_ws(source: str, cursor: int) -> int:
    while cursor < len(source) and source[cursor].isspace():
        cursor += 1
    return cursor


def _strip_resizebox(source: str) -> str:
    """Rewrite \\resizebox{w}{h}{content} to just content (nested braces safe)."""
    while True:
        match = RESIZEBOX_RE.search(source)
        if not match:
            return source
        cursor = match.end()
        groups: list[str] = []
        for _ in range(3):
            cursor = _skip_ws(source, cursor)
            group = _parse_group(source, cursor, "{", "}")
            if not group:
                break
            groups.append(group[0])
            cursor = group[1]
        if len(groups) != 3:
            # Malformed command: drop the token itself so the loop terminates.
            source = source[: match.start()] + source[match.end() :]
            continue
        source = source[: match.start()] + groups[2] + source[cursor:]


def _strip_math_labels(source: str) -> str:
    return re.sub(r"\\label\s*\{[^}]*\}", "", source)


# Environments MathJax rejects inside \[...\] display math, mapped to their
# inner-safe equivalents (empty string = drop the wrapper tokens entirely).
_DISPLAY_SAFE_ENV_MAP = {
    "align": "aligned",
    "align*": "aligned",
    "alignat": "alignedat",
    "alignat*": "alignedat",
    "flalign": "aligned",
    "flalign*": "aligned",
    "eqnarray": "aligned",
    "eqnarray*": "aligned",
    "gather": "gathered",
    "gather*": "gathered",
    "multline": "gathered",
    "multline*": "gathered",
    "equation": "",
    "equation*": "",
}
_ENV_TOKEN_RE = re.compile(r"\\(begin|end)\{([A-Za-z*]+)\}")


def normalize_display_math(body: str) -> str:
    """Rewrite environments nested in display math to forms MathJax accepts inside \\[...\\]."""

    def swap(match: re.Match[str]) -> str:
        replacement = _DISPLAY_SAFE_ENV_MAP.get(match.group(2))
        if replacement is None:
            return match.group(0)
        if not replacement:
            return ""
        return f"\\{match.group(1)}{{{replacement}}}"

    return _ENV_TOKEN_RE.sub(swap, body)


def _strip_comments(source: str) -> str:
    lines = []
    for line in source.splitlines():
        lines.append(re.sub(r"(?<!\\)%.*$", "", line))
    return "\n".join(lines)


def _clean_text(source: str) -> str:
    if not source:
        return ""
    source = _strip_comments(source)
    source, math_spans = _protect_math(source)
    source = re.sub(r"\\setcounter\{[^}]+\}\{[^}]+\}", "", source)
    source = source.replace("~", " ")
    source = re.sub(r"\\separator\b", " ", source)
    try:
        text = LatexNodes2Text().latex_to_text(source)
    except Exception:
        text = source
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _restore_math(text, math_spans)
    return text.strip()


def _protect_math(source: str) -> tuple[str, list[str]]:
    """Replace math spans with plain-text tokens that survive latex-to-text conversion.

    Spans are normalized to MathJax delimiters: \\( \\) for inline, \\[ \\] for display.
    """
    spans: list[str] = []

    def stash(match: re.Match[str]) -> str:
        display = match.group("display") or match.group("dollars2")
        inline = match.group("inline") or match.group("dollars")
        if display is not None:
            spans.append(f"\\[{normalize_display_math(display.strip())}\\]")
        else:
            spans.append(f"\\({inline.strip()}\\)")
        return _MATH_TOKEN.format(index=len(spans) - 1)

    return MATH_SPAN_RE.sub(stash, source), spans


def _restore_math(text: str, spans: list[str]) -> str:
    if not spans:
        return text

    def unstash(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return spans[index] if index < len(spans) else match.group(0)

    return _MATH_TOKEN_RE.sub(unstash, text)


def _language_from_option(option_text: str | None) -> str | None:
    if not option_text:
        return None
    match = re.search(r"language\s*=\s*([A-Za-z0-9_+-]+)", option_text)
    return match.group(1) if match else None


def _find_unsupported(elements: list[ContentElement]) -> list[str]:
    unsupported: list[str] = []
    for element in elements:
        if element.kind == "raw" and element.title:
            unsupported.append(element.title)
        unsupported.extend(_find_unsupported(element.children))
        for item in element.items:
            unsupported.extend(_find_unsupported(item.children))
    return unsupported


def _infer_title_from_slides(slides: list[BeamerSlide]) -> str:
    for slide in slides:
        if slide.is_titlepage:
            continue
        title = slide.title.strip()
        if not title:
            continue
        title = re.sub(r"^Introduction to\s+", "", title, flags=re.IGNORECASE)
        title = re.split(r"\s+-\s+", title)[0].strip()
        return title
    return ""


def _element_summary(elements: list[ContentElement]) -> str:
    if not elements:
        return "no parsed content"
    counts: dict[str, int] = {}
    for element in elements:
        counts[element.kind] = counts.get(element.kind, 0) + 1
    return ", ".join(f"{kind}:{count}" for kind, count in sorted(counts.items()))
