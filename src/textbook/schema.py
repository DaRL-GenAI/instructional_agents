"""Pydantic data models for textbook-grounded material generation.

Canonical definitions live in §2 of SUMMER_PLAN.md (the design doc). This
module scaffolds them verbatim; refinements go through PR review.
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
