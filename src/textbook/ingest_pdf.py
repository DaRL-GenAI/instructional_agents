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
from pathlib import Path
import re
import string
from typing import List, Optional

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
# We normalise the markdown first: promote the first non-numbered
# heading to `#` (chapter title) and demote `N.N.N` patterns to `###`
# (treated as prose paragraphs by the IR builder). Numbered `N.N`
# headings stay at `##` (sections).


_PDF_MD_HEADING_RE = re.compile(r"^(#+)\s+(.*)$")
_PDF_MD_NUMBER_PREFIX_RE = re.compile(r"^[\*_\[\s]*(\d+\.\d+(?:\.\d+)?)\s")
# Explicit chapter markers: "Chapter 12", "**Chapter 12**", "Chapter 12: Title",
# "Appendix A", "Part II" — detected after stripping leading markdown decoration.
_PDF_MD_CHAPTER_PATTERN_RE = re.compile(
    r"^[\*_\s]*(?:Chapter|Appendix|Part|Section|Unit)\s+(?:\d+|[A-Z]|[IVX]+)\b",
    re.IGNORECASE,
)


def _normalize_pdf_markdown_headings(md_text: str, seen_chapter: bool = False) -> tuple[str, bool]:
    """Convert pymupdf4llm's uniform `##` headings into the level
    hierarchy that the markdown ingester expects.

    Heuristics (applied in order; first match wins):
      * ``## Chapter N ...`` / ``## Appendix X ...`` / ``## Part I`` /
        ``## Unit 3`` -> ``#`` (explicit chapter — handles multi-chapter
        PDFs like Agentic Design Patterns).
      * ``## N.N ...`` -> ``##`` (top-level numbered section, kept).
      * ``## N.N.N ...`` -> ``###`` (subsection — emitted as prose
        paragraph by the IR builder).
      * First otherwise-unnumbered ``##`` -> ``#`` (handles single-chapter
        PDFs like Han's per-chapter files where the chapter title isn't
        prefixed with "Chapter N").
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

    Operates line-by-line on the raw markdown text.
    """
    lines = md_text.split("\n")
    out_lines: List[str] = []
    for line in lines:
        m = _PDF_MD_HEADING_RE.match(line)
        if not m:
            out_lines.append(line)
            continue
        hashes, content = m.group(1), m.group(2)
        if len(hashes) != 2:
            out_lines.append(line)
            continue
        # Explicit "Chapter N" / "Appendix X" / "Part I" / "Unit 3" — always a chapter.
        if _PDF_MD_CHAPTER_PATTERN_RE.match(content):
            out_lines.append(f"# {content}")
            seen_chapter = True
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
        # Unnumbered heading.
        if not seen_chapter:
            out_lines.append(f"# {content}")
            seen_chapter = True
        else:
            out_lines.append(f"### {content}")
    return "\n".join(out_lines), seen_chapter


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
