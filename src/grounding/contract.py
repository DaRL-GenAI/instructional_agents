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

# How many sections per topic to lock into the contract.
#
# Initial work used 3 sections; a forensic replay against the
# data-mining baseline showed 12 of 15 course chapters had their
# top-section share above 50 % — the top-3 binding was
# over-concentrating writers onto a single section, driving the
# retrieval_bad failure slice. Widening to 6 gives the writer more
# in-scope options when the top-3 don't match a slide's exact topic.
# Generic across textbooks: a wider contract on a well-matched chapter
# just lets retrieval continue picking the same top sections.
SECTIONS_PER_TOPIC = 6

# Subtopic decomposition: how many subtopics to extract per chapter.
#
# HyDE++ paraphrase count. Pushing from 3 to 5 paraphrased queries per
# chapter brings more candidate sections into top-k, lifting recall on
# chapters where the chapter title alone doesn't anchor well to any
# single section. Each extra subtopic adds ~$0.04 / chapter
# (gpt-4o-mini), which lands at ~$0.20 across a 15-chapter course.
SUBTOPICS_PER_CHAPTER = 5

# RRF constant for fusing rankings across multiple queries. Same value
# as the retriever's internal RRF (Cormack et al. 2009).
QUERY_FUSION_RRF_K = 60

# Smart intro detection.
#
# Generic-survey chapter titles ("Introduction to X", "Overview of Y",
# "Basics of Z") don't anchor well to any single textbook section because
# the survey *spans* the textbook. A forensic replay showed those course
# chapters had the worst over-concentrated bindings (e.g. an intro
# chapter bound to a single clustering section at 46 % share; a
# "Classification Basics" chapter bound to one classification section at
# 60 %; a "Pattern Evaluation" chapter bound to one section at 94 %).
#
# Two complementary heuristics flag a chapter for an extended contract:
#   * KEYWORD MATCH on title or description against ``_GENERIC_KEYWORDS``
#   * DOMINANCE — top section's fused RRF is at least the multiplier
#     above the second section's. Catches the cases where the title isn't
#     literally "introduction" but the binding still collapsed to one
#     section (the chapter title's a poor topical anchor anyway).
#
# Affected chapters get ``SMART_INTRO_SECTIONS_PER_TOPIC`` sections instead
# of ``SECTIONS_PER_TOPIC``. Generic across textbooks: the keyword list
# is curriculum-vocabulary, not source-specific.
_GENERIC_KEYWORDS = (
    "introduction", "intro to", "overview", "basics", "basic ",
    "fundamentals", "fundamental ", "survey", "review",
    "project work", "presentations", "summary", "final",
    # Meta-evaluation and meta-comparison chapters — "about the methods"
    # rather than mapping to any single textbook section, so they widen
    # and may abstain entirely below.
    "evaluation", "evaluating", "validation", "validating",
    "assessment of", "advanced", "comparison", "comparing",
    "methods of", "techniques of", "applications of",
    "cluster analysis", "pattern evaluation",
)
SMART_INTRO_DOMINANCE_RATIO = 2.0  # Lowered from 2.5 to catch chapters
                                    # like "Clustering Methods" with a
                                    # narrowly-dominant top section.
SMART_INTRO_SECTIONS_PER_TOPIC = 10

# Meta-chapter abstain — when a chapter's best section after widening
# still has a low fused RRF score, the topic genuinely has no good
# anchor in the source (e.g. "Pattern Evaluation", "Project Work").
# Rather than widen to even more weakly-related sections, set
# section_ids=[] so the writer falls back to vanilla (no fabricated
# citations). The threshold is calibrated to a measured baseline:
# chapters with top RRF < 0.025 after widening had average precision
# <40% in the prior generation.
META_ABSTAIN_RRF_FLOOR = 0.025

# Relative-score floor on the bound sections — drops only NOISE sections
# (a near-zero fused RRF relative to the top), not a primary off-topic
# filter. A score floor can't cleanly separate on-topic from off-topic:
# a genuinely on-topic sub-section (e.g. "Density-Based Methods") often
# scores BELOW an off-topic straggler HyDE pulled in (e.g. a Chapter 3
# PCA section), so an aggressive floor starves the legitimate sections of
# their figures. Off-topic *slides* are prevented by the softened
# TOPIC-COVERAGE outline instruction ("skip a topic clearly from a
# different subject"), and off-topic *figures* by the embedding-based
# figure↔slide matching. This floor just removes sections that barely
# registered at all.
SECTION_RELATIVE_SCORE_FLOOR = 0.10


