from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .errors import FrontendSlidesError
from .models import BeamerDeck, BeamerSlide, ContentElement, ListItem


NOTE_MARKER_RE = re.compile(
    r"^<!--\s*speaker-note:\s*(slide-(?P<number>\d{3,}))\s*-->\s*$",
    re.MULTILINE,
)
NOTE_HEADING_RE = re.compile(
    r"^##\s+Slide\s+(?P<number>\d{3,}):\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)
LEGACY_HEADING_RE = re.compile(
    r"^##\s+Section\s+(?P<number>\d+):\s*(?P<title>.+?)\s*$",
    re.MULTILINE,
)
SEPARATOR_RE = re.compile(r"\n\s*---\s*(?:\n|$)")


@dataclass(frozen=True)
class SpeakerNote:
    """One validated note correlated to one rendered slide."""

    id: str
    index: int
    title: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "index": self.index,
            "title": self.title,
            "text": self.text,
        }

    def to_manifest_entry(self) -> dict[str, object]:
        return {
            "id": self.id,
            "index": self.index,
            "title": self.title,
            "note_sha256": self.sha256,
        }


def stable_slide_id(index: int) -> str:
    if index < 1:
        raise ValueError("Slide indexes are one-based.")
    return f"slide-{index:03d}"


def slide_title(deck: BeamerDeck, slide: BeamerSlide) -> str:
    if slide.is_titlepage:
        return deck.title
    return slide.title.strip() or "Untitled"


