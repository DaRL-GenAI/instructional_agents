"""PDF -> Textbook IR ingester.

Reads a PDF textbook and produces the same Textbook IR as ingest_md, by
reconstructing chapter / section structure from text patterns and font-size
cues — a PDF has no explicit heading markup the way markdown does.

Handles two layouts:
  - a whole-book PDF with "Chapter N" headings inside
  - one-chapter-per-file PDFs combined via ingest_pdf_directory

Heading detection needs BOTH cues to agree: a heading must be visually
heading-sized (font larger than body text) AND either match a heading pattern
("Chapter N", "Appendix X", a numbered section "3.2") or be a short line in a
heading-size tier. Requiring both rules out body-text mentions ("in Chapter 2,
we saw..."), running headers, and table-of-contents lines, which match the
pattern but are body-sized.

Text extraction uses PyMuPDF, which recovers inter-word spacing reliably (some
textbook PDFs do not encode explicit space glyphs). Page numbers are the real
PDF page indices (1-based). Text from math fonts is lossy; such paragraphs are
tagged kind="equation" and kept as-is. parser_quality reports parse cleanliness.
"""

from collections import Counter
import dataclasses
from dataclasses import dataclass
from pathlib import Path
import re
import string
from typing import List, Optional, Set

import fitz  # PyMuPDF

from .ingest_md import _blocks_to_chapters
from .schema import Chapter, PageSpan, Textbook


# Fonts whose presence signals mathematical content (extraction is lossy here).
MATH_FONT_HINTS = ("MTSY", "MSAM", "MSBM", "CMSY", "CMMI", "CMEX", "Symbol")

RE_CHAPTER_WORD = re.compile(r"^\s*chapter\s+\d+\b", re.IGNORECASE)
RE_APPENDIX = re.compile(r"^\s*appendix\b", re.IGNORECASE)
RE_SUBSECTION = re.compile(r"^\s*\d+\.\d+\.\d+")
RE_SECTION = re.compile(r"^\s*\d+\.\d+(?!\d)")
RE_BARE_NUMBER = re.compile(r"^\s*\d+\.?\s*$")               # "3" or "3."
RE_BARE_SECTION_NUMBER = re.compile(r"^\s*\d+(\.\d+)+\s*$")  # "3.2", "3.2.1"
RE_FIGURE_CAP = re.compile(r"^\s*(figure|fig\.|table)\s+\d", re.IGNORECASE)
RE_LEADING_INT = re.compile(r"\s*(\d+)")

# Document-level unit titles that count as level-1 headings on an exact match.
# Deliberately excludes "introduction" / "conclusion" / "references" — those
# also occur as per-chapter section headings and must not become chapters.
STRUCTURAL_TITLES = frozenset({
    "preface", "foreword", "glossary", "bibliography", "index",
    "contents", "table of contents", "dedication",
    "acknowledgment", "acknowledgments",
})
# Back-matter titles after which fine heading structure is not worth extracting.
BACK_MATTER_TITLES = frozenset({"glossary", "index", "bibliography"})

# A line is a heading candidate when its font size exceeds body size by this.
HEADING_SIZE_MARGIN = 1.5
# A heading line must be short — not flowing prose or a table-of-contents entry.
HEADING_MAX_CHARS = 80
HEADING_MAX_WORDS = 12
# Lines in the top/bottom this-fraction of a page are header/footer territory.
MARGIN_BAND = 0.08

# Characters considered "clean" for the parser-quality score.
_CLEAN_CHARS = set(string.printable) | set("’‘“”—–…•°×÷±≤≥≠→∞§ﬁﬂ")


def _page_lines(page) -> List[dict]:
    """Extract a page's text lines with font metadata.

    `page` is a PyMuPDF page. PyMuPDF groups spans into visual lines natively
    and recovers spacing reliably. Header/footer filtering is deferred to
    _pdf_to_blocks, which has the document body-size available.

    Returns dicts: {text, size, fontname, top_frac, top, bottom, math_ratio}.
    """
    height = page.rect.height or 1.0
    out: List[dict] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(sp.get("text", "") for sp in spans).strip()
            if not text:
                continue
            bbox = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
            top, bottom = bbox[1], bbox[3]
            sizes: Counter = Counter()
            fonts: Counter = Counter()
            math_chars = 0
            total = 0
            for sp in spans:
                n = max(len(sp.get("text", "")), 1)
                total += n
                sizes[round(sp.get("size", 0.0), 1)] += n
                fonts[sp.get("font", "")] += n
                if any(h in (sp.get("font") or "") for h in MATH_FONT_HINTS):
                    math_chars += n
            out.append({
                "text": text,
                "size": sizes.most_common(1)[0][0],
                "fontname": fonts.most_common(1)[0][0],
                "top_frac": top / height,
                "top": top,
                "bottom": bottom,
                "math_ratio": math_chars / total,
            })
    return out