def _apply_relative_score_floor(ranked, top_n, floor_fraction):
    """Of the top-``top_n`` ranked ``(section_id, score)`` pairs, keep only
    those whose score is at least ``floor_fraction`` of the top score —
    dropping weakly-related stragglers while preserving a genuinely spread
    binding. Always keeps at least the top section. ``ranked`` must be
    sorted by descending score."""
    if not ranked:
        return []
    top_score = ranked[0][1]
    floor = floor_fraction * top_score
    kept = [sid for sid, sc in ranked[:top_n] if sc >= floor]
    return kept or [ranked[0][0]]


def _is_generic_intro_chapter(title: str, desc: str) -> bool:
    """Keyword-based intro / meta-chapter detection.

    Catches the bulk of catastrophic intro chapters by curriculum
    vocabulary. The dominance heuristic catches the rest (chapter titles
    that aren't literally "Introduction" but still bind to a single
    section).
    """
    text = f"{title} {desc}".lower()
    return any(kw in text for kw in _GENERIC_KEYWORDS)


def _is_dominant_binding(ranked: list[tuple[str, float]]) -> bool:
    """Top section dominates if the next section is >= ratio* below it
    on the fused RRF score. Reflects an over-concentrated contract — the
    writer will keep citing the dominant section and drown out the
    smaller signal.
    """
    if len(ranked) < 2:
        return False
    top = ranked[0][1]
    second = ranked[1][1]
    if second <= 0:
        return True
    return top / second >= SMART_INTRO_DOMINANCE_RATIO

# Coverage floor for the top section's fused RRF score. Below this, we
# treat the chapter as "off-textbook" — no good match exists in the
# textbook for this topic, so we drop grounding for that chapter rather
# than have the LLM cite a weakly-related section. Empirically: a single
# query returning the section at rank 0 gives 1/60 ≈ 0.0167, so 0.012 is
# the "barely on-topic — no query found this section in its top ~15"
# threshold. Multi-query reliably pushes good matches well above 0.025.
COVERAGE_FLOOR_RRF = 0.012

# Scale-invariant normalization. The raw fused score sums 1/(K+rank) over a
# VARIABLE number of queries (1 base + up to SUBTOPICS_PER_CHAPTER), so the
# absolute floors above drift when the query count or section granularity
# changes — a transfer hazard across textbooks. Dividing by the max attainable
# score (n_queries / K) maps it to [0, 1] (1.0 == ranked #1 by every query),
# making the abstain floors query-count-invariant. The normalized floors are
# the equivalents of the raw floors at the reference query count (1 base + 5
# subtopics = 6), so the default-config behavior is preserved.
NORM_COVERAGE_FLOOR = 0.12       # ~ COVERAGE_FLOOR_RRF (0.012) at 6 queries
NORM_META_ABSTAIN_FLOOR = 0.25   # ~ META_ABSTAIN_RRF_FLOOR (0.025) at 6 queries

# Book-RELATIVE abstain floors. The fixed floors above were tuned on the eval
# textbooks; a denser/sparser book could mass-abstain or mass-bind. Instead the
# floors adapt to the book's OWN median top_norm: a chapter abstains when its
# top section scores weakly RELATIVE to the typical chapter. A small absolute
# backstop keeps a uniformly-weak book from binding pure noise. On the eval
# books (median top_norm ~0.5) these resolve to ≈ the legacy fixed floors, so
# behavior is preserved there.
REL_COVERAGE_FRACTION = 0.25
REL_META_FRACTION = 0.50
NORM_COVERAGE_FLOOR_MIN = 0.05
NORM_META_ABSTAIN_MIN = 0.10


def _median(values):
    """Median of a list of floats; 0.0 for an empty list."""
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return 0.0
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0

# Coverage cap for chapters that span many sections (raised from 10). A
# clustering chapter covers K-Means, K-Medoids, hierarchical, density, grid, and
# evaluation — ~15 textbook sections — and was previously truncated to a third
# of itself. The relative-score floor still gates which sections actually bind.
MAX_SECTIONS_PER_TOPIC = 16


def _normalized_top(top_score: float, n_queries: int) -> float:
    """Map a raw fused RRF top-score to [0, 1] (1.0 == ranked #1 by every
    query) so the abstain floors are invariant to the query count."""
    return top_score * QUERY_FUSION_RRF_K / max(1, n_queries)


def _count_sections_above_floor(ranked, floor_fraction: float) -> int:
    """Number of sections within ``floor_fraction`` of the top score — the size
    of the on-topic 'plateau' that coverage widening should try to bind."""
    if not ranked:
        return 0
    floor = floor_fraction * ranked[0][1]
    return sum(1 for _sid, sc in ranked if sc >= floor)


_FILLER_TITLE_WORDS = (
    "summary", "bibliographic notes", "bibliography", "exercises", "problems",
    "index", "references", "glossary", "acknowledgment", "acknowledgement",
    "preface", "contents", "about the author", "further reading",
)


