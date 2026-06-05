"""Pydantic data models for textbook-grounded material generation.

Defines the textbook intermediate representation (Paragraph -> Section ->
Chapter -> Textbook) plus the retrieval and grounding artifacts
(EvidenceChunk, GeneratedClaim, GroundingReport) used by downstream
agents to ingest sources, retrieve evidence, and verify generated claims.
"""

import re
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel


# Title-pattern regex for non-instructional chapters that PDF / markdown
# ingesters often misclassify as real chapters. Matches case-insensitively
# at the START of a chapter title — so "Preface" matches but "Chapter 1:
# Introduction to Preprocessing" does NOT. Generic across textbooks; no
# per-source rules.
_POLLUTION_TITLE_RE = re.compile(
    r"^(?:Acknowledg|Foreword|Preface|Appendix|Glossary|Index"
    r"|Bibliography|References|Errata|Dedication|Copyright|Imprint"
    r"|Table\s+of\s+Contents|TOC|About\s+the\s+Authors?"
    r"|About\s+the\s+Editors?|Cover|Title\s+Page|Half\s+Title)",
    re.IGNORECASE,
)

# Chapters with very few paragraphs are usually boilerplate (front-matter
# blurbs, ad pages, brief notices). 5 paragraphs is a conservative floor:
# even a short real chapter typically has at least one section with several
# paragraphs of teaching content. Used in conjunction with the title regex.
_MIN_PARAGRAPHS_INSTRUCTIONAL = 5


def _is_instructional(c) -> bool:
    """True if a `Chapter` looks like a real teaching chapter.

    Three checks (in order — first failure wins):

    1. Has a meaningful title (not empty, not the "Untitled chapter"
       heading-detector fallback).
    2. Title does NOT match the pollution regex (front-matter,
       back-matter, etc.).
    3. Has at least ``_MIN_PARAGRAPHS_INSTRUCTIONAL`` paragraphs across
       all sections — boilerplate page-fillers are filtered here.

    The function is intentionally type-hint-loose (just `c`) so it can
    be defined before the `Chapter` class and still pick up duck-typed
    callers in tests.
    """
    title = (c.title or "").strip()
    if not title or title.lower() == "untitled chapter":
        return False
    if _POLLUTION_TITLE_RE.match(title):
        return False
    total_paragraphs = sum(len(s.paragraphs) for s in c.sections)
    if total_paragraphs < _MIN_PARAGRAPHS_INSTRUCTIONAL:
        return False
    return True


class Paragraph(BaseModel):
    para_id: str            # "ch3.s2.p07"
    text: str
    page: int
    kind: Literal["prose","definition","example","equation","exercise","figure_cap"]

class PageSpan(BaseModel):
    start: int                  # first page (inclusive)
    end: int                    # last page (inclusive)

class Section(BaseModel):
    section_id: str         # "ch3.s2"
    title: str
    pages: PageSpan
    paragraphs: List[Paragraph]
    concepts: List[str]

class Chapter(BaseModel):
    chapter_id: str
    number: int
    title: str
    pages: PageSpan
    sections: List[Section]
    learning_objectives: List[str]

class Textbook(BaseModel):
    textbook_id: str
    title: str; authors: List[str]; edition: Optional[str]
    source_format: Literal["pdf","markdown","html","epub"]
    parser_quality: float       # 0..1 — chapters <0.6 excluded from headline tables
    chapters: List[Chapter]

    def toc(self, word_budget: int = 400) -> str:
        """Format the textbook's table of contents for prompt injection.

        Returns a chapter-first listing with sections under each chapter,
        e.g. ::

            Chapter 2: Getting to Know Your Data
              - 2.1 Data Objects and Attribute Types
              - 2.2 Basic Statistical Descriptions
            Chapter 3: Data Preprocessing
              - ...

        **Pollution filter** (generic, no per-textbook rules) drops three
        categories of non-instructional chapters before formatting:

        * Heading-detector fallback titles ("Untitled chapter")
        * Front-matter / back-matter by title pattern (Acknowledgment,
          Foreword, Preface, Appendix, Glossary, Index, Bibliography,
          References, etc.) — see ``_POLLUTION_TITLE_RE``
        * Very short chapters (< ``_MIN_PARAGRAPHS_INSTRUCTIONAL``
          paragraphs across all sections) which are almost always
          boilerplate page-fillers

        If pollution-filtering leaves zero chapters, we fall back to the
        unfiltered list so the TOC is never empty (better to show some
        front matter than nothing).

        Token-budgeted: chapters are packed in order, dropping section
        detail (then truncating the chapter list itself) when the cumulative
        word count would exceed ``word_budget``. Even on huge textbooks the
        chapter-title backbone always fits — sections are a "nice to have"
        that degrade first.
        """
        if not self.chapters:
            return ""

        # Pollution filter. Drop chapters that are clearly non-instructional
        # (front-matter, back-matter, boilerplate). All-or-nothing fallback:
        # if filtering removes everything, keep the originals so the TOC
        # remains non-empty.
        real_chapters = [c for c in self.chapters if _is_instructional(c)]
        chapters = real_chapters if real_chapters else self.chapters

        # First pass: chapter titles only — this is the floor.
        title_lines = [f"Chapter {c.number}: {c.title}" for c in chapters]
        total = sum(len(l.split()) for l in title_lines)
        if total > word_budget:
            # Even the chapter list alone overflows; truncate it.
            kept: List[str] = []
            running = 0
            for line in title_lines:
                w = len(line.split())
                if running + w > word_budget - 6:  # room for the ellipsis line
                    break
                kept.append(line)
                running += w
            kept.append(f"... ({len(title_lines) - len(kept)} more chapters)")
            return "\n".join(kept)

        # Second pass: add sections under each chapter while budget allows.
        remaining = word_budget - total
        out: List[str] = []
        for c, title_line in zip(chapters, title_lines):
            out.append(title_line)
            for s in c.sections:
                line = f"  - {s.section_id} {s.title}"
                w = len(line.split())
                if w > remaining:
                    break
                out.append(line)
                remaining -= w
        return "\n".join(out)

class TopicMapping(BaseModel):
    topic: str
    section_ids: List[str]      # ordered, most-relevant first
    rationale: str

class CourseContract(BaseModel):
    course_id: str
    textbook_ids: List[str]
    audience: str
    in_scope_topics: List[str]
    out_of_scope_topics: List[str]
    learning_outcomes: List[str]
    prereq_edges: List[Tuple[str, str]]   # DAG over topics
    topic_to_textbook: List[TopicMapping]
    citation_required: bool = True

class EvidenceChunk(BaseModel):
    chunk_id: str
    text: str
    section_id: str
    page: int
    citation: str           # "[CSAPP:Ch3§2 p.45]"
    embedding: Optional[List[float]]
    bm25_terms: List[str]

class GeneratedClaim(BaseModel):
    text: str
    citation: Optional[str] = None   # any citation token attached; full shape expanded in PR #6 when verifier lands

class GroundingReport(BaseModel):
    chapter_id: str
    n_claims: int; n_supported: int
    citation_precision: float
    citation_recall: float
    faithfulness: float          # RAGAS-style
    context_precision: float
    context_recall: float
    unsupported_claims: List[GeneratedClaim]
    topic_drift_count: int
    overall_score: float         # 1..5
