"""Pydantic data models for textbook-grounded material generation.

Defines the textbook intermediate representation (Paragraph -> Section ->
Chapter -> Textbook) plus the retrieval and grounding artifacts
(EvidenceChunk, GeneratedClaim, GroundingReport) used by downstream
agents to ingest sources, retrieve evidence, and verify generated claims.
"""

from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel


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

        Token-budgeted: chapters are packed in order, dropping section
        detail (then truncating the chapter list itself) when the cumulative
        word count would exceed ``word_budget``. Even on huge textbooks the
        chapter-title backbone always fits — sections are a "nice to have"
        that degrade first.
        """
        if not self.chapters:
            return ""

        # Skip placeholder chapters from heading-detector fallback —
        # showing the model "Untitled chapter" five times is noise, not
        # signal. Filter only when there are real titles to fall back on.
        real_chapters = [c for c in self.chapters
                         if c.title and c.title.lower() != "untitled chapter"]
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