def _is_filler_section(title: str) -> bool:
    """True for non-teaching boilerplate sections (Summary, Exercises,
    Bibliographic Notes, Index, References, ...) that shouldn't consume a
    binding slot. Textbook-agnostic — universal academic section conventions,
    matched after stripping leading section numbers and markdown emphasis."""
    t = re.sub(r"[*_`\[\]]+", "", title or "").strip().lower()
    t = re.sub(r"^\d+(?:\.\d+)*\s*", "", t).strip()
    return any(t == w or t.startswith(w) for w in _FILLER_TITLE_WORDS)


_SECTION_NUM_RE = re.compile(r"\s*\**\[?\s*(\d+)\.\d+")


def _section_chapter_num(title: str):
    """Leading chapter number from an 'N.M ...' section title, else None."""
    m = _SECTION_NUM_RE.match(title or "")
    return int(m.group(1)) if m else None


def _chapter_coherence_filter(ranked, title_by_sid, span: int = 1):
    """Drop bound sections from textbook chapters far from the dominant chapter
    of the top-scored sections. Controls HyDE drift (a clustering chapter
    pulling in a data-preprocessing section) using the section NUMBERING, which
    stays reliable even when the IR's chapter-boundary detection is broken.
    No-op when sections aren't numbered (un-numbered sources degrade safely)."""
    numbered = [
        (sid, sc, _section_chapter_num(title_by_sid.get(sid, "")))
        for sid, sc in ranked
    ]
    if sum(1 for _s, _c, n in numbered if n is not None) < 3:
        return ranked  # not enough numbering signal to judge coherence
    mass: dict = {}
    for _sid, sc, n in numbered[:8]:  # the top sections define the topic's chapter
        if n is not None:
            mass[n] = mass.get(n, 0.0) + sc
    if not mass:
        return ranked
    dominant = max(mass, key=mass.get)
    kept = [
        (sid, sc) for sid, sc, n in numbered
        if n is None or abs(n - dominant) <= span
    ]
    return kept or ranked


