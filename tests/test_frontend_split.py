import json
from pathlib import Path

from src.frontend_slides.models import BeamerDeck, BeamerSlide, ContentElement, ListItem
from src.frontend_slides.split import (
    SPLIT_THRESHOLD,
    TARGET_PART_WEIGHT,
    split_overloaded_slides,
    write_split_report,
)
from src.frontend_slides.weights import slide_weight


def _text(content: str = "Short line.") -> ContentElement:
    return ContentElement(kind="text", text=content)


def _list(count: int, ordered: bool = False) -> ContentElement:
    return ContentElement(
        kind="list",
        ordered=ordered,
        items=[ListItem(text=f"Item {i + 1}") for i in range(count)],
    )


def _deck(slides: list[BeamerSlide]) -> BeamerDeck:
    return BeamerDeck(source_path=Path("deck.tex"), title="Deck", slides=slides)


def _slide(index: int, elements: list[ContentElement], title: str = "Topic", **kwargs) -> BeamerSlide:
    return BeamerSlide(index=index, title=title, elements=elements, raw_tex="", **kwargs)


def test_light_slides_are_untouched() -> None:
    deck = _deck([_slide(1, [_text(), _list(4)])])

    result, records = split_overloaded_slides(deck)

    assert records == []
    assert result.slide_count == 1
    assert result.slides[0].elements == deck.slides[0].elements


def test_heavy_list_splits_with_cont_title_and_ol_continuation() -> None:
    deck = _deck(
        [
            _slide(1, [_list(SPLIT_THRESHOLD + 3, ordered=True)], title="Steps"),
            _slide(2, [_text()], title="After"),
        ]
    )

    result, records = split_overloaded_slides(deck)

    assert len(records) == 1
    parts = records[0].parts
    assert len(parts) >= 2
    assert parts[0].title == "Steps"
    assert parts[1].title == "Steps (cont.)"
    assert [slide.index for slide in result.slides] == list(range(1, result.slide_count + 1))
    assert result.slides[-1].title == "After"

    first, second = result.slides[0].elements[0], result.slides[1].elements[0]
    assert second.start == first.start + len(first.items)
    assert all(slide_weight(slide) <= SPLIT_THRESHOLD for slide in result.slides)


def test_lead_in_text_moves_with_what_it_introduces() -> None:
    lead_in = _text("The following table summarises:")
    table = ContentElement(kind="table", rows=[["a", "b"]] * 6)
    deck = _deck([_slide(1, [_list(7), lead_in, table])])

    result, records = split_overloaded_slides(deck)

    assert len(records) == 1
    for slide in result.slides:
        if lead_in in slide.elements:
            assert table in slide.elements, "lead-in text was separated from its table"


def test_titlepage_and_atomic_elements_are_never_split() -> None:
    titlepage = _slide(1, [], title="", is_titlepage=True)
    code = ContentElement(kind="code", text="x = 1\n" * 40)
    deck = _deck([titlepage, _slide(2, [code])])

    result, records = split_overloaded_slides(deck)

    assert records == []
    assert result.slide_count == 2


def test_heavy_block_splits_by_children_keeping_title() -> None:
    block = ContentElement(
        kind="block",
        title="Definition",
        children=[_list(TARGET_PART_WEIGHT), _list(TARGET_PART_WEIGHT)],
    )
    deck = _deck([_slide(1, [block], title="Concepts")])

    result, records = split_overloaded_slides(deck)

    assert len(records) == 1
    assert result.slide_count >= 2
    for slide in result.slides:
        assert slide.elements[0].kind == "block"
        assert slide.elements[0].title == "Definition"


def test_display_equations_inside_list_items_trigger_readable_splits() -> None:
    introduction = _text(
        r"Consider the differential equation: \[\frac{dy}{dt}+3y=5\] Steps:"
    )
    steps = ContentElement(
        kind="list",
        ordered=True,
        items=[
            ListItem(text=rf"Step {index}: \[Y_{index}(s)=\frac{{{index}}}{{s+1}}\]")
            for index in range(1, 7)
        ],
    )
    deck = _deck([_slide(1, [introduction, steps], title="Worked Example")])

    result, records = split_overloaded_slides(deck)

    assert len(records) == 1
    assert result.slide_count >= 2
    assert all(slide_weight(slide) <= SPLIT_THRESHOLD for slide in result.slides)


def test_split_report_schema(tmp_path: Path) -> None:
    deck = _deck([_slide(1, [_list(SPLIT_THRESHOLD + 3)], title="Steps")])
    original_count = deck.slide_count
    result, records = split_overloaded_slides(deck)

    path = write_split_report(records, result, original_count, tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "slide-splits.json"
    assert payload["original_frame_count"] == 1
    assert payload["final_slide_count"] == result.slide_count
    assert payload["split_threshold"] == SPLIT_THRESHOLD
    split = payload["splits"][0]
    assert split["source_frame_index"] == 1
    assert split["source_frame_title"] == "Steps"
    assert "exceeds threshold" in split["reason"]
    assert [part["slide_index"] for part in split["parts"]] == [1, 2]
    assert split["parts"][1]["title"] == "Steps (cont.)"
    assert all({"slide_index", "title", "weight", "element_count"} <= set(part) for part in split["parts"])


def test_no_split_report_is_written_with_empty_list(tmp_path: Path) -> None:
    deck = _deck([_slide(1, [_text()])])
    result, records = split_overloaded_slides(deck)

    path = write_split_report(records, result, deck.slide_count, tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["splits"] == []
    assert payload["original_frame_count"] == payload["final_slide_count"] == 1
