"""Course contract — bind syllabus topics to textbook section IDs.

Once the syllabus has been split into chapters (each a topic), the
contract pre-computes which textbook sections cover each topic via a
hybrid-retrieval pass. Downstream prompt construction uses the mapping
to *bound* retrieval — instead of searching the whole textbook for every
slide, retrieval is restricted to the sections the contract says are
relevant. Better precision, fewer off-topic citations.

Two retrieval-quality boosts are applied when an LLM is available:

  * **HyDE (Hypothetical Document Embeddings).** The chapter title +
    description is a short query that embeds sparsely. We ask the LLM
    to write a 3–4 sentence hypothetical textbook paragraph for the
    topic, then retrieve against THAT — which lives in the same
    embedding neighborhood as real textbook prose, lifting recall.
  * **Multi-query via LLM subtopic decomposition.** The LLM extracts
    2–4 subtopics from the chapter; we retrieve per subtopic and fuse
    section rankings with RRF. Addresses the case where a chapter
    title doesn't anchor well anywhere in the textbook (e.g. a broad
    survey chapter that overlaps several specialist sections).

Both fall back gracefully — if no LLM is passed (e.g. tests), or an
LLM call errors out, contract-build degrades to the single-query path
unchanged.

Building the contract is cheap: a handful of `retriever.search()` calls
plus a few small LLM calls (~$0.001/chapter on gpt-4o-mini).
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from src.grounding.knowledge_base import TextbookKnowledgeBase
from src.grounding.retriever import HybridRetriever
from src.textbook.schema import CourseContract, TopicMapping

# How many candidate chunks to pull per individual query before fusion.
RETRIEVE_PER_TOPIC = 8

# How many sections per topic to lock into the contract. 3 strikes a
# balance: tight enough to keep retrieval focused, loose enough to allow
# topics that span multiple sections (common in survey chapters).
SECTIONS_PER_TOPIC = 3

# Subtopic decomposition: how many subtopics to extract per chapter.
# 3 is the sweet spot — enough breadth to surface distinct sections,
# few enough that each retrieval pass stays informative.
SUBTOPICS_PER_CHAPTER = 3

# RRF constant for fusing rankings across multiple queries. Same value
# as the retriever's internal RRF (Cormack et al. 2009).
QUERY_FUSION_RRF_K = 60

# Coverage floor for the top section's fused RRF score. Below this, we
# treat the chapter as "off-textbook" — no good match exists in the
# textbook for this topic, so we drop grounding for that chapter rather
# than have the LLM cite a weakly-related section. Empirically: a single
# query returning the section at rank 0 gives 1/60 ≈ 0.0167, so 0.012 is
# the "barely on-topic — no query found this section in its top ~15"
# threshold. Multi-query reliably pushes good matches well above 0.025.
COVERAGE_FLOOR_RRF = 0.012


def build_course_contract(
    course_id: str,
    chapters: Sequence[dict],
    kb: TextbookKnowledgeBase,
    retriever: HybridRetriever,
    *,
    sections_per_topic: int = SECTIONS_PER_TOPIC,
    audience: str = "",
    llm=None,
    use_hyde: bool = True,
    use_subtopics: bool = True,
    num_subtopics: int = SUBTOPICS_PER_CHAPTER,
) -> CourseContract:
    """Build a contract by retrieving textbook sections for each chapter.

    `chapters` is the output of `SyllabusProcessor.process_syllabus` —
    a list of ``{"title": ..., "description": ...}`` dicts.

    When ``llm`` is provided, HyDE + multi-query subtopic decomposition
    are applied to lift recall. When ``llm`` is None (tests, cache-only
    paths), the function degrades to single-query retrieval — identical
    to the prior behavior.
    """
    mappings: List[TopicMapping] = []
    for ch in chapters:
        title = (ch.get("title") or "").strip()
        desc = (ch.get("description") or "").strip()
        base_query = f"{title}. {desc}".strip()
        if not base_query:
            mappings.append(TopicMapping(
                topic=title, section_ids=[], rationale="empty chapter description",
            ))
            continue

        # Assemble the query set: the raw chapter as baseline, plus
        # LLM-extracted subtopics, each optionally HyDE-expanded.
        queries: List[str] = [base_query]
        rationale_parts: List[str] = []

        if llm is not None and use_subtopics:
            subtopics = _extract_subtopics(title, desc, llm, n=num_subtopics)
            if subtopics:
                queries.extend(subtopics)
                rationale_parts.append(f"{len(subtopics)} subtopics")

        if llm is not None and use_hyde:
            expanded: List[str] = []
            for q in queries:
                hyde = _hyde_expand(q, title, llm)
                # If HyDE fails, keep the original — never lose the baseline query.
                expanded.append(hyde if hyde else q)
            queries = expanded
            rationale_parts.append("HyDE-expanded")

        # Multi-query retrieval: each query retrieves independently;
        # section IDs are fused across queries via reciprocal-rank fusion.
        section_scores: dict[str, float] = {}
        first_chunks_by_section: dict[str, object] = {}
        for q in queries:
            try:
                results = retriever.search(q, top_k=RETRIEVE_PER_TOPIC)
            except Exception as e:
                # Per-query failure shouldn't sink the whole contract;
                # log and continue with whatever other queries succeed.
                print(f"[contract] retrieval failed for query (skipped): {e}")
                continue
            seen_in_query: set[str] = set()
            for rank, r in enumerate(results):
                sid = r.chunk.section_id
                if sid in seen_in_query:
                    # Each section contributes once per query — score by
                    # the BEST rank, not by how many chunks of it landed.
                    continue
                seen_in_query.add(sid)
                section_scores[sid] = (
                    section_scores.get(sid, 0.0) + 1.0 / (QUERY_FUSION_RRF_K + rank)
                )
                first_chunks_by_section.setdefault(sid, r.chunk)

        # Top sections by fused score, take up to sections_per_topic.
        ranked = sorted(section_scores.items(), key=lambda kv: -kv[1])
        top_score = ranked[0][1] if ranked else 0.0

        # Coverage gating: if the top section barely registered, this
        # chapter doesn't map to anything in the textbook. Better to
        # generate ungrounded content than to fabricate citations to a
        # weakly-related section. Downstream sees `section_ids=[]` and
        # falls back to the vanilla (no-citation) prompt for that chapter.
        if top_score < COVERAGE_FLOOR_RRF:
            section_ids: List[str] = []
            coverage_status = (
                f"off-textbook (top RRF={top_score:.4f} < floor "
                f"{COVERAGE_FLOOR_RRF:.4f})"
            )
        else:
            section_ids = [sid for sid, _ in ranked[:sections_per_topic]]
            coverage_status = f"top section RRF={top_score:.4f}"

        rationale_pieces = [f"{len(queries)} queries"] + rationale_parts + [
            coverage_status
        ]
        mappings.append(TopicMapping(
            topic=title,
            section_ids=section_ids,
            rationale=" · ".join(rationale_pieces),
        ))

    return CourseContract(
        course_id=course_id,
        textbook_ids=[kb.textbook_id],
        audience=audience,
        in_scope_topics=[m.topic for m in mappings],
        out_of_scope_topics=[],
        learning_outcomes=[],
        prereq_edges=[],
        topic_to_textbook=mappings,
        citation_required=True,
    )


def sections_for_chapter(
    contract: Optional[CourseContract], chapter_idx: int,
) -> Optional[List[str]]:
    """Look up the section IDs bound to a chapter by index.

    Returns ``None`` (no filter — search the whole textbook) when no
    contract is in play or the index is out of range. Returns ``[]``
    only if the contract explicitly assigned zero sections to this
    chapter (e.g. an empty description).
    """
    if contract is None:
        return None
    if 0 <= chapter_idx < len(contract.topic_to_textbook):
        return list(contract.topic_to_textbook[chapter_idx].section_ids)
    return None


# --------------------------------------------------------------------- #
# LLM-driven query enrichment (HyDE + subtopics)
# --------------------------------------------------------------------- #


_SUBTOPIC_PROMPT = (
    "You are helping retrieve relevant textbook passages for a course chapter.\n"
    "Given the chapter below, list {n} specific subtopics or named concepts "
    "that a student would learn in this chapter. Each subtopic should be a "
    "2–6 word phrase suitable for searching a textbook index — concrete and "
    "technical, not vague.\n\n"
    "CHAPTER TITLE: {title}\n"
    "CHAPTER DESCRIPTION: {desc}\n\n"
    "Return EXACTLY {n} subtopics, one per line, with NO numbering, NO "
    "bullet points, NO commentary, NO blank lines. Just the subtopic "
    "phrases themselves."
)


_HYDE_PROMPT = (
    "Write a single 3–4 sentence paragraph that would appear in a textbook "
    "covering the topic below. Use precise technical language and formal "
    "definitions as a textbook would. Do NOT add citations, introductions, "
    "summaries, or commentary — just the paragraph itself.\n\n"
    "CHAPTER CONTEXT: {title}\n"
    "TOPIC TO COVER: {topic}\n\n"
    "Paragraph (3–4 sentences, textbook prose, no preamble):"
)


def _extract_subtopics(title: str, desc: str, llm, *, n: int = SUBTOPICS_PER_CHAPTER) -> List[str]:
    """Ask the LLM for ``n`` concrete subtopics for this chapter.

    Returns ``[]`` on any failure — the caller treats that as "no extra
    queries" and falls back to the baseline query.
    """
    prompt = _SUBTOPIC_PROMPT.format(n=n, title=title, desc=desc or "(no description)")
    try:
        response, _, _ = llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"[contract] subtopic extraction failed: {e}")
        return []
    return _parse_subtopics(response, expected=n)


def _hyde_expand(query: str, title: str, llm) -> Optional[str]:
    """Ask the LLM for a hypothetical textbook paragraph for ``query``.

    Returns ``None`` on failure — the caller keeps the original query.
    """
    prompt = _HYDE_PROMPT.format(title=title, topic=query)
    try:
        response, _, _ = llm.generate_response(
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        print(f"[contract] HyDE expansion failed: {e}")
        return None
    return _clean_hyde_paragraph(response)


_BULLET_PREFIX = re.compile(r"^\s*[-*•]\s+|^\s*\d+[.)]\s+")


def _parse_subtopics(response: str, *, expected: int) -> List[str]:
    """Pull line-per-subtopic items out of the LLM response, robustly.

    The model occasionally adds numbering or bullet markers despite being
    told not to. Strip those and return at most ``expected`` non-empty
    lines.
    """
    if not response or not isinstance(response, str):
        return []
    if response.startswith("Error:"):  # fallback path from src.agents.LLM
        return []
    out: List[str] = []
    for line in response.splitlines():
        cleaned = _BULLET_PREFIX.sub("", line).strip()
        # Trim trailing punctuation we don't want in a search query.
        cleaned = cleaned.rstrip(" .;:")
        if not cleaned:
            continue
        # Discard implausibly long lines — those are usually the model
        # adding commentary instead of subtopic phrases.
        if len(cleaned.split()) > 12:
            continue
        out.append(cleaned)
        if len(out) >= expected:
            break
    return out


def _clean_hyde_paragraph(response: str) -> Optional[str]:
    """Drop any preamble the model added and return the paragraph itself."""
    if not response or not isinstance(response, str):
        return None
    if response.startswith("Error:"):
        return None
    text = response.strip()
    # Strip a leading "Paragraph:" or "Here is..." preamble if present.
    for prefix in (
        "Paragraph:", "Here is a paragraph:", "Here's a paragraph:",
        "Here is the paragraph:", "Here's the paragraph:",
    ):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].lstrip()
    if not text:
        return None
    return text