def _score_chapter(ch, retriever, llm, title_by_sid, *,
                   use_hyde, use_subtopics, num_subtopics):
    """Score one chapter for binding: build queries (subtopics + HyDE),
    multi-query retrieve, fuse to ranked sections, compute the normalized top
    score. Returns a record dict, or None when the chapter has no description.
    Pure scoring — the abstain GATE is applied by the caller so its floors can
    be set relative to the whole book's score distribution."""
    title = (ch.get("title") or "").strip()
    desc = (ch.get("description") or "").strip()
    base_query = f"{title}. {desc}".strip()
    if not base_query:
        return None
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
    # Multi-query retrieval: each query retrieves independently; section IDs are
    # fused across queries via reciprocal-rank fusion (best rank per query).
    section_scores: dict[str, float] = {}
    for q in queries:
        try:
            results = retriever.search(q, top_k=RETRIEVE_PER_TOPIC)
        except Exception as e:
            print(f"[contract] retrieval failed for query (skipped): {e}")
            continue
        seen_in_query: set[str] = set()
        for rank, r in enumerate(results):
            sid = r.chunk.section_id
            if sid in seen_in_query:
                continue
            seen_in_query.add(sid)
            section_scores[sid] = (
                section_scores.get(sid, 0.0) + 1.0 / (QUERY_FUSION_RRF_K + rank)
            )
    # Drop boilerplate sections; control HyDE drift to within ±1 chapter.
    ranked = sorted(section_scores.items(), key=lambda kv: -kv[1])
    ranked = [
        (sid, sc) for sid, sc in ranked
        if not _is_filler_section(title_by_sid.get(sid, ""))
    ]
    ranked = _chapter_coherence_filter(ranked, title_by_sid)
    top_score = ranked[0][1] if ranked else 0.0
    return {
        "title": title, "desc": desc, "queries": queries, "ranked": ranked,
        "top_norm": _normalized_top(top_score, len(queries)),
        "rationale_parts": rationale_parts,
    }


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
    # section_id -> title, to drop non-teaching boilerplate sections from binding.
    title_by_sid = {
        s.section_id: s.title
        for ch in kb.textbook.chapters for s in ch.sections
    }
    # Pass 1 — score every chapter (query expansion + retrieval + ranking),
    # collected FIRST so the abstain floors can be set RELATIVE to the book's
    # own score distribution (transfer-robust) instead of fixed scalars.
    records = [
        _score_chapter(
            ch, retriever, llm, title_by_sid,
            use_hyde=use_hyde, use_subtopics=use_subtopics,
            num_subtopics=num_subtopics,
        )
        for ch in chapters
    ]
    # Book-relative floors: a chapter abstains when its top section scores
    # weakly RELATIVE to the typical chapter. Small absolute backstop so a
    # uniformly-weak book can't bind noise. On the eval books (median top_norm
    # ~0.5) these ≈ the legacy fixed floors, preserving behavior there.
    _norms = [r["top_norm"] for r in records if r and r["top_norm"] > 0]
    _ref = _median(_norms)
    if _ref > 0:
        coverage_floor = max(NORM_COVERAGE_FLOOR_MIN, REL_COVERAGE_FRACTION * _ref)
        meta_floor = max(NORM_META_ABSTAIN_MIN, REL_META_FRACTION * _ref)
    else:
        coverage_floor, meta_floor = NORM_COVERAGE_FLOOR, NORM_META_ABSTAIN_FLOOR

    # Pass 2 — gate each chapter against the (book-relative) floors.
    for rec, ch in zip(records, chapters):
        if rec is None:
            mappings.append(TopicMapping(
                topic=(ch.get("title") or "").strip(), section_ids=[],
                rationale="empty chapter description",
            ))
            continue
        title = rec["title"]
        desc = rec["desc"]
        queries = rec["queries"]
        ranked = rec["ranked"]
        top_norm = rec["top_norm"]
        rationale_parts = list(rec["rationale_parts"])
        n_queries = len(queries)

        # Coverage gating: if the top section barely registered, this
        # chapter doesn't map to anything in the textbook. Better to
        # generate ungrounded content than to fabricate citations to a
        # weakly-related section. Downstream sees `section_ids=[]` and
        # falls back to the vanilla (no-citation) prompt for that chapter.
        if top_norm < coverage_floor:
            section_ids: List[str] = []
            coverage_status = (
                f"off-textbook (top normalized RRF={top_norm:.3f} < floor "
                f"{coverage_floor:.3f})"
            )
        else:
            # Smart intro widening. If the chapter looks like a
            # generic-survey or its binding is dominated by a single
            # section, widen to SMART_INTRO_SECTIONS_PER_TOPIC so the
            # writer has cross-section options. Otherwise keep the
            # default sections_per_topic.
            effective_top_n = sections_per_topic
            smart_widen_trigger = None
            n_above_floor = _count_sections_above_floor(
                ranked, SECTION_RELATIVE_SCORE_FLOOR
            )
            if _is_generic_intro_chapter(title, desc):
                smart_widen_trigger = "generic-keyword"
            elif _is_dominant_binding(ranked):
                smart_widen_trigger = "dominant-binding"
            elif n_above_floor > sections_per_topic:
                # Chapter genuinely spans many sections (broad/survey) — widen to
                # cover the on-topic plateau instead of truncating to a third.
                smart_widen_trigger = "broad-binding"
            if smart_widen_trigger:
                effective_top_n = max(
                    effective_top_n, min(MAX_SECTIONS_PER_TOPIC, n_above_floor)
                )

            # Meta-chapter abstain — if the chapter was widened but the
            # top section's score is STILL below the abstain floor, the
            # topic has no real anchor in the source (e.g. "Pattern
            # Evaluation", "Project Work"). Force section_ids=[] so the
            # writer falls back to vanilla rather than fabricate
            # citations against weakly-related sections.
            if smart_widen_trigger and top_norm < meta_floor:
                section_ids = []
                rationale_parts.append(
                    f"META-ABSTAIN (widened but top normalized RRF={top_norm:.3f} "
                    f"< meta_floor={meta_floor:.3f})"
                )
                mappings.append(TopicMapping(
                    topic=title,
                    section_ids=section_ids,
                    rationale=" · ".join(
                        [f"{len(queries)} queries"] + rationale_parts +
                        ["meta-chapter abstain"]
                    ),
                ))
                continue

            # Relative-score floor: keep only sections scoring near the top
            # so a weakly-related straggler HyDE pulled in (a different
            # chapter's topic) doesn't end up bound and forcing an
            # off-topic slide. Always keep at least the top section.
            section_ids = _apply_relative_score_floor(
                ranked, effective_top_n, SECTION_RELATIVE_SCORE_FLOOR
            )
            dropped = min(effective_top_n, len(ranked)) - len(section_ids)
            if smart_widen_trigger:
                coverage_status = (
                    f"top normalized RRF={top_norm:.3f} · "
                    f"widened to {len(section_ids)} sections "
                    f"({smart_widen_trigger}; "
                    f"{dropped} below {SECTION_RELATIVE_SCORE_FLOOR:.0%} "
                    f"relative floor dropped)"
                )
            else:
                coverage_status = f"top normalized RRF={top_norm:.3f}"

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
