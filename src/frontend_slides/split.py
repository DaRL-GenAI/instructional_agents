"""Split overloaded beamer frames into multiple HTML slides.

Dense frames used to rely on aggressive font auto-shrink, which produced
unreadably small text. Instead, frames whose content weight exceeds
SPLIT_THRESHOLD are partitioned into consecutive slides that each stay near
TARGET_PART_WEIGHT, and every split is recorded in slide-splits.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from .models import BeamerDeck, BeamerSlide, ContentElement
from .weights import element_weight, item_weight, slide_weight

# Weights approximate rendered body lines (see weights.py). Slides past the
# threshold overflow the 1080px stage even after the renderer switches to a
# two-column layout, so they are split instead of shrunk.
SPLIT_THRESHOLD = 13
MAX_ELEMENTS = 6
TARGET_PART_WEIGHT = 9
MAX_PART_ELEMENTS = 4
MIN_TRAILING_PART_WEIGHT = 3


@dataclass
class SplitPart:
    slide_index: int
    title: str
    weight: int
    element_count: int


@dataclass
class SplitRecord:
    source_frame_index: int
    source_frame_title: str
    reason: str
    parts: list[SplitPart] = field(default_factory=list)


def split_overloaded_slides(deck: BeamerDeck) -> tuple[BeamerDeck, list[SplitRecord]]:
    records: list[SplitRecord] = []
    # Each entry pairs the slide with the SplitPart to backfill once final indices are known.
    staged: list[tuple[BeamerSlide, SplitPart | None]] = []

    for slide in deck.slides:
        reason = _split_reason(slide)
        parts = _partition_elements(slide.elements) if reason else []
        if len(parts) <= 1:
            staged.append((slide, None))
            continue
        record = SplitRecord(slide.index, slide.title, reason)
        for part_number, elements in enumerate(parts, start=1):
            title = _part_title(slide.title, part_number)
            part = SplitPart(
                slide_index=0,
                title=title,
                weight=sum(element_weight(element) for element in elements),
                element_count=len(elements),
            )
            staged.append((replace(slide, title=title, elements=elements), part))
            record.parts.append(part)
        records.append(record)

    slides: list[BeamerSlide] = []
    for position, (slide, part) in enumerate(staged, start=1):
        slides.append(replace(slide, index=position))
        if part:
            part.slide_index = position
    return replace(deck, slides=slides), records


def write_split_report(
    records: list[SplitRecord],
    deck: BeamerDeck,
    original_frame_count: int,
    output_dir: Path,
) -> Path:
    payload = {
        "source_beamer": str(deck.source_path),
        "original_frame_count": original_frame_count,
        "final_slide_count": deck.slide_count,
        "split_threshold": SPLIT_THRESHOLD,
        "splits": [
            {
                "source_frame_index": record.source_frame_index,
                "source_frame_title": record.source_frame_title,
                "reason": record.reason,
                "parts": [
                    {
                        "slide_index": part.slide_index,
                        "title": part.title,
                        "weight": part.weight,
                        "element_count": part.element_count,
                    }
                    for part in record.parts
                ],
            }
            for record in records
        ],
    }
    path = Path(output_dir) / "slide-splits.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _split_reason(slide: BeamerSlide) -> str:
    if slide.is_titlepage:
        return ""
    weight = slide_weight(slide)
    if weight > SPLIT_THRESHOLD:
        return f"content weight {weight} exceeds threshold {SPLIT_THRESHOLD}"
    if len(slide.elements) > MAX_ELEMENTS:
        return f"element count {len(slide.elements)} exceeds {MAX_ELEMENTS}"
    return ""


def _partition_elements(elements: list[ContentElement]) -> list[list[ContentElement]]:
    units = [unit for element in elements for unit in expand_units(element)]
    parts = _greedy_pack(units, TARGET_PART_WEIGHT, MAX_PART_ELEMENTS)
    _apply_cohesion(parts)
    _merge_light_trailing_part(parts)
    return [part for part in parts if part]


def _greedy_pack(
    units: list[ContentElement], cap: int, max_elements: int | None = None
) -> list[list[ContentElement]]:
    groups: list[list[ContentElement]] = []
    current: list[ContentElement] = []
    current_weight = 0
    for unit in units:
        weight = element_weight(unit)
        full = current and (
            current_weight + weight > cap or (max_elements and len(current) >= max_elements)
        )
        if full:
            groups.append(current)
            current, current_weight = [], 0
        current.append(unit)
        current_weight += weight
    if current:
        groups.append(current)
    return groups


def expand_units(element: ContentElement) -> list[ContentElement]:
    """Break an element heavier than one part into smaller pieces where structure allows.

    Lists split by items (promoting a lone mega-item's children), blocks split by
    children keeping their title; everything else is atomic.
    """
    if element_weight(element) <= TARGET_PART_WEIGHT:
        return [element]
    if element.kind == "list":
        return _split_oversized_list(element)
    if element.kind == "block":
        child_units = [unit for child in element.children for unit in expand_units(child)]
        groups = _greedy_pack(child_units, TARGET_PART_WEIGHT - 1)
        if len(groups) <= 1:
            return [element]
        return [replace(element, children=group) for group in groups]
    return [element]


def _split_oversized_list(element: ContentElement) -> list[ContentElement]:
    if len(element.items) == 1 and element.items[0].children:
        return _promote_single_item(element)
    chunks: list[ContentElement] = []
    items: list = []
    weight = 0
    start = element.start
    for item in element.items:
        weight_of_item = item_weight(item)
        if items and weight + weight_of_item > TARGET_PART_WEIGHT:
            chunks.append(replace(element, items=items, start=start))
            start = start + len(items) if element.ordered else 1
            items, weight = [], 0
        items.append(item)
        weight += weight_of_item
    if items:
        chunks.append(replace(element, items=items, start=start))
    expanded: list[ContentElement] = []
    for chunk in chunks:
        if len(chunk.items) == 1 and chunk.items[0].children and element_weight(chunk) > TARGET_PART_WEIGHT:
            expanded.extend(_promote_single_item(chunk))
        else:
            expanded.append(chunk)
    return expanded


def _promote_single_item(element: ContentElement) -> list[ContentElement]:
    """Hoist a lone bullet's nested content to top level so it can flow across parts.

    The bullet text stays as a childless single-item list, so it still reads as
    the lead-in it was.
    """
    item = element.items[0]
    units: list[ContentElement] = []
    if item.text:
        units.append(replace(element, items=[replace(item, children=[])]))
    for child in item.children:
        units.extend(expand_units(child))
    return units


def _apply_cohesion(parts: list[list[ContentElement]]) -> None:
    """Keep lead-in text with the element it introduces instead of ending a part on it."""
    for index in range(len(parts) - 1):
        part, following = parts[index], parts[index + 1]
        if len(part) > 1 and part[-1].kind == "text" and following and following[0].kind != "text":
            following.insert(0, part.pop())


def _merge_light_trailing_part(parts: list[list[ContentElement]]) -> None:
    """A near-empty final part reads as an orphan; fold it into the previous slide."""
    if len(parts) >= 2:
        trailing_weight = sum(element_weight(element) for element in parts[-1])
        if trailing_weight < MIN_TRAILING_PART_WEIGHT:
            parts[-2].extend(parts.pop())


def _part_title(title: str, part_number: int) -> str:
    if part_number == 1:
        return title
    base = title.strip() or "Continued"
    if not title.strip():
        return base
    if part_number == 2:
        return f"{base} (cont.)"
    return f"{base} (cont. {part_number - 1})"
