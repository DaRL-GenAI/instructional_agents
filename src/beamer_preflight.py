"""Deterministic repairs for common, safely recoverable Beamer source defects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_LIST_ENVIRONMENTS = {"itemize", "enumerate"}
_PROTECTED_ENVIRONMENTS = {"lstlisting", "verbatim", "Verbatim", "minted"}
_ENV_TOKEN = re.compile(
    r"\\(?P<action>begin|end)\{"
    r"(?P<environment>itemize|enumerate|lstlisting|verbatim|Verbatim|minted)"
    r"\}(?P<option>[ \t]*\[[^\]\r\n]*\])?"
)
_PROTECTED_ENV_TOKEN = re.compile(
    r"\\(?P<action>begin|end)\{"
    r"(?P<environment>lstlisting|verbatim|Verbatim|minted)"
    r"\}"
)
_LINE_ENV_TOKEN = re.compile(
    r"\\(?P<action>begin|end)\{"
    r"(?P<environment>itemize|enumerate|lstlisting|verbatim|Verbatim|minted)"
    r"\}(?P<option>[ \t]*\[[^\]\r\n]*\])?"
)
_LINE_ITEM = re.compile(r"\\item(?:\s|\[|$)")

# Color-bearing commands whose mandatory argument is a color *name* unless an
# optional [model] argument turns it into a raw spec such as [HTML]{FF0000}.
_COLOR_ARG_COMMAND = re.compile(
    r"\\(?:textcolor|pagecolor|colorbox|rowcolor|cellcolor|columncolor|"
    r"arrayrulecolor|color(?![A-Za-z]))\s*"
    r"(?P<model>\[[^\]]*\])?\s*\{(?P<expr>[^{}]*)\}"
)
_FCOLORBOX = re.compile(
    r"\\fcolorbox\s*(?P<m1>\[[^\]]*\])?\s*\{(?P<c1>[^{}]*)\}"
    r"\s*(?P<m2>\[[^\]]*\])?\s*\{(?P<c2>[^{}]*)\}"
)
_COLORLET = re.compile(
    r"\\colorlet\s*\{(?P<name>[^{}]*)\}\s*(?:\[[^\]]*\])?\s*\{(?P<expr>[^{}]*)\}"
)
_COLOR_DEFINITION = re.compile(
    r"\\(?:definecolor|providecolor)\*?\s*(?:\[[^\]]*\])?\s*\{(?P<name>[^{}]*)\}"
)
_SETBEAMERCOLOR = re.compile(
    r"\\setbeamercolor\*?\s*\{[^{}]*\}\s*\{(?P<body>[^{}]*)\}"
)
_BEAMER_COLOR_KEY = re.compile(r"\b(?:fg|bg)\s*=\s*(?P<expr>[^,]+)")
_TIKZ_COLOR_KEY = re.compile(
    r"(?<![A-Za-z])(?:left color|right color|inner color|outer color|"
    r"fill|draw|text|color)\s*=\s*"
    r"(?P<expr>[A-Za-z][A-Za-z0-9]*(?:![^\s,\]{}]+)?)"
)
_COLOR_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*")
_BEGIN_DOCUMENT = re.compile(r"\\begin\{document\}")

# Names xcolor always defines, regardless of package options.
_XCOLOR_BASE_NAMES = frozenset(
    {
        "black", "blue", "brown", "cyan", "darkgray", "gray", "green",
        "lightgray", "lime", "magenta", "olive", "orange", "pink", "purple",
        "red", "teal", "violet", "white", "yellow",
    }
)

# Values that look like color names in option lists but must never be defined.
_SKIP_NAMES = frozenset({"none", "transparent"})

# LLM-invented names observed in (or likely from) the course style vocabulary
# ("electric cobalt blue", "neon yellow", "hot pink", ...), mapped to hexes
# that match the intent of the bold-template-pack palettes.
_CURATED_COLOR_HEX = {
    "electricblue": "0047AB",
    "electriccobalt": "0047AB",
    "cobaltblue": "0047AB",
    "cobalt": "0047AB",
    "electricpurple": "7B2FF7",
    "electricyellow": "E8F000",
    "neonyellow": "E8F000",
    "acidyellow": "D7F000",
    "neongreen": "39FF14",
    "neonpink": "FF2EC4",
    "neoncyan": "00F0FF",
    "neonblue": "1F51FF",
    "hotred": "E63946",
    "deepforestgreen": "1B4332",
    "offwhite": "FAF7F2",
    "cream": "FFF8E7",
    "paper": "FAF7F2",
    "charcoal": "36454F",
    "ink": "1A1A1A",
    "midnight": "191970",
}

# Lowercase svgnames/dvipsnames-style lookup so common names resolve to their
# conventional hex without loading any xcolor name table in the preamble.
_NAMED_COLOR_HEX = {
    "black": "000000", "blue": "0000FF", "brown": "A52A2A", "cyan": "00FFFF",
    "darkgray": "A9A9A9", "gray": "808080", "green": "008000",
    "lightgray": "D3D3D3", "lime": "00FF00", "magenta": "FF00FF",
    "olive": "808000", "orange": "FFA500", "pink": "FFC0CB",
    "purple": "800080", "red": "FF0000", "teal": "008080",
    "violet": "EE82EE", "white": "FFFFFF", "yellow": "FFFF00",
    "aliceblue": "F0F8FF", "antiquewhite": "FAEBD7", "apricot": "FBB982",
    "aqua": "00FFFF", "aquamarine": "7FFFD4", "azure": "F0FFFF",
    "beige": "F5F5DC", "bisque": "FFE4C4", "bittersweet": "C04F17",
    "blanchedalmond": "FFEBCD", "bluegreen": "00B3B8", "blueviolet": "8A2BE2",
    "brickred": "B6321C", "burlywood": "DEB887", "burntorange": "F7921D",
    "cadetblue": "5F9EA0", "carnationpink": "F282B4", "cerulean": "00A2E3",
    "chartreuse": "7FFF00", "chocolate": "D2691E", "coral": "FF7F50",
    "cornflowerblue": "6495ED", "cornsilk": "FFF8DC", "crimson": "DC143C",
    "dandelion": "FDBC42", "darkblue": "00008B", "darkcyan": "008B8B",
    "darkgoldenrod": "B8860B", "darkgreen": "006400", "darkkhaki": "BDB76B",
    "darkmagenta": "8B008B", "darkolivegreen": "556B2F", "darkorange": "FF8C00",
    "darkorchid": "9932CC", "darkred": "8B0000", "darksalmon": "E9967A",
    "darkseagreen": "8FBC8F", "darkslateblue": "483D8B",
    "darkslategray": "2F4F4F", "darkslategrey": "2F4F4F",
    "darkturquoise": "00CED1", "darkviolet": "9400D3", "deeppink": "FF1493",
    "deepskyblue": "00BFFF", "dimgray": "696969", "dimgrey": "696969",
    "dodgerblue": "1E90FF", "emerald": "00A99D", "firebrick": "B22222",
    "floralwhite": "FFFAF0", "forestgreen": "228B22", "fuchsia": "FF00FF",
    "gainsboro": "DCDCDC", "ghostwhite": "F8F8FF", "gold": "FFD700",
    "goldenrod": "DAA520", "greenyellow": "ADFF2F", "honeydew": "F0FFF0",
    "hotpink": "FF69B4", "indianred": "CD5C5C", "indigo": "4B0082",
    "ivory": "FFFFF0", "junglegreen": "00A99A", "khaki": "F0E68C",
    "lavender": "E6E6FA", "lavenderblush": "FFF0F5", "lawngreen": "7CFC00",
    "lemonchiffon": "FFFACD", "lightblue": "ADD8E6", "lightcoral": "F08080",
    "lightcyan": "E0FFFF", "lightgoldenrodyellow": "FAFAD2",
    "lightgreen": "90EE90", "lightgrey": "D3D3D3", "lightpink": "FFB6C1",
    "lightsalmon": "FFA07A", "lightseagreen": "20B2AA",
    "lightskyblue": "87CEFA", "lightslategray": "778899",
    "lightslategrey": "778899", "lightsteelblue": "B0C4DE",
    "lightyellow": "FFFFE0", "limegreen": "32CD32", "linen": "FAF0E6",
    "mahogany": "A9341F", "maroon": "800000", "mediumaquamarine": "66CDAA",
    "mediumblue": "0000CD", "mediumorchid": "BA55D3",
    "mediumpurple": "9370DB", "mediumseagreen": "3CB371",
    "mediumslateblue": "7B68EE", "mediumspringgreen": "00FA9A",
    "mediumturquoise": "48D1CC", "mediumvioletred": "C71585",
    "melon": "F89E7B", "midnightblue": "191970", "mintcream": "F5FFFA",
    "mistyrose": "FFE4E1", "moccasin": "FFE4B5", "mulberry": "A93C93",
    "navajowhite": "FFDEAD", "navy": "000080", "navyblue": "006EB8",
    "oldlace": "FDF5E6", "olivedrab": "6B8E23", "olivegreen": "3C8031",
    "orangered": "FF4500", "orchid": "DA70D6", "palegoldenrod": "EEE8AA",
    "palegreen": "98FB98", "paleturquoise": "AFEEEE",
    "palevioletred": "DB7093", "papayawhip": "FFEFD5", "peach": "F7965A",
    "peachpuff": "FFDAB9", "periwinkle": "7977B8", "peru": "CD853F",
    "pinegreen": "008B72", "plum": "DDA0DD", "powderblue": "B0E0E6",
    "processblue": "00B0F0", "rawsienna": "974006", "redorange": "F26035",
    "redviolet": "A1246B", "rhodamine": "EF559F", "rosybrown": "BC8F8F",
    "royalblue": "4169E1", "royalpurple": "613F99", "rubinered": "ED017D",
    "saddlebrown": "8B4513", "salmon": "FA8072", "sandybrown": "F4A460",
    "seagreen": "2E8B57", "seashell": "FFF5EE", "sepia": "671800",
    "sienna": "A0522D", "silver": "C0C0C0", "skyblue": "87CEEB",
    "slateblue": "6A5ACD", "slategray": "708090", "slategrey": "708090",
    "snow": "FFFAFA", "springgreen": "00FF7F", "steelblue": "4682B4",
    "tan": "D2B48C", "tealblue": "00AEB3", "thistle": "D8BFD8",
    "tomato": "FF6347", "turquoise": "40E0D0", "violetred": "EF58A0",
    "wheat": "F5DEB3", "whitesmoke": "F5F5F5", "wildstrawberry": "EE2967",
    "yellowgreen": "9ACD32", "yelloworange": "FAA21A",
}

_MODIFIER_PREFIXES = (
    "electric", "neon", "hot", "deep", "acid", "vivid", "bold", "bright",
    "dark", "light", "soft", "pale", "muted", "warm", "cool", "rich",
    "dusty", "medium",
)

_HUE_FALLBACK_HEX = {
    "blue": "0047AB", "cobalt": "0047AB", "navy": "001F5B", "red": "D62828",
    "green": "1B7A3D", "forest": "1B4332", "teal": "0F766E",
    "purple": "6D28D9", "violet": "7C3AED", "pink": "E0218A",
    "rose": "E0218A", "orange": "F77F00", "yellow": "EAB308",
    "gold": "D4A017", "cyan": "0891B2", "magenta": "C026D3",
    "brown": "7B4B2A", "gray": "6B7280", "grey": "6B7280",
    "black": "000000", "white": "FFFFFF", "cream": "FFF8E7",
    "charcoal": "36454F", "ink": "1A1A1A",
}

_NEUTRAL_FALLBACK_HEX = "4A5568"


@dataclass(frozen=True)
class BeamerPreflightResult:
    source: str
    removed_list_wrapper_pairs: int
    original_max_list_depth: int
    normalized_max_list_depth: int
    injected_color_definitions: tuple[str, ...] = ()
    inserted_list_closures: int = 0

    @property
    def changed(self) -> bool:
        return (
            self.removed_list_wrapper_pairs > 0
            or bool(self.injected_color_definitions)
            or self.inserted_list_closures > 0
        )


@dataclass(frozen=True)
class _ListToken:
    start: int
    end: int
    action: str
    environment: str


def normalize_beamer_source(
    source: str,
    *,
    max_list_depth: int = 3,
) -> BeamerPreflightResult:
    """Repair safely recoverable defects in assembled Beamer source.

    Three deterministic passes run in order:

    1. Close an indented child list when an outdented sibling ``\\item`` shows
       that the generated source omitted the closing environment. A repair is
       accepted only when it makes the complete list structure balanced.
    2. Flatten list wrappers beyond Beamer's supported nesting depth. The
       nested ``\\item`` content is retained at the deepest supported level.
       Other malformed list structures are left unchanged so preflight never
       makes an invalid environment sequence harder to diagnose.
    3. Inject ``\\providecolor`` definitions before ``\\begin{document}`` for
       every referenced-but-undefined color name, so LLM-coined names such as
       ``electricblue`` can never abort pdflatex with "Undefined color".
       ``\\providecolor`` is a no-op for already-defined names, which makes
       over-injection harmless and the pass idempotent.

    Tokens inside verbatim-style environments and LaTeX comments are ignored
    by all passes.
    """
    if max_list_depth < 1:
        raise ValueError("max_list_depth must be at least 1")

    structurally_repaired, inserted_closures = (
        _repair_unclosed_lists_before_items(source)
    )
    normalized, removed_pairs, original_depth, normalized_depth = (
        _normalize_lists(structurally_repaired, max_list_depth)
    )
    repaired, injected = _ensure_color_definitions(normalized)

    return BeamerPreflightResult(
        source=repaired,
        removed_list_wrapper_pairs=removed_pairs,
        original_max_list_depth=original_depth,
        normalized_max_list_depth=normalized_depth,
        injected_color_definitions=injected,
        inserted_list_closures=inserted_closures,
    )


def normalize_beamer_file(
    path: Path | str,
    *,
    max_list_depth: int = 3,
) -> BeamerPreflightResult:
    source_path = Path(path)
    result = normalize_beamer_source(
        source_path.read_text(encoding="utf-8"),
        max_list_depth=max_list_depth,
    )
    if result.changed:
        temporary = source_path.with_suffix(source_path.suffix + ".preflight.tmp")
        temporary.write_text(result.source, encoding="utf-8")
        temporary.replace(source_path)
    return result


def _normalize_lists(
    source: str,
    max_list_depth: int,
) -> tuple[str, int, int, int]:
    tokens = _list_tokens_outside_protected_regions(source)
    stack: list[str] = []
    original_max_depth = 0
    for token in tokens:
        if token.action == "begin":
            stack.append(token.environment)
            original_max_depth = max(original_max_depth, len(stack))
        elif not stack or stack.pop() != token.environment:
            return source, 0, original_max_depth, original_max_depth
    if stack:
        return source, 0, original_max_depth, original_max_depth

    output: list[str] = []
    cursor = 0
    retained_depth = 0
    decisions: list[bool] = []
    removed_pairs = 0
    normalized_max_depth = 0
    for token in tokens:
        output.append(source[cursor:token.start])
        if token.action == "begin":
            retain = retained_depth < max_list_depth
            decisions.append(retain)
            if retain:
                output.append(source[token.start:token.end])
                retained_depth += 1
                normalized_max_depth = max(normalized_max_depth, retained_depth)
            else:
                removed_pairs += 1
        else:
            retain = decisions.pop()
            if retain:
                output.append(source[token.start:token.end])
                retained_depth -= 1
        cursor = token.end
    output.append(source[cursor:])

    return "".join(output), removed_pairs, original_max_depth, normalized_max_depth


def _repair_unclosed_lists_before_items(source: str) -> tuple[str, int]:
    """Close indented child lists before an outdented sibling ``\\item``.

    Generated LaTeX sometimes starts a nested ``itemize`` for one top-level
    item and omits its closing tag before the next sibling item. Indentation
    identifies the intended parent without guessing when formatting is flat.
    The candidate rewrite is accepted only when every list environment is
    balanced afterward.
    """
    output: list[str] = []
    stack: list[tuple[str, int, str]] = []
    protected_stack: list[str] = []
    inserted = 0

    for line in source.splitlines(keepends=True):
        stripped = line.lstrip(" \t")
        indentation = line[: len(line) - len(stripped)]
        indent_width = len(indentation.expandtabs(4))
        token = _LINE_ENV_TOKEN.match(stripped)

        if protected_stack:
            if token:
                action = token.group("action")
                environment = token.group("environment")
                if action == "begin" and environment in _PROTECTED_ENVIRONMENTS:
                    protected_stack.append(environment)
                elif action == "end" and environment == protected_stack[-1]:
                    protected_stack.pop()
            output.append(line)
            continue

        if token and token.group("environment") in _PROTECTED_ENVIRONMENTS:
            if token.group("action") == "begin":
                protected_stack.append(token.group("environment"))
            output.append(line)
            continue

        if not stripped.startswith("%") and _LINE_ITEM.match(stripped) and stack:
            parent_index = next(
                (
                    index
                    for index in range(len(stack) - 1, -1, -1)
                    if stack[index][1] < indent_width
                ),
                None,
            )
            if parent_index is not None and parent_index < len(stack) - 1:
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                for environment, _width, begin_indent in reversed(
                    stack[parent_index + 1 :]
                ):
                    output.append(f"{begin_indent}\\end{{{environment}}}{newline}")
                    inserted += 1
                del stack[parent_index + 1 :]

        if token and not stripped.startswith("%"):
            action = token.group("action")
            environment = token.group("environment")
            if environment in _LIST_ENVIRONMENTS:
                if action == "begin":
                    stack.append((environment, indent_width, indentation))
                elif stack and stack[-1][0] == environment:
                    stack.pop()
        output.append(line)

    if inserted == 0:
        return source, 0
    candidate = "".join(output)
    if not _list_structure_is_balanced(candidate):
        return source, 0
    return candidate, inserted


def _list_structure_is_balanced(source: str) -> bool:
    stack: list[str] = []
    for token in _list_tokens_outside_protected_regions(source):
        if token.action == "begin":
            stack.append(token.environment)
        elif not stack or stack.pop() != token.environment:
            return False
    return not stack


def _ensure_color_definitions(source: str) -> tuple[str, tuple[str, ...]]:
    insertion_point = _document_begin_index(source)
    if insertion_point is None:
        return source, ()

    referenced = _referenced_color_names(source)
    defined = _defined_color_names(source)
    missing = sorted(name for name in referenced if name not in defined)
    if not missing:
        return source, ()

    lines = ["% [preflight] auto-defined colors for referenced-but-undefined names"]
    for name in missing:
        lines.append(
            f"\\providecolor{{{name}}}{{HTML}}{{{_hex_for_color_name(name)}}}"
        )
    block = "\n".join(lines) + "\n"
    if insertion_point > 0 and source[insertion_point - 1] != "\n":
        block = "\n" + block
    return source[:insertion_point] + block + source[insertion_point:], tuple(missing)


def _document_begin_index(source: str) -> int | None:
    for match in _BEGIN_DOCUMENT.finditer(source):
        if not _is_commented(source, match.start()):
            return match.start()
    return None


def _referenced_color_names(source: str) -> set[str]:
    spans = _protected_spans(source)

    def usable(position: int) -> bool:
        return not _is_commented(source, position) and not _in_spans(position, spans)

    names: set[str] = set()
    for match in _COLOR_ARG_COMMAND.finditer(source):
        if usable(match.start()) and not match.group("model"):
            names.update(_color_expression_names(match.group("expr")))
    for match in _FCOLORBOX.finditer(source):
        if not usable(match.start()):
            continue
        if not match.group("m1"):
            names.update(_color_expression_names(match.group("c1")))
            if not match.group("m2"):
                names.update(_color_expression_names(match.group("c2")))
    for match in _COLORLET.finditer(source):
        if usable(match.start()):
            names.update(_color_expression_names(match.group("expr")))
    for match in _SETBEAMERCOLOR.finditer(source):
        if not usable(match.start()):
            continue
        for key_match in _BEAMER_COLOR_KEY.finditer(match.group("body")):
            names.update(_color_expression_names(key_match.group("expr")))
    for match in _TIKZ_COLOR_KEY.finditer(source):
        if usable(match.start()):
            names.update(_color_expression_names(match.group("expr")))
    return names


def _defined_color_names(source: str) -> set[str]:
    defined = set(_XCOLOR_BASE_NAMES)
    for match in _COLOR_DEFINITION.finditer(source):
        if not _is_commented(source, match.start()):
            defined.add(match.group("name").strip())
    for match in _COLORLET.finditer(source):
        if not _is_commented(source, match.start()):
            defined.add(match.group("name").strip())
    return defined


def _color_expression_names(expression: str) -> set[str]:
    names: set[str] = set()
    for segment in expression.split("!"):
        token = segment.strip().lstrip("-").strip()
        if not _COLOR_NAME_TOKEN.fullmatch(token):
            continue
        if token.lower() in _SKIP_NAMES:
            continue
        names.add(token)
    return names


def _hex_for_color_name(name: str) -> str:
    for candidate in _candidate_keys(name):
        if candidate in _CURATED_COLOR_HEX:
            return _CURATED_COLOR_HEX[candidate]
        if candidate in _NAMED_COLOR_HEX:
            return _NAMED_COLOR_HEX[candidate]
    normalized = _normalize_color_key(name)
    best_hue = ""
    for hue in _HUE_FALLBACK_HEX:
        if hue in normalized and len(hue) > len(best_hue):
            best_hue = hue
    if best_hue:
        return _HUE_FALLBACK_HEX[best_hue]
    return _NEUTRAL_FALLBACK_HEX


def _candidate_keys(name: str) -> list[str]:
    current = _normalize_color_key(name)
    candidates: list[str] = []
    while current and current not in candidates:
        candidates.append(current)
        for prefix in _MODIFIER_PREFIXES:
            if current.startswith(prefix) and len(current) > len(prefix):
                current = current[len(prefix):]
                break
        else:
            break
    return candidates


def _normalize_color_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _protected_spans(source: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    for match in _PROTECTED_ENV_TOKEN.finditer(source):
        if _is_commented(source, match.start()):
            continue
        if match.group("action") == "begin":
            stack.append((match.group("environment"), match.start()))
        elif stack and stack[-1][0] == match.group("environment"):
            _, start = stack.pop()
            if not stack:
                spans.append((start, match.end()))
    if stack:
        spans.append((stack[0][1], len(source)))
    return spans


def _in_spans(position: int, spans: list[tuple[int, int]]) -> bool:
    return any(start <= position < end for start, end in spans)


def _list_tokens_outside_protected_regions(source: str) -> list[_ListToken]:
    tokens: list[_ListToken] = []
    protected_stack: list[str] = []
    for match in _ENV_TOKEN.finditer(source):
        if _is_commented(source, match.start()):
            continue
        action = match.group("action")
        environment = match.group("environment")
        if protected_stack:
            if action == "begin" and environment in _PROTECTED_ENVIRONMENTS:
                protected_stack.append(environment)
            elif action == "end" and environment == protected_stack[-1]:
                protected_stack.pop()
            continue
        if environment in _PROTECTED_ENVIRONMENTS:
            if action == "begin":
                protected_stack.append(environment)
            continue
        if environment in _LIST_ENVIRONMENTS:
            tokens.append(
                _ListToken(
                    start=match.start(),
                    end=match.end(),
                    action=action,
                    environment=environment,
                )
            )
    return tokens


def _is_commented(source: str, position: int) -> bool:
    line_start = source.rfind("\n", 0, position) + 1
    cursor = line_start
    while True:
        percent = source.find("%", cursor, position)
        if percent < 0:
            return False
        backslashes = 0
        index = percent - 1
        while index >= line_start and source[index] == "\\":
            backslashes += 1
            index -= 1
        if backslashes % 2 == 0:
            return True
        cursor = percent + 1
