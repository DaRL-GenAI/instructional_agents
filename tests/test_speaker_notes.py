from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.frontend_slides import load_assets
from src.frontend_slides import parse_beamer
from src.frontend_slides import FrontendSlidesError
from src.frontend_slides import StyleCandidate
from src.frontend_slides import (
    correlate_speaker_notes,
    notes_manifest,
    parse_speaker_notes,
    render_speaker_notes_markdown,
    upgrade_legacy_script,
)
from src.frontend_slides import render_deck_html


def _deck(tmp_path: Path):
    tex = tmp_path / "slides.tex"
    tex.write_text(
        r"""\documentclass{beamer}
\title{Safe <Course>}
\begin{document}
\begin{frame}\titlepage\end{frame}
\begin{frame}{First Concept}
The model is \(y'=y\).
\end{frame}
\begin{frame}{Equation}
\begin{equation}
y=e^x
\end{equation}
\end{frame}
\end{document}
""",
        encoding="utf-8",
    )
    return parse_beamer(tex)


def _canonical(deck) -> str:
    return render_speaker_notes_markdown(
        deck,
        [
            "Explain the first concept.",
            "Do not emit </script><script>alert('notes')</script> as markup.",
        ],
        document_title="Slides Script: Test",
    )


def test_canonical_notes_include_title_marker_and_validate(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    markdown = _canonical(deck)

    notes = correlate_speaker_notes(deck, markdown)

    assert [note.id for note in notes] == [
        "slide-001",
        "slide-002",
        "slide-003",
    ]
    assert notes[0].title == "Safe <Course>"
    assert "learning goals" in notes[0].text
    assert [entry["id"] for entry in notes_manifest(notes)] == [
        "slide-001",
        "slide-002",
        "slide-003",
    ]
    assert all(len(str(entry["note_sha256"])) == 64 for entry in notes_manifest(notes))


def test_canonical_notes_preserve_internal_horizontal_rules(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    note_with_rules = (
        "---\n\n"
        "Open with the comparison.\n\n"
        "---\n\n"
        "Then explain why the distinction matters."
    )
    markdown = render_speaker_notes_markdown(
        deck,
        [
            note_with_rules,
            "Explain the equation.",
        ],
    )

    notes = correlate_speaker_notes(deck, markdown)

    assert notes[1].text == note_with_rules
    assert notes[2].text == "Explain the equation."


@pytest.mark.parametrize(
    ("markdown_edit", "message"),
    [
        (lambda text: text.replace("slide-002", "slide-001"), "Duplicate"),
        (lambda text: text.replace("First Concept", "Different title"), "does not match"),
        (lambda text: text.replace("Explain the first concept.", ""), "empty"),
    ],
)
def test_correlation_rejects_ambiguous_or_empty_notes(
    tmp_path: Path,
    markdown_edit,
    message: str,
) -> None:
    deck = _deck(tmp_path)

    with pytest.raises(FrontendSlidesError, match=message):
        correlate_speaker_notes(deck, markdown_edit(_canonical(deck)))


def test_legacy_upgrade_requires_matching_titles(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    legacy = """# Slides Script

## Section 1: First Concept

Explain the first concept.

---

## Section 2: Equation

Explain the equation.
"""

    upgraded = upgrade_legacy_script(deck, legacy)
    assert len(parse_speaker_notes(upgraded)) == 3
    assert "<!-- speaker-note: slide-001 -->" in upgraded

    with pytest.raises(FrontendSlidesError, match="does not match"):
        upgrade_legacy_script(
            deck,
            legacy.replace("## Section 2: Equation", "## Section 2: Wrong"),
        )


def test_renderer_embeds_correlated_notes_and_unboxed_equations(tmp_path: Path) -> None:
    deck = _deck(tmp_path)
    notes = correlate_speaker_notes(deck, _canonical(deck))
    candidate = StyleCandidate(
        id="test",
        name="Test Style",
        source="generated",
    )

    rendered = render_deck_html(
        deck,
        candidate,
        load_assets(),
        speaker_notes=notes,
    )

    assert 'id="slide-001"' in rendered
    assert 'data-slide-id="slide-003"' in rendered
    assert 'id="presenterNotes"' in rendered
    assert "event.key === 'n' || event.key === 'N'" in rendered
    assert "html.static-export .presenter-notes" in rendered
    assert re.search(
        r"\.formula\s*\{\s*background:\s*transparent;\s*border:\s*0;"
        r"\s*box-shadow:\s*none;",
        rendered,
    )

    payload_match = re.search(
        r'<script type="application/json" id="speaker-notes-data">(.*?)</script>',
        rendered,
        flags=re.DOTALL,
    )
    assert payload_match is not None
    payload = json.loads(payload_match.group(1))
    assert [entry["id"] for entry in payload] == [
        "slide-001",
        "slide-002",
        "slide-003",
    ]
    assert "</script>" not in payload_match.group(1)
    assert payload[-1]["text"].startswith("Do not emit </script>")
