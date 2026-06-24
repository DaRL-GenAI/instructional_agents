"""Markdown -> Textbook IR ingester.

Reads a markdown file or a directory of chapter_NAME/*.md files and produces
a pydantic Textbook instance (see schema.py for the data model). Designed
against a section-per-file deep-learning markdown layout but works for any
CommonMark / MyST-flavored markdown source.

Source format quirks handled:
- Sphinx-style inline directives like :label:`anchor` / :eqlabel:`x` / :numref:`y`
  are stripped from paragraph text (they're cross-ref metadata, not content).
- Display math `$$...$$` paragraphs are classified as kind="equation".
- Image-only paragraphs `![caption](path)` are classified as kind="figure_cap".
- Code fences become kind="example".
- Paragraphs starting with "**Definition" or "Definition:" become kind="definition".
- All other paragraphs are kind="prose".

Markdown has no native page concept, so synthetic page numbers are assigned by
walking paragraphs in source order and incrementing after each ~250 words.
"""

from pathlib import Path
import re
from typing import List, Optional, Tuple

from markdown_it import MarkdownIt

from .schema import (
    Chapter,
    PageSpan,
    Paragraph,
    Section,
    Textbook,
)


# Sphinx/MyST directives appear inline like :label:`anchor`. Strip the
# directive but leave surrounding text intact.
SPHINX_INLINE_RE = re.compile(r":(label|eqlabel|numref|cite|ref):`[^`]*`")

# A paragraph that is entirely a display-math block: $$ ... $$ on its own.
DISPLAY_MATH_RE = re.compile(r"^\s*\$\$.+\$\$\s*$", re.DOTALL)

# A paragraph that is entirely a single image: ![alt](src).
IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^\)]+\)\s*$")

# Words per "page" for synthetic pagination. Ballpark prose textbook density.
WORDS_PER_SYNTHETIC_PAGE = 250


def _strip_sphinx_directives(text: str) -> str:
    """Remove inline :label:/:eqlabel:/:numref: directives, keep surrounding text."""
    return SPHINX_INLINE_RE.sub("", text)


def _classify_paragraph(content: str) -> str:
    """Map raw paragraph text to a Paragraph.kind value."""
    s = content.strip()
    if not s:
        return "prose"
    if DISPLAY_MATH_RE.match(s):
        return "equation"
    if IMAGE_ONLY_RE.match(s):
        return "figure_cap"
    if s.startswith("**Definition") or s.startswith("Definition:"):
        return "definition"
    return "prose"


def _extract_blocks(md_text: str) -> List[dict]:
    """Tokenize markdown and emit a list of structural blocks.

    Each block is one of:
      {"type": "heading", "level": int, "title": str, "line_no": int}
      {"type": "paragraph", "kind": str, "text": str, "line_no": int}

    Code fences are emitted as paragraph blocks with kind="example".
    """
    md = MarkdownIt()
    tokens = md.parse(md_text)
    blocks: List[dict] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])
            line_no = (tok.map[0] + 1) if tok.map else 0
            title = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = _strip_sphinx_directives(tokens[i + 1].content).strip()
            blocks.append({
                "type": "heading",
                "level": level,
                "title": title,
                "line_no": line_no,
            })
            i += 3
        elif tok.type == "paragraph_open":
            line_no = (tok.map[0] + 1) if tok.map else 0
            content = ""
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                content = _strip_sphinx_directives(tokens[i + 1].content).strip()
            if content:
                blocks.append({
                    "type": "paragraph",
                    "kind": _classify_paragraph(content),
                    "text": content,
                    "line_no": line_no,
                })
            i += 3
        elif tok.type == "fence":
            line_no = (tok.map[0] + 1) if tok.map else 0
            text = tok.content.strip()
            if text:
                blocks.append({
                    "type": "paragraph",
                    "kind": "example",
                    "text": text,
                    "line_no": line_no,
                })
            i += 1
        else:
            i += 1
    return blocks


# Chapter/section heading titles from PDF extraction often carry markdown
# emphasis and a trailing page-number artifact, e.g. "**K-Means Clustering 445**"
# or "1.1 **Why Data Mining? 1**". These titles are exactly what the course
# contract binds topics against, so polluted titles degrade binding precision.
# Cleaned at the single point where Chapter/Section are constructed.
_HEADING_EMPHASIS_RE = re.compile(r"[*_`\[\]]+")
_HEADING_TRAILING_PAGENUM_RE = re.compile(r"^(.*\S)\s+(\d{1,3})$")
_HEADING_COUNTING_WORDS = {
    "chapter", "section", "part", "appendix", "unit", "lecture", "week",
    "vol", "volume", "no", "chap", "figure", "fig", "table", "eq", "equation",
    "problem", "exercise", "step", "phase", "level", "lesson", "module",
}