def _body_size(pages_lines: List[List[dict]]) -> float:
    """Most common font size, weighted by text length = the body-text size."""
    sizes: Counter = Counter()
    for lines in pages_lines:
        for ln in lines:
            sizes[ln["size"]] += len(ln["text"])
    return sizes.most_common(1)[0][0] if sizes else 10.0


def _heading_size_tiers(pages_lines: List[List[dict]], body_size: float) -> List[float]:
    """Distinct heading-candidate font sizes, largest first."""
    big = {
        ln["size"]
        for lines in pages_lines for ln in lines
        if ln["size"] > body_size + HEADING_SIZE_MARGIN
    }
    return sorted(big, reverse=True)


def _heading_level(text: str, size: float, body: float, tiers: List[float]) -> Optional[int]:
    """Return heading level 1/2/3, or None if the line is not a heading.

    A heading must be visually heading-sized (font > body) and short. Level 1
    (chapter) additionally requires a pattern match; font size alone never
    promotes a line to chapter level (some PDFs typeset whole sections at
    chapter-title size).
    """
    t = text.strip()
    # gate 1: must be visually a heading (bigger than body text)
    if size <= body + HEADING_SIZE_MARGIN:
        return None
    # gate 2: headings are short — not flowing prose or TOC lines
    if len(t) > HEADING_MAX_CHARS or len(t.split()) > HEADING_MAX_WORDS:
        return None

    low = t.lower()
    # level 1: pattern + (already-confirmed) heading size
    if RE_CHAPTER_WORD.match(t):
        return 1
    if RE_APPENDIX.match(t):
        return 1
    if low in STRUCTURAL_TITLES:
        return 1
    if RE_BARE_NUMBER.match(t) and size > 1.8 * body:
        return 1  # giant display chapter number (e.g. Han's "3")

    # numbered sections / subsections
    if RE_SUBSECTION.match(t):
        return 3
    if RE_SECTION.match(t):
        return 2

    # size-based fallback: section / subsection only, never a chapter
    if len(tiers) >= 2 and size >= tiers[1]:
        return 2
    return 3


def _classify_pdf_paragraph(text: str, math_ratio: float) -> str:
    """Classify a PDF paragraph by content cues -> Paragraph.kind value."""
    t = text.strip()
    if math_ratio > 0.35:
        return "equation"
    if RE_FIGURE_CAP.match(t):
        return "figure_cap"
    if t.lower().startswith(("example ", "exercise ")):
        return "example"
    return "prose"


def _merge_split_headings(blocks: List[dict]) -> List[dict]:
    """Merge a bare-number heading with the heading line that follows it.

    Textbooks often render a section number ("3.2") and its title
    ("Data Cleaning") as separate runs at different font sizes, emitted as two
    lines. This rejoins them, keeping the number-derived level.
    """
    merged: List[dict] = []
    i = 0
    while i < len(blocks):
        b = blocks[i]
        is_bare = (
            b["type"] == "heading"
            and (RE_BARE_NUMBER.match(b["title"])
                  or RE_BARE_SECTION_NUMBER.match(b["title"]))
        )
        if (is_bare and i + 1 < len(blocks)
                and blocks[i + 1]["type"] == "heading"):
            nxt = blocks[i + 1]
            num = b["title"].strip().rstrip(".")
            combined = dict(b)
            combined["title"] = f"{num} {nxt['title']}".strip()
            merged.append(combined)  # keep b's (number-derived) level
            i += 2
        else:
            merged.append(b)
            i += 1
    return merged


