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


@dataclass(frozen=True)
class BeamerPreflightResult:
    source: str
    removed_list_wrapper_pairs: int
    original_max_list_depth: int
    normalized_max_list_depth: int

    @property
    def changed(self) -> bool:
        return self.removed_list_wrapper_pairs > 0


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
    """Flatten list wrappers beyond Beamer's supported nesting depth.

    The nested ``\\item`` content is retained at the deepest supported level.
    Tokens inside verbatim-style environments and LaTeX comments are ignored.
    Malformed list structures are returned unchanged so preflight never makes
    an already-invalid environment sequence harder to diagnose.
    """
    if max_list_depth < 1:
        raise ValueError("max_list_depth must be at least 1")

    tokens = _list_tokens_outside_protected_regions(source)
    stack: list[str] = []
    original_max_depth = 0
    for token in tokens:
        if token.action == "begin":
            stack.append(token.environment)
            original_max_depth = max(original_max_depth, len(stack))
        elif not stack or stack.pop() != token.environment:
            return BeamerPreflightResult(
                source=source,
                removed_list_wrapper_pairs=0,
                original_max_list_depth=original_max_depth,
                normalized_max_list_depth=original_max_depth,
            )
    if stack:
        return BeamerPreflightResult(
            source=source,
            removed_list_wrapper_pairs=0,
            original_max_list_depth=original_max_depth,
            normalized_max_list_depth=original_max_depth,
        )

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

    return BeamerPreflightResult(
        source="".join(output),
        removed_list_wrapper_pairs=removed_pairs,
        original_max_list_depth=original_max_depth,
        normalized_max_list_depth=normalized_max_depth,
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