def _clean_heading_title(title: str) -> str:
    """Strip markdown emphasis and a trailing page-number artifact from a
    heading title. Conservative on the page number: only removes a trailing
    1-3 digit integer when the remaining title still has >= 2 words and the
    word before the number is not a counting word, so 'Chapter 8' /
    'Section 3' / 'Top 10 Algorithms' are preserved. Textbook-agnostic."""
    t = _HEADING_EMPHASIS_RE.sub("", title or "").strip()
    m = _HEADING_TRAILING_PAGENUM_RE.match(t)
    if m:
        head = m.group(1).rstrip()
        words = head.split()
        last_word = words[-1].lower().strip(".:,;") if words else ""
        if len(words) >= 2 and last_word not in _HEADING_COUNTING_WORDS:
            t = head
    return t.strip()


def _new_section(chapter_num: int, section_idx: int, title: str) -> Section:
    return Section(
        section_id=f"ch{chapter_num}.s{section_idx}",
        title=_clean_heading_title(title),
        pages=PageSpan(start=0, end=0),
        paragraphs=[],
        concepts=[],
    )


def _new_chapter(chapter_num: int, title: str) -> Chapter:
    return Chapter(
        chapter_id=f"ch{chapter_num}",
        number=chapter_num,
        title=_clean_heading_title(title),
        pages=PageSpan(start=0, end=0),
        sections=[],
        learning_objectives=[],
    )


def _blocks_to_chapters(blocks: List[dict]) -> List[Chapter]:
    """Group blocks into Chapter/Section/Paragraph based on heading levels.

    Rule: level-1 heading -> new Chapter; level-2 heading -> new Section;
    level-3+ headings are emitted as kind="prose" paragraphs inside the
    current section (treated as subsection markers). Paragraphs that appear
    before the first section heading are placed in an implicit
    "Chapter intro" section so every paragraph has a parent section.
    """
    chapters: List[Chapter] = []
    current_chapter: Optional[Chapter] = None
    current_section: Optional[Section] = None
    chapter_idx = 0
    section_idx = 0
    para_idx = 0

    def ensure_chapter():
        nonlocal current_chapter, chapter_idx, section_idx, para_idx, current_section
        if current_chapter is None:
            chapter_idx += 1
            section_idx = 0
            para_idx = 0
            current_chapter = _new_chapter(chapter_idx, "Untitled chapter")
            chapters.append(current_chapter)
            current_section = None

    def ensure_section(default_title: str = "Chapter intro"):
        nonlocal current_section, section_idx, para_idx
        ensure_chapter()
        if current_section is None:
            section_idx += 1
            para_idx = 0
            current_section = _new_section(chapter_idx, section_idx, default_title)
            current_chapter.sections.append(current_section)

    for blk in blocks:
        if blk["type"] == "heading":
            level = blk["level"]
            title = blk["title"]
            if level == 1:
                chapter_idx += 1
                section_idx = 0
                para_idx = 0
                current_chapter = _new_chapter(chapter_idx, title)
                chapters.append(current_chapter)
                current_section = None
            elif level == 2:
                ensure_chapter()
                section_idx += 1
                para_idx = 0
                current_section = _new_section(chapter_idx, section_idx, title)
                current_chapter.sections.append(current_section)
            else:  # level >= 3 -> emit as paragraph (subsection marker)
                ensure_section()
                para_idx += 1
                current_section.paragraphs.append(Paragraph(
                    para_id=f"ch{chapter_idx}.s{section_idx}.p{para_idx:02d}",
                    text=title,
                    page=blk.get("page", 0),
                    kind="prose",
                ))
        else:  # paragraph
            ensure_section()
            para_idx += 1
            current_section.paragraphs.append(Paragraph(
                para_id=f"ch{chapter_idx}.s{section_idx}.p{para_idx:02d}",
                text=blk["text"],
                page=blk.get("page", 0),
                kind=blk["kind"],
            ))

    return chapters