def _merge_wrapped_headings(blocks: List[dict]) -> List[dict]:
    """Merge consecutive level-1 headings on the same page.

    A long chapter / appendix title that wraps to two lines is emitted as two
    heading blocks; on a single page that is always a wrapped title, never two
    real chapters (each chapter starts on its own page).
    """
    merged: List[dict] = []
    for b in blocks:
        if (merged and b["type"] == "heading" and b.get("level") == 1
                and merged[-1]["type"] == "heading" and merged[-1].get("level") == 1
                and merged[-1].get("page") == b.get("page")):
            merged[-1] = dict(merged[-1])
            merged[-1]["title"] = f"{merged[-1]['title']} {b['title']}".strip()
        else:
            merged.append(b)
    return merged


def _pdf_to_blocks(doc) -> tuple:
    """Walk a PyMuPDF document; return (blocks, total_chars, clean_chars).

    blocks match ingest_md's format with an extra 'page' (1-based PDF page).
    Header/footer lines (small text in the page margins) are dropped. Heading
    detection switches off once a back-matter unit (glossary / index /
    bibliography) is reached — that content has no chapter structure worth
    extracting and is often typeset at heading-size.
    """
    pages_lines = [_page_lines(doc[i]) for i in range(doc.page_count)]
    body = _body_size(pages_lines)
    tiers = _heading_size_tiers(pages_lines, body)

    blocks: List[dict] = []
    para_lines: List[dict] = []
    total_chars = 0
    clean_chars = 0
    in_back_matter = False

    def flush_paragraph() -> None:
        nonlocal para_lines
        if para_lines:
            text = " ".join(ln["text"] for ln in para_lines).strip()
            if text:
                math_ratio = sum(ln["math_ratio"] for ln in para_lines) / len(para_lines)
                blocks.append({
                    "type": "paragraph",
                    "kind": _classify_pdf_paragraph(text, math_ratio),
                    "text": text,
                    "page": para_lines[0]["page"],
                    "line_no": 0,
                })
        para_lines = []

    for pi, lines in enumerate(pages_lines, start=1):
        prev_bottom: Optional[float] = None
        for ln in lines:
            # drop running headers / footers: margin-band lines that are not
            # themselves heading-sized (a chapter heading at the page top stays)
            in_margin = ln["top_frac"] < MARGIN_BAND or ln["top_frac"] > 1 - MARGIN_BAND
            if in_margin and ln["size"] <= body + HEADING_SIZE_MARGIN:
                continue
            ln["page"] = pi
            total_chars += len(ln["text"])
            clean_chars += sum(1 for ch in ln["text"] if ch in _CLEAN_CHARS)
            level = None if in_back_matter else _heading_level(
                ln["text"], ln["size"], body, tiers)
            if level is not None:
                flush_paragraph()
                blocks.append({
                    "type": "heading",
                    "level": level,
                    "title": ln["text"],
                    "page": pi,
                    "line_no": 0,
                })
                if ln["text"].strip().lower() in BACK_MATTER_TITLES:
                    in_back_matter = True
            else:
                # paragraph break on a large vertical gap between lines
                if prev_bottom is not None and ln["top"] - prev_bottom > body * 1.2:
                    flush_paragraph()
                para_lines.append(ln)
            prev_bottom = ln["bottom"]
    flush_paragraph()
    return blocks, total_chars, clean_chars


def _parser_quality(total_chars: int, clean_chars: int) -> float:
    """Fraction of extracted characters that are well-formed (0..1)."""
    if total_chars == 0:
        return 0.0
    return round(clean_chars / total_chars, 3)


def _finalize_real_pages(textbook: Textbook) -> None:
    """Fill Section/Chapter PageSpans from the real PDF page numbers already
    carried on each Paragraph."""
    for chapter in textbook.chapters:
        ch_pages: List[int] = []
        for section in chapter.sections:
            sec_pages = [p.page for p in section.paragraphs if p.page > 0]
            if sec_pages:
                section.pages = PageSpan(start=min(sec_pages), end=max(sec_pages))
                ch_pages.extend(sec_pages)
        if ch_pages:
            chapter.pages = PageSpan(start=min(ch_pages), end=max(ch_pages))


def _renumber_chapter(chapter: Chapter, new_num: int) -> None:
    """Rewrite a chapter's number and all nested IDs to a new chapter index."""
    chapter.number = new_num
    chapter.chapter_id = f"ch{new_num}"
    for s_idx, section in enumerate(chapter.sections, start=1):
        section.section_id = f"ch{new_num}.s{s_idx}"
        for p_idx, para in enumerate(section.paragraphs, start=1):
            para.para_id = f"ch{new_num}.s{s_idx}.p{p_idx:02d}"