def normalize_title(value: str) -> str:
    """Normalize titles for correlation without discarding meaningful words."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"[*_`]+", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized.casefold()


def deterministic_title_note(title: str) -> str:
    return (
        f"Welcome learners to {title}. Briefly orient them to the chapter's "
        "purpose, learning goals, and the progression of the slides that follow."
    )


def parse_speaker_notes(markdown: str) -> list[SpeakerNote]:
    """Parse canonical note blocks from ``script.md``.

    Each block begins with a stable HTML-comment marker followed by a visible
    heading. Requiring both keeps the document pleasant to read while giving
    the renderer an unambiguous machine contract.
    """
    markers = list(NOTE_MARKER_RE.finditer(markdown))
    if not markers:
        raise FrontendSlidesError(
            "script.md has no speaker-note markers; expected "
            "'<!-- speaker-note: slide-001 -->'."
        )
    marker_ids = [marker.group(1) for marker in markers]
    duplicate_ids = sorted(
        note_id for note_id in set(marker_ids) if marker_ids.count(note_id) > 1
    )
    if duplicate_ids:
        raise FrontendSlidesError(
            "Duplicate speaker-note ID: " + ", ".join(duplicate_ids) + "."
        )

    notes: list[SpeakerNote] = []
    for position, marker in enumerate(markers):
        block_start = marker.end()
        block_end = markers[position + 1].start() if position + 1 < len(markers) else len(markdown)
        block = markdown[block_start:block_end]
        heading = NOTE_HEADING_RE.search(block)
        if not heading:
            raise FrontendSlidesError(
                f"{marker.group(1)} is missing its '## Slide NNN: Title' heading."
            )
        prefix = block[: heading.start()]
        if prefix.strip():
            raise FrontendSlidesError(
                f"{marker.group(1)} has unexpected content before its slide heading."
            )
        marker_number = int(marker.group("number"))
        heading_number = int(heading.group("number"))
        if marker_number != heading_number:
            raise FrontendSlidesError(
                f"{marker.group(1)} disagrees with heading number {heading_number:03d}."
            )
        body = block[heading.end():]
        separator = SEPARATOR_RE.search(body)
        if separator:
            body = body[: separator.start()]
        text = body.strip()
        notes.append(
            SpeakerNote(
                id=marker.group(1),
                index=marker_number,
                title=heading.group("title").strip(),
                text=text,
            )
        )
    return notes


def load_speaker_notes(path: Path | str) -> list[SpeakerNote]:
    script_path = Path(path)
    if not script_path.is_file() or script_path.stat().st_size == 0:
        raise FrontendSlidesError(f"Speaker notes are missing or empty: {script_path}")
    return parse_speaker_notes(script_path.read_text(encoding="utf-8"))


def validate_speaker_notes(
    deck: BeamerDeck,
    notes: Sequence[SpeakerNote],
) -> list[str]:
    errors: list[str] = []
    if len(notes) != deck.slide_count:
        errors.append(
            f"Speaker-note count {len(notes)} does not match slide count {deck.slide_count}."
        )

    seen: set[str] = set()
    for expected_index, note in enumerate(notes, 1):
        expected_id = stable_slide_id(expected_index)
        if note.id in seen:
            errors.append(f"Duplicate speaker-note ID: {note.id}.")
        seen.add(note.id)
        if note.index != expected_index or note.id != expected_id:
            errors.append(
                f"Speaker note {expected_index} must use ordered ID {expected_id}, "
                f"found {note.id}."
            )
        if not note.text.strip():
            errors.append(f"{note.id} has empty speaker notes.")
        if expected_index <= deck.slide_count:
            expected_title = slide_title(deck, deck.slides[expected_index - 1])
            if normalize_title(note.title) != normalize_title(expected_title):
                errors.append(
                    f"{note.id} title {note.title!r} does not match rendered "
                    f"slide title {expected_title!r}."
                )
    return errors


def correlate_speaker_notes(
    deck: BeamerDeck,
    markdown_or_notes: str | Sequence[SpeakerNote],
) -> list[SpeakerNote]:
    notes = (
        parse_speaker_notes(markdown_or_notes)
        if isinstance(markdown_or_notes, str)
        else list(markdown_or_notes)
    )
    errors = validate_speaker_notes(deck, notes)
    if errors:
        raise FrontendSlidesError("Speaker-note correlation failed: " + "; ".join(errors))
    return notes


def render_speaker_notes_markdown(
    deck: BeamerDeck,
    content_notes: Sequence[str],
    *,
    document_title: str = "Slides Script",
) -> str:
    """Create canonical ``script.md`` from finalized slide order.

    ``content_notes`` excludes title pages. Title-page notes are deterministic,
    so model-generated notes remain mapped only to the content frames they were
    authored from.
    """
    expected_content = sum(not slide.is_titlepage for slide in deck.slides)
    if len(content_notes) != expected_content:
        raise FrontendSlidesError(
            f"Cannot compile script.md: received {len(content_notes)} content notes "
            f"for {expected_content} content slides."
        )
    content_iterator = iter(content_notes)
    notes: list[SpeakerNote] = []
    for index, slide in enumerate(deck.slides, 1):
        title = slide_title(deck, slide)
        text = (
            deterministic_title_note(title)
            if slide.is_titlepage
            else str(next(content_iterator)).strip()
        )
        notes.append(
            SpeakerNote(
                id=stable_slide_id(index),
                index=index,
                title=title,
                text=text,
            )
        )
    errors = validate_speaker_notes(deck, notes)
    if errors:
        raise FrontendSlidesError("Cannot compile script.md: " + "; ".join(errors))
    return _render_markdown(document_title, notes)


def upgrade_legacy_script(deck: BeamerDeck, markdown: str) -> str:
    """Upgrade a legacy ``## Section`` script when titles align exactly.

    A mismatch is intentionally fatal: silently attaching a plausible note to
    the wrong slide is worse than requiring note-only repair.
    """
    if NOTE_MARKER_RE.search(markdown):
        correlate_speaker_notes(deck, markdown)
        return markdown

    headings = list(LEGACY_HEADING_RE.finditer(markdown))
    expected_slides = [slide for slide in deck.slides if not slide.is_titlepage]
    if len(headings) != len(expected_slides):
        raise FrontendSlidesError(
            "Legacy script cannot be upgraded safely: "
            f"{len(headings)} sections for {len(expected_slides)} content slides."
        )

    content_notes: list[str] = []
    for position, (heading, slide) in enumerate(zip(headings, expected_slides)):
        expected_title = slide_title(deck, slide)
        actual_title = heading.group("title").strip()
        if normalize_title(actual_title) != normalize_title(expected_title):
            raise FrontendSlidesError(
                "Legacy script cannot be upgraded safely: "
                f"section {position + 1} title {actual_title!r} does not match "
                f"rendered slide title {expected_title!r}."
            )
        block_end = headings[position + 1].start() if position + 1 < len(headings) else len(markdown)
        body = markdown[heading.end():block_end]
        separator = SEPARATOR_RE.search(body)
        if separator:
            body = body[: separator.start()]
        note = body.strip()
        if not note:
            raise FrontendSlidesError(
                f"Legacy script cannot be upgraded safely: section {position + 1} is empty."
            )
        content_notes.append(note)

    heading = markdown.splitlines()[0].lstrip("# ").strip() if markdown.strip() else "Slides Script"
    return render_speaker_notes_markdown(
        deck,
        content_notes,
        document_title=heading or "Slides Script",
    )


def repair_speaker_notes_markdown(
    deck: BeamerDeck,
    *,
    document_title: str = "Slides Script",
) -> str:
    """Create correlated replacement notes from the exact parsed slide content.

    This is intentionally a note-only recovery path for legacy decks whose
    historical scripts cannot be aligned safely. It never changes slides.tex
    or assessment.md.
    """
    content_notes = [
        _deterministic_content_note(slide)
        for slide in deck.slides
        if not slide.is_titlepage
    ]
    return render_speaker_notes_markdown(
        deck,
        content_notes,
        document_title=document_title,
    )


def notes_manifest(notes: Iterable[SpeakerNote]) -> list[dict[str, object]]:
    return [note.to_manifest_entry() for note in notes]


def _render_markdown(document_title: str, notes: Sequence[SpeakerNote]) -> str:
    blocks = [f"# {document_title.strip().lstrip('#').strip()}\n"]
    for note in notes:
        blocks.append(
            f"<!-- speaker-note: {note.id} -->\n"
            f"## Slide {note.index:03d}: {note.title}\n\n"
            f"{note.text.strip()}\n\n"
            "---\n"
        )
    return "\n".join(blocks).rstrip() + "\n"


def _deterministic_content_note(slide: BeamerSlide) -> str:
    visible = " ".join(
        fragment
        for element in slide.elements
        for fragment in _element_fragments(element)
        if fragment
    )
    visible = re.sub(r"\s+", " ", visible).strip()
    if len(visible) > 1800:
        visible = visible[:1797].rstrip() + "..."
    detail = (
        f" Walk learners through these visible elements in order: {visible}"
        if visible
        else ""
    )
    return (
        f"Present {slide.title.strip() or 'this slide'}.{detail} "
        "Explain the relationships and any formulas directly from the slide, "
        "then check understanding before advancing."
    )


def _element_fragments(element: ContentElement) -> list[str]:
    fragments = [element.title or "", element.text or ""]
    for item in element.items:
        fragments.extend(_item_fragments(item))
    for row in element.rows:
        fragments.extend(str(cell) for cell in row)
    for child in element.children:
        fragments.extend(_element_fragments(child))
    if not any(fragment.strip() for fragment in fragments) and element.raw:
        fragments.append(element.raw)
    return [str(fragment).strip() for fragment in fragments if str(fragment).strip()]


def _item_fragments(item: ListItem) -> list[str]:
    fragments = [item.text]
    for child in item.children:
        fragments.extend(_element_fragments(child))
    return [str(fragment).strip() for fragment in fragments if str(fragment).strip()]