def _assign_pages(textbook: Textbook, words_per_page: int = WORDS_PER_SYNTHETIC_PAGE) -> None:
    """Walk paragraphs in source order and assign synthetic page numbers.

    Page increments when cumulative word count crosses words_per_page. Page
    numbers are shared across chapters (continuous), mirroring physical books.
    Updates each Paragraph.page in place and fills in Section.pages and
    Chapter.pages spans.
    """
    page = 1
    word_count = 0
    for chapter in textbook.chapters:
        chapter_start = page
        for section in chapter.sections:
            section_start = page
            for para in section.paragraphs:
                para.page = page
                word_count += len(para.text.split())
                if word_count >= words_per_page:
                    page += 1
                    word_count = 0
            section.pages = PageSpan(start=section_start, end=page)
        chapter.pages = PageSpan(start=chapter_start, end=page)


def ingest_file(
    path: Path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
    source_format: str = "markdown",
    parser_quality: float = 1.0,
) -> Textbook:
    """Read a single markdown file and return a Textbook IR.

    Level-1 headings (`#`) become Chapters. Level-2 (`##`) become Sections.
    Level-3+ headings are emitted as prose paragraphs within the current
    section. Synthetic page numbers are assigned after parsing.
    """
    path = Path(path)
    md_text = path.read_text(encoding="utf-8")
    blocks = _extract_blocks(md_text)
    chapters = _blocks_to_chapters(blocks)
    textbook = Textbook(
        textbook_id=textbook_id,
        title=title,
        authors=authors or [],
        edition=edition,
        source_format=source_format,
        parser_quality=parser_quality,
        chapters=chapters,
    )
    _assign_pages(textbook)
    return textbook


def ingest_directory(
    path: Path,
    textbook_id: str = "tb1",
    title: str = "Untitled",
    authors: Optional[List[str]] = None,
    edition: Optional[str] = None,
) -> Textbook:
    """Read a directory of chapter_*/ subdirs and return a Textbook IR.

    Layout (chapter-per-directory markdown):
        path/
          chapter_introduction/
            index.md          (chapter intro / single-file chapters)
          chapter_linear-regression/
            index.md
            linear-regression.md
            ...

    Each chapter_NAME/ subdir becomes one Chapter. Each .md file inside
    becomes one Section (index.md is sorted first). Within a section file,
    the level-1 heading (if any) is dropped as redundant, level-2 headings
    become subsection markers (prose paragraphs), and content follows.
    """
    path = Path(path)
    chapter_dirs = sorted([
        d for d in path.iterdir()
        if d.is_dir() and d.name.startswith("chapter_")
    ])
    chapters: List[Chapter] = []
    for ch_idx, ch_dir in enumerate(chapter_dirs, start=1):
        md_files = list(ch_dir.glob("*.md"))
        if not md_files:
            continue
        md_files.sort(key=lambda p: (0 if p.name == "index.md" else 1, p.name))
        chapter_title = ch_dir.name.replace("chapter_", "").replace("-", " ").title()
        sections: List[Section] = []
        section_idx = 0
        for md_file in md_files:
            section_idx += 1
            section_title = md_file.stem.replace("-", " ").replace("_", " ").title()
            md_text = md_file.read_text(encoding="utf-8")
            blocks = _extract_blocks(md_text)
            paragraphs: List[Paragraph] = []
            para_idx = 0
            for blk in blocks:
                if blk["type"] == "heading" and blk["level"] == 1:
                    # Use the first level-1 heading as section title (overrides filename-derived default).
                    if section_title.lower() == md_file.stem.replace("-", " ").replace("_", " ").title().lower():
                        section_title = blk["title"]
                    continue
                if blk["type"] == "heading":
                    para_idx += 1
                    paragraphs.append(Paragraph(
                        para_id=f"ch{ch_idx}.s{section_idx}.p{para_idx:02d}",
                        text=blk["title"],
                        page=0,
                        kind="prose",
                    ))
                else:
                    para_idx += 1
                    paragraphs.append(Paragraph(
                        para_id=f"ch{ch_idx}.s{section_idx}.p{para_idx:02d}",
                        text=blk["text"],
                        page=0,
                        kind=blk["kind"],
                    ))
            sections.append(Section(
                section_id=f"ch{ch_idx}.s{section_idx}",
                title=section_title,
                pages=PageSpan(start=0, end=0),
                paragraphs=paragraphs,
                concepts=[],
            ))
        chapters.append(Chapter(
            chapter_id=f"ch{ch_idx}",
            number=ch_idx,
            title=chapter_title,
            pages=PageSpan(start=0, end=0),
            sections=sections,
            learning_objectives=[],
        ))
    textbook = Textbook(
        textbook_id=textbook_id,
        title=title,
        authors=authors or [],
        edition=edition,
        source_format="markdown",
        parser_quality=1.0,
        chapters=chapters,
    )
    _assign_pages(textbook)
    return textbook