def _blocks_to_textbook_chapters(blocks: List[dict]) -> List[Chapter]:
    """Run the shared block grouping after PDF-specific heading merges."""
    blocks = _merge_split_headings(blocks)
    blocks = _merge_wrapped_headings(blocks)
    return _blocks_to_chapters(blocks)


def ingest_pdf_file(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Ingest a single PDF (a whole book or one chapter) into a Textbook IR."""
    path = Path(path)
    doc = fitz.open(path)
    try:
        blocks, total_chars, clean_chars = _pdf_to_blocks(doc)
    finally:
        doc.close()
    textbook = Textbook(
        textbook_id=textbook_id,
        title=title,
        authors=authors or [],
        edition=edition,
        source_format="pdf",
        parser_quality=_parser_quality(total_chars, clean_chars),
        chapters=_blocks_to_textbook_chapters(blocks),
    )
    _finalize_real_pages(textbook)
    return textbook


def _file_sort_key(p: Path) -> tuple:
    """Sort PDF files by any leading integer in the filename, then by name.

    Keeps "2---...pdf" before "10---...pdf" (a plain string sort would not).
    """
    m = RE_LEADING_INT.match(p.name)
    return (int(m.group(1)) if m else 10 ** 9, p.name)


def ingest_pdf_directory(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Ingest a folder of per-chapter PDF files into one Textbook IR.

    Each ``*.pdf`` contributes one or more chapters; the chapters are
    concatenated and renumbered. Files are processed in leading-number order.
    """
    path = Path(path)
    pdf_files = sorted(
        (p for p in path.iterdir() if p.suffix.lower() == ".pdf"),
        key=_file_sort_key,
    )
    all_chapters: List[Chapter] = []
    quals: List[float] = []
    for pf in pdf_files:
        doc = fitz.open(pf)
        try:
            blocks, total_chars, clean_chars = _pdf_to_blocks(doc)
        finally:
            doc.close()
        all_chapters.extend(_blocks_to_textbook_chapters(blocks))
        quals.append(_parser_quality(total_chars, clean_chars))
    for idx, chapter in enumerate(all_chapters, start=1):
        _renumber_chapter(chapter, idx)
    textbook = Textbook(
        textbook_id=textbook_id,
        title=title,
        authors=authors or [],
        edition=edition,
        source_format="pdf",
        parser_quality=round(sum(quals) / len(quals), 3) if quals else 0.0,
        chapters=all_chapters,
    )
    _finalize_real_pages(textbook)
    return textbook


# --------------------------------------------------------------------- #
# Alternative ingestion path — pymupdf4llm + markdown ingester
# --------------------------------------------------------------------- #
#
# The font-size / pattern-detection ingester above works on plain text
# pulled from PyMuPDF's `page.get_text()`. Plain text mangles equations
# (math glyphs collapse to noise), garbles tables (cell boundaries are
# lost), and drops list structure — all of which hurt downstream
# retrieval. The verifier's `retrieval_bad` slice was 20 % on Han's
# math-heavy textbook largely because of this.
#
# pymupdf4llm.to_markdown() does a much better job: equations come out
# as LaTeX-ish inline math, tables come out as markdown tables, headings
# come out as explicit `##` markers. We pass that output through the
# existing markdown ingester (`ingest_md._extract_blocks` +
# `_blocks_to_chapters`) so chapters / sections / paragraphs all land
# in the same `Textbook` IR shape as before.
#
# pymupdf4llm emits every heading at `##` level regardless of nesting.
# We normalise the markdown first: promote chapter boundaries to `#`
# and demote `N.N.N` patterns to `###` (treated as prose paragraphs by
# the IR builder). Numbered `N.N` headings stay at `##` (sections).
#
# Chapter boundaries are recognised from two shapes:
#   * an explicit "Chapter N ..." heading — unless it carries a trailing
#     page number (a table-of-contents entry) or repeats a chapter
#     number already promoted (a running header);
#   * a page-top "Title N" heading whose standalone number is the next
#     chapter in sequence and whose page continues with prose — the
#     opening-page layout of textbooks that print the chapter number as
#     a display numeral beside the title rather than as "Chapter N".


_PDF_MD_HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
_PDF_MD_NUMBER_PREFIX_RE = re.compile(r"^[\*_\[\s]*(\d+\.\d+(?:\.\d+)?)\s")
# Explicit chapter markers: "Chapter 12", "**Chapter 12**", "Chapter 12: Title",
# "Appendix A", "Part II" — detected after stripping leading markdown decoration.
_PDF_MD_CHAPTER_PATTERN_RE = re.compile(
    r"^[\*_\s]*(?:Chapter|Appendix|Part|Section|Unit)\s+(?:\d+|[A-Z]|[IVX]+)\b",
    re.IGNORECASE,
)
_PDF_MD_CHAPTER_NUM_RE = re.compile(r"(?:Chapter|Unit)\s+(\d+)", re.IGNORECASE)
# A chapter-keyword heading ending in a bare integer is a reference line
# (TOC entry with its page number), not a chapter boundary.
_PDF_MD_TRAILING_INT_RE = re.compile(r"\s\d{1,4}\s*$")
# Standalone 1-2 digit integer (not part of "3.1" or a longer number).
_PDF_MD_STANDALONE_INT_RE = re.compile(r"(?<![\d.])(\d{1,2})(?![\d.])")
_PDF_MD_EMPHASIS_RE = re.compile(r"[\*_\[\]]")
# Numbered labels that sit at the top of a page without opening a chapter
# ("Figure 2", "Table 3", "Example 4"): the word right before the number.
_PDF_MD_CAPTION_WORD_RE = re.compile(
    r"(?:fig(?:ure)?s?|tables?|examples?|exercises?|steps?|algorithms?|"
    r"equations?|eqs?|listings?|box(?:es)?|problems?|lemmas?|theorems?|"
    r"definitions?|proofs?|corollar(?:y|ies)|propositions?|remarks?|notes?|"
    r"cases?|questions?|solutions?|activit(?:y|ies)|labs?|plates?|charts?|"
    r"exhibits?|pages?|slides?|items?)\.?",
    re.IGNORECASE,
)


@dataclass
class HeadingState:
    """Chapter-detection state threaded across per-page normaliser calls.

    ``solid_numbers`` are chapter numbers whose promoted heading was followed
    by body prose on its page (a real chapter opening). Only those make a
    later heading with the same number a running header; a number promoted
    from a hollow entry (a contents line) yields to the real opening."""

    seen_chapter: bool = False
    promoted_numbers: Set[int] = dataclasses.field(default_factory=set)
    max_number: int = 0
    solid_numbers: Set[int] = dataclasses.field(default_factory=set)


def _looks_like_body_prose(text: str) -> bool:
    """True when ``text`` reads as running prose rather than a TOC/index.

    Chapter-opening pages follow their title with paragraphs; contents
    pages follow theirs with digit-dense entry lists. Sampled on the
    first 500 non-space characters.
    """
    sample = re.sub(r"\s", "", text)[:500]
    if len(sample) < 200:
        return False
    digits = sum(c.isdigit() for c in sample)
    return digits / len(sample) < 0.10


def _match_title_number_opening(
    plain: str, state: "HeadingState",
) -> Optional[tuple[int, str]]:
    """Match a chapter-opening heading of the form "Title N" / "Ti N tle".

    Requires exactly one standalone small integer that is the next
    chapter number in sequence, with a title-like remainder. Returns
    ``(number, title)`` or None.
    """
    ints = [(m.start(), m.group(1))
            for m in _PDF_MD_STANDALONE_INT_RE.finditer(plain)]
    if len(ints) != 1:
        return None
    pos, tok = ints[0]
    number = int(tok)
    if number > 40 or number != state.max_number + 1:
        return None
    before = plain[:pos].split()
    if before and _PDF_MD_CAPTION_WORD_RE.fullmatch(before[-1]):
        return None  # "Figure 2", "Table 3" — a label, not a chapter title
    title = (plain[:pos] + plain[pos + len(tok):]).strip()
    title = re.sub(r"\s{2,}", " ", title)
    if sum(c.isalpha() for c in title) < 3 or not title[:1].isupper():
        return None
    return number, title


def _normalize_pdf_markdown_headings(
    md_text: str,
    seen_chapter: bool = False,
    state: Optional[HeadingState] = None,
    page_start: bool = False,
) -> tuple[str, bool]:
    """Convert pymupdf4llm's uniform `##` headings into the level
    hierarchy that the markdown ingester expects.

    Heuristics (applied in order; first match wins):
      * ``## Chapter N ...`` / ``## Appendix X ...`` / ``## Part I`` /
        ``## Unit 3`` -> ``#`` (explicit chapter — handles multi-chapter
        PDFs like pattern-catalog books) — UNLESS the heading ends in a
        bare integer (a TOC entry carrying its page number), sits on a
        page with other "Chapter N" headings (a contents page), or repeats
        a chapter number already opened with body prose (a running
        header); those demote to ``###``.
      * ``## N.N ...`` -> ``##`` (top-level numbered section, kept).
      * ``## N.N.N ...`` -> ``###`` (subsection — emitted as prose
        paragraph by the IR builder).
      * Page-top ``## Title N`` where N is the next chapter number in
        sequence, the word before N is not a caption label ("Figure",
        "Table", ...), and the page continues with prose -> ``# Chapter N
        Title`` (the display-numeral opening-page layout; only when
        ``page_start`` is True).
      * First otherwise-unnumbered ``##`` -> ``#`` (handles single-chapter
        PDFs where the chapter title isn't prefixed with "Chapter N").
      * Subsequent unnumbered ``##`` -> ``###`` (sub-section labels like
        "Method:", "Figure 10.15", "Key takeaways", etc. that pymupdf4llm
        emits as headings but aren't structural breaks).
      * Other levels (already ``#``, ``###+``, or non-heading lines) are
        left alone.

    The ``seen_chapter`` argument lets callers thread the
    chapter-promotion state ACROSS multiple invocations — useful when
    pymupdf4llm yields one markdown block per source page and a
    later page's first unnumbered ``##`` should be treated as a
    sub-section rather than a fresh chapter. Returns a
    ``(normalised_text, seen_chapter_after)`` tuple so callers can
    chain calls without losing state.

    ``state`` (optional) carries the richer cross-page record — chapter
    numbers already promoted and the running maximum — enabling two
    protections the bool alone cannot give: TOC/running-header
    suppression for "Chapter N" headings, and page-top "Title N"
    opening detection (only attempted when ``page_start`` is True,
    i.e. the call receives exactly one source page). When ``state`` is
    given it is mutated in place and is authoritative over the bool.

    Operates line-by-line on the raw markdown text.
    """
    if state is None:
        state = HeadingState(seen_chapter=seen_chapter)
    lines = md_text.split("\n")
    out_lines: List[str] = []
    content_seen = False

    def _is_chapter_heading(line: str) -> bool:
        hm = _PDF_MD_HEADING_RE.match(line)
        return bool(hm and len(hm.group(1)) == 2
                    and _PDF_MD_CHAPTER_PATTERN_RE.match(hm.group(2)))

    chapter_rows = [i for i, l in enumerate(lines) if _is_chapter_heading(l)]
    # One source page carrying several "Chapter N" headings is a contents
    # page: none of its entries opens a chapter.
    contents_page = page_start and len(chapter_rows) >= 2

    def _prose_follows(idx: int) -> bool:
        stop = next((i for i in chapter_rows if i > idx), len(lines))
        return _looks_like_body_prose("\n".join(lines[idx + 1:stop]))

    for idx, line in enumerate(lines):
        m = _PDF_MD_HEADING_RE.match(line)
        if not m:
            out_lines.append(line)
            if line.strip():
                content_seen = True
            continue
        hashes, content = m.group(1), m.group(2)
        if len(hashes) != 2:
            out_lines.append(line)
            content_seen = True
            continue
        at_page_top = page_start and not content_seen
        content_seen = True
        plain = _PDF_MD_EMPHASIS_RE.sub("", content).strip()
        # Explicit "Chapter N" / "Appendix X" / "Part I" / "Unit 3" heading.
        if _PDF_MD_CHAPTER_PATTERN_RE.match(content):
            num_m = _PDF_MD_CHAPTER_NUM_RE.search(plain)
            number = int(num_m.group(1)) if num_m else None
            # A trailing integer AFTER the title ("Chapter 4 Title 125")
            # is a TOC entry's page number; the prefix's own number
            # ("Chapter 12" with no title) must not trigger this.
            prefix_m = _PDF_MD_CHAPTER_PATTERN_RE.match(plain)
            remainder = plain[prefix_m.end():] if prefix_m else plain
            is_reference = (_PDF_MD_TRAILING_INT_RE.search(remainder) is not None
                            or contents_page)
            # A repeat is a running header only when the number was already
            # promoted from a real opening (prose followed it); a number
            # taken by a hollow contents line yields to the real opening.
            is_repeat = number is not None and number in state.solid_numbers
            if is_reference or is_repeat:
                out_lines.append(f"### {content}")
            else:
                out_lines.append(f"# {content}")
                state.seen_chapter = True
                if number is not None:
                    state.promoted_numbers.add(number)
                    state.max_number = max(state.max_number, number)
                    if _prose_follows(idx):
                        state.solid_numbers.add(number)
            continue
        # Numbered "N.N" or "N.N.N" — section vs subsection.
        num = _PDF_MD_NUMBER_PREFIX_RE.match(content)
        if num is not None:
            dot_count = num.group(1).count(".")
            if dot_count == 1:
                out_lines.append(f"## {content}")
            else:
                out_lines.append(f"### {content}")
            continue
        # Page-top "Title N" chapter opening (display-numeral layout).
        if at_page_top:
            opening = _match_title_number_opening(plain, state)
            if opening is not None and _looks_like_body_prose(
                "\n".join(lines[idx + 1:])
            ):
                number, title = opening
                out_lines.append(f"# Chapter {number} {title}")
                state.seen_chapter = True
                state.promoted_numbers.add(number)
                state.solid_numbers.add(number)
                state.max_number = number
                continue
        # Unnumbered heading.
        if not state.seen_chapter:
            out_lines.append(f"# {content}")
            state.seen_chapter = True
        else:
            out_lines.append(f"### {content}")
    return "\n".join(out_lines), state.seen_chapter


def ingest_pdf_file_via_markdown(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Ingest a single PDF via pymupdf4llm.to_markdown() + markdown ingester.

    Cleaner extraction for math-heavy / table-heavy PDFs: equations
    become LaTeX, tables become markdown, headings come through
    explicitly. Falls back to plain-text `ingest_pdf_file` if
    pymupdf4llm is unavailable or the markdown output yields no
    chapters (rare; we have not seen it on real input).
    """
    try:
        import pymupdf4llm
    except ImportError:
        # Graceful degradation: no pymupdf4llm in the env -> use the
        # original plain-text ingester so the project still runs.
        return ingest_pdf_file(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )
    from .ingest_md import _extract_blocks, _assign_pages
    path = Path(path)
    md_text = pymupdf4llm.to_markdown(str(path), page_chunks=False, show_progress=False)
    md_text, _ = _normalize_pdf_markdown_headings(md_text)
    blocks = _extract_blocks(md_text)
    chapters = _blocks_to_chapters(blocks)
    if not chapters:
        # No chapter structure detected — fall back to plain-text path
        # so we at least get *something* rather than an empty IR.
        return ingest_pdf_file(
            path, textbook_id=textbook_id, title=title,
            authors=authors, edition=edition,
        )
    textbook = Textbook(
        textbook_id=textbook_id, title=title,
        authors=authors or [], edition=edition,
        source_format="pdf",
        parser_quality=1.0,  # pymupdf4llm doesn't expose a quality score
        chapters=chapters,
    )
    _assign_pages(textbook)
    return textbook


def ingest_pdf_directory_via_markdown(
    path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Ingest a folder of per-chapter PDFs via pymupdf4llm.

    Each ``*.pdf`` is run through `ingest_pdf_file_via_markdown` and the
    resulting chapters concatenated + renumbered. Mirrors the layout of
    `ingest_pdf_directory` (the plain-text variant).
    """
    path = Path(path)
    pdf_files = sorted(
        (p for p in path.iterdir() if p.suffix.lower() == ".pdf"),
        key=_file_sort_key,
    )
    all_chapters: List[Chapter] = []
    for pf in pdf_files:
        sub = ingest_pdf_file_via_markdown(
            pf, textbook_id=textbook_id, title=title,
        )
        all_chapters.extend(sub.chapters)
    for idx, chapter in enumerate(all_chapters, start=1):
        _renumber_chapter(chapter, idx)
    textbook = Textbook(
        textbook_id=textbook_id, title=title,
        authors=authors or [], edition=edition,
        source_format="pdf",
        parser_quality=1.0,
        chapters=all_chapters,
    )
    # The per-PDF ingester already assigned synthetic pages within each
    # source PDF; re-assign at the top-level so page numbers are
    # consistent across the concatenated book.
    from .ingest_md import _assign_pages
    _assign_pages(textbook)
    return textbook
