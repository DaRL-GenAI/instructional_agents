import os
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from src.agents import (
    LLM,
    Agent,
)
from src.beamer_preflight import normalize_beamer_source, repair_messages


class SlideUtils:
    """Utility class: provides reusable utility functions for slides"""
    
    @staticmethod
    def get_latex_template(catalog: bool = False, template_path: Optional[str] = None) -> str:
        """Get LaTeX template"""
        default_template = r"""
\documentclass{beamer}

% Theme choice
\usetheme{Madrid} % You can change to e.g., Warsaw, Berlin, CambridgeUS, etc.

% Encoding and font
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}

% Graphics and tables
\usepackage{graphicx}
\usepackage{booktabs}

% Code listings
\usepackage{listings}
\lstset{
basicstyle=\ttfamily\small,
keywordstyle=\color{blue},
commentstyle=\color{gray},
stringstyle=\color{red},
breaklines=true,
frame=single
}

% Math packages
\usepackage{amsmath}
\usepackage{amssymb}

% Colors
\usepackage{xcolor}

% TikZ and PGFPlots
\usepackage{tikz}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usetikzlibrary{positioning}

% Hyperlinks
\usepackage{hyperref}

% Title information
\title{Sample Beamer Presentation}
\author{Your Name}
\institute{Your Institution}
\date{\today}

\begin{document}

% Title frame
\begin{frame}[fragile]
    \titlepage
\end{frame}

\end{document}
"""
        
        if catalog and template_path:
            if os.path.exists(template_path):
                with open(template_path, "r", encoding="utf-8") as f:
                    return f.read()
        elif catalog:
            template_dir = "catalog/references"
            latex_template_path = os.path.join(template_dir, "latex_template.tex")
            if os.path.exists(latex_template_path):
                with open(latex_template_path, "r", encoding="utf-8") as f:
                    return f.read()
        
        return default_template
    
    @staticmethod
    def parse_latex_template(latex_template: str) -> Tuple[str, str]:
        """Parse LaTeX template, separating prefix and suffix"""
        begin_doc = latex_template.find("\\begin{document}")
        end_doc = latex_template.find("\\end{document}")
        
        if begin_doc != -1 and end_doc != -1:
            prefix = latex_template[:begin_doc + len("\\begin{document}")]
            suffix = latex_template[end_doc:]
            return prefix, suffix
        elif begin_doc != -1:
            prefix = latex_template[:begin_doc + len("\\begin{document}")]
            suffix = "\n\n\\end{document}"
            return prefix, suffix
        else:
            # Standard structure not found, assume entire template is prefix
            prefix = latex_template + "\n\n\\begin{document}\n"
            suffix = "\n\\end{document}"
            return prefix, suffix
    
    @staticmethod
    def extract_latex_frames(latex_source: str) -> List[str]:
        """Extract all frames from LaTeX source code"""
        frame_pattern = re.compile(r'\\begin{frame}.*?\\end{frame}', re.DOTALL)
        frames = frame_pattern.findall(latex_source)
        return frames
    
    @staticmethod
    def compile_latex_document(
        prefix: str,
        frames: List[str],
        suffix: str
    ) -> str:
        """Compile a complete LaTeX document"""
        latex_source = prefix + "\n\n" + "\n\n".join(frames) + "\n\n" + suffix
        
        # Validate document structure
        match = re.search(r"\\documentclass.*?\\begin\{document\}.*?\\end\{document\}", latex_source, re.DOTALL)
        if match:
            return match.group()
        else:
            return latex_source  # Return even if no match, let the caller decide
    
    @staticmethod
    def generate_latex_frame_prompt(
        title: str,
        content: str,
        description: Optional[str] = None,
        current_frames: Optional[str] = None,
        user_feedback: Optional[Dict] = None,
        max_frames: int = 3
    ) -> str:
        """Generate prompt for LaTeX frame creation"""
        feedback_text = ""
        if user_feedback:
            feedback_text = f"""
User Feedback:
[For slides]{json.dumps(user_feedback.get('slides', {}), indent=2)}
[For overall]{json.dumps(user_feedback.get('overall', {}), indent=2)}
"""
        
        current_frames_text = ""
        if current_frames:
            current_frames_text = f"""
Current LaTeX Frames (for reference):
```latex
{current_frames}
```
"""
        
        description_text = f"\nSlide Description: {description}" if description else ""
        
        return f"""
Based on the following slide content, generate LaTeX code for a presentation slide.
You can create multiple frames if the content is too extensive for a single frame.

Slide Title: {title}{description_text}

Detailed Content:
{content[:2000]}

{current_frames_text}{feedback_text}

Please generate the LaTeX code for this slide using the beamer class format.
You should first summarize the content and extract key points to A BRIEF SUMMARY.

IMPORTANT: You can create multiple frames for this slide if needed (maximum {max_frames} frames). Consider creating separate frames for:
- Different concepts or topics
- Lengthy explanations that won't fit on one slide
- Examples that need their own space
- Code snippets or formulas that need more room

Each frame should be structured as follows:
\\begin{{frame}}[fragile]
    \\frametitle{{Slide Title - Part X}}
    % Content goes here
\\end{{frame}}

Guidelines:
1. Don't use non-English characters directly, e.g. use $\\gamma$ instead of γ, $\\epsilon$ instead of ε
2. If any symbol has a special meaning, add a backslash. e.g. use \\& instead of &
3. Use bullet points or numbered lists for clarity
4. Keep each frame focused and not overcrowded
5. If you create multiple frames [***NO MORE THAN {max_frames} FRAMES***], ensure logical flow between them
6. Never nest itemize/enumerate environments more than 3 levels deep; prefer 2 levels for readability
7. Colors: the preamble is fixed, so you cannot add \\definecolor. Only use standard color names (red, blue, teal, gray, ...), color names already defined in the template or current frames, or inline hex via \\textcolor[HTML]{{RRGGBB}}{{...}}. Never invent named colors such as electricblue
8. Never nest display-math environments. For multiple aligned lines, use \\begin{{align*}} by itself, or put \\begin{{aligned}} inside \\begin{{equation}}. Never put align, align*, gather, or multline inside equation
9. Code-heavy frames may use at most one lstlisting environment each. Consolidate a multi-step workflow into one complete, concise snippet (ideally 12 lines or fewer) instead of a separate code block under every step

Use LaTeX features like:
- \\begin{{itemize}} for bullet points
- \\begin{{enumerate}} for numbered lists
- \\begin{{block}}{{Title}} for highlighted blocks
- \\begin{{lstlisting}} for code snippets
- \\begin{{equation}} for mathematical formulas

Your response should contain all the frames for this slide, each from \\begin{{frame}}[fragile] to \\end{{frame}}.
Separate multiple frames with blank lines.
"""
    
    @staticmethod
    def generate_latex_frames_from_content(
        agent: Agent,
        title: str,
        content: str,
        description: Optional[str] = None,
        current_frames: Optional[str] = None,
        user_feedback: Optional[Dict] = None,
        max_frames: int = 3
    ) -> List[str]:
        """Generate LaTeX frames from content using an Agent"""
        prompt = SlideUtils.generate_latex_frame_prompt(
            title=title,
            content=content,
            description=description,
            current_frames=current_frames,
            user_feedback=user_feedback,
            max_frames=max_frames
        )
        
        agent.reset_history()
        response, _, _ = agent.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        
        frames = SlideUtils.extract_latex_frames(response)
        return frames


# --------------------------------------------------------------------- #
# Textbook-grounding helpers (module level)                              #
# --------------------------------------------------------------------- #
# Only used when a SlidesDeliberation is constructed with a retriever
# (``--use-textbook``). The vanilla pipeline never calls them.

# Two retrieval hits whose first N words match are treated as the same
# passage (the chunker overlaps adjacent prose chunks by OVERLAP_TOKENS).
_DEDUPE_PREFIX_WORDS = 40

# Inline markers carried by figure / equation chunks from the paged PDF
# ingester. Kept as a module-level constant so the dedupe helper can
# recognise visual chunks without importing the class.
_VISUAL_CHUNK_MARKERS = ("[IMAGE_PATH:", "[LATEX:", "[TABLE:", "[ALGORITHM_STEPS:")


def _is_visual_chunk_text(text: str) -> bool:
    return any(m in text for m in _VISUAL_CHUNK_MARKERS)


def _dedupe_results(results):
    """Drop later results whose chunk overlaps a kept earlier chunk.

    Two retrieval results are considered duplicates if EITHER:
      * their full text matches byte-for-byte, OR
      * their first :data:`_DEDUPE_PREFIX_WORDS` words match the first
        ``_DEDUPE_PREFIX_WORDS`` words of an already-kept chunk (catches
        the common case where chunk N+1 starts with the last ~64 tokens of
        chunk N due to OVERLAP_TOKENS).

    Visual chunks (figure / equation markers) are exempt from the prefix
    rule against prose chunks -- their content role is distinct and they
    are tiny -- but still dedupe on byte-identical text.

    Preserves the retriever's rank order -- first occurrence of each
    cluster is kept, later occurrences are dropped. Never raises.
    """
    if not results:
        return results
    kept = []
    seen_full: set = set()
    seen_prefix: set = set()
    for r in results:
        text = r.chunk.text or ""
        is_visual = _is_visual_chunk_text(text)
        prefix = " ".join(text.split()[:_DEDUPE_PREFIX_WORDS])
        if is_visual:
            if text in seen_full:
                continue
        else:
            if text in seen_full or (prefix and prefix in seen_prefix):
                continue
        kept.append(r)
        seen_full.add(text)
        if prefix and not is_visual:
            seen_prefix.add(prefix)
    return kept


class SlidesDeliberation:
    """
    SlidesDeliberation class for organizing agents to collaboratively create slides
    """
    def __init__(self,
                 id: str,
                 name: str,
                 agents: Dict[str, Agent],
                 llm: LLM,
                 max_rounds: int = 1,
                 output_dir: str = "./outputs/",
                 catalog: bool = False,
                 catalog_dict: Dict[str, Any] = None,
                 resume: bool = False,
                 retriever=None,
                 section_ids=None,
                 textbook_id: str = None,
                 ):
        """
        Initialize SlidesDeliberation

        Args:
            id: Unique identifier for this deliberation
            name: Human-readable name for this deliberation
            agents: Dictionary of agents with roles as keys
            llm: LLM instance to use
            max_rounds: Maximum discussion rounds
            latex_template: LaTeX template to use for slides
            output_dir: Directory to save output files
            resume: If True and a checkpoint exists in output_dir, pick up
                from the last completed step / slide instead of starting
                from scratch.
            retriever: Optional textbook retriever (``--use-textbook``).
                ``None`` (the default) leaves every prompt byte-identical
                to the vanilla pipeline.
            section_ids: Textbook section IDs the course contract bound to
                this chapter; scopes evidence retrieval. ``None`` = whole
                textbook.
            textbook_id: Identifier of the loaded textbook (for logging).
        """
        self.id = id
        self.name = name
        self.agents = agents
        self.llm = llm
        self.max_rounds = max_rounds
        self.output_dir = output_dir
        self.catalog = catalog
        self.catalog_dict = catalog_dict if catalog_dict else {}
        self.resume = resume

        # Optional textbook-grounding handles. When `retriever` is None,
        # `_build_evidence_block` returns empty strings and every prompt is
        # constructed exactly as in the vanilla pipeline.
        self.retriever = retriever
        self.section_ids = section_ids
        self.textbook_id = textbook_id
        # Per-chapter top_k tuned by the density of chunks in the chapter's
        # bound sections (see _compute_top_k_for_chapter).
        self._evidence_top_k = self._compute_top_k_for_chapter()

        # Initialize containers for results
        self.slides_outline = []
        self.latex_dict = {}  # Now stores list of frames per slide
        self.slides_script = {}
        self.assessment_template = {}  # New: assessment template
        self.assessment_content = {}   # New: assessment content

    # ------------------------------------------------------------------ #
    # Textbook-grounding helpers                                          #
    # ------------------------------------------------------------------ #
    # Word budget for the injected evidence block. Stays well under the
    # model's context window after the rest of the prompt.
    _EVIDENCE_WORD_BUDGET = 1800
    _EVIDENCE_TOP_K = 6            # default; per-chapter tuning may override
    _EVIDENCE_TOP_K_MIN = 5        # floor for thin chapters
    _EVIDENCE_TOP_K_MAX = 12       # ceiling -- beyond this hits the word budget
    _CHUNKS_PER_TOP_K_STEP = 12    # ~12 chunks of density per top_k step

    # Artifact-type vocabulary for `_build_evidence_block`. The strict
    # rule-set ("slide") applies to slides + assessments -- both are READ
    # documents. The relaxed rule-set ("script") applies to speaker
    # scripts -- SPOKEN narration where mandatory direct quotation breaks
    # narrative flow, so RULE 2 softens to "paraphrase naturally."
    _ARTIFACT_TYPES = ("slide", "script", "assessment")

    # Abort the run after this many consecutive retrieval failures of the
    # same error class: writer calls would keep spending money while no
    # grounded evidence reaches the prompt.
    _MAX_CONSECUTIVE_RETRIEVAL_FAILURES = 10

    # Horizontal rules used to frame the evidence block.
    _EVIDENCE_RULE = "═" * 68
    _EXCERPTS_RULE = "═" * 27 + " EXCERPTS " + "═" * 27

    def _compute_top_k_for_chapter(self) -> int:
        """Tune the retriever top_k by the density of bound chunks.

        Returns ``_EVIDENCE_TOP_K`` (the default) when the retriever is
        absent, no sections are bound, or the KB chunks attribute is
        unavailable. Otherwise counts how many chunks belong to sections in
        ``self.section_ids`` and scales: roughly
        ``round(chunks / _CHUNKS_PER_TOP_K_STEP)``, clamped to
        ``[_EVIDENCE_TOP_K_MIN, _EVIDENCE_TOP_K_MAX]``.
        """
        if self.retriever is None or not self.section_ids:
            return self._EVIDENCE_TOP_K
        try:
            kb_chunks = self.retriever.kb.chunks
        except AttributeError:
            return self._EVIDENCE_TOP_K
        bound = sum(1 for c in kb_chunks if c.section_id in self.section_ids)
        if bound == 0:
            return self._EVIDENCE_TOP_K
        scaled = round(bound / self._CHUNKS_PER_TOP_K_STEP)
        return max(self._EVIDENCE_TOP_K_MIN,
                   min(self._EVIDENCE_TOP_K_MAX, scaled))

    def _build_evidence_block(
        self,
        query: str,
        artifact: str = "slide",
        section_ids_override=None,
        cross_chapter: bool = False,
    ) -> tuple:
        """Retrieve textbook evidence for `query` and format it for a prompt.

        Returns ``(evidence_block, "")`` -- the second element is always an
        empty string (kept so callers need no signature change).
        ``evidence_block`` is empty when ``self.retriever is None`` (vanilla
        path) or retrieval yielded nothing in scope; otherwise it is plain
        text the caller prepends to its prompt.

        ``artifact`` is one of ``"slide" | "script" | "assessment"``; it
        toggles RULE 2 between the read-document and spoken-script
        phrasings. RULES 3 / 6 / 7 are universal.

        Section filtering, in priority order: ``cross_chapter=True`` searches
        the whole textbook; ``section_ids_override`` (a per-slide narrowed
        pick) replaces the chapter binding; otherwise ``self.section_ids``.
        """
        if self.retriever is None:
            return "", ""
        if artifact not in self._ARTIFACT_TYPES:
            # Defensive: an unknown artifact label falls back to the strict
            # rule-set rather than crashing.
            artifact = "slide"
        try:
            if cross_chapter:
                effective_section_ids = None
            elif section_ids_override is not None:
                effective_section_ids = section_ids_override
            else:
                effective_section_ids = self.section_ids
            results = self.retriever.search(
                query,
                top_k=getattr(self, "_evidence_top_k", self._EVIDENCE_TOP_K),
                section_ids=effective_section_ids,
            )
        except Exception as e:
            # Cost protection: if retrieval keeps failing the same way, the
            # run is no longer producing grounded output but still paying
            # for writer calls. Abort cleanly after a generous threshold.
            cls = type(self)
            err_type = type(e).__name__
            if getattr(cls, "_last_retrieval_error_type", None) == err_type:
                cls._consecutive_retrieval_failures = (
                    getattr(cls, "_consecutive_retrieval_failures", 0) + 1
                )
            else:
                cls._consecutive_retrieval_failures = 1
                cls._last_retrieval_error_type = err_type
            n = cls._consecutive_retrieval_failures
            print(f"[grounding] retrieval failed ({e}); falling back to vanilla prompt "
                  f"(consecutive {err_type} failures: {n})")
            if n >= self._MAX_CONSECUTIVE_RETRIEVAL_FAILURES:
                raise RuntimeError(
                    f"Grounding retrieval failed {n} times in a row with the "
                    f"same error class ({err_type}). Aborting run to prevent "
                    f"further cost (writer calls keep running even though no "
                    f"grounded evidence is reaching the prompt). "
                    f"Last error: {e!r}"
                )
            return "", ""
        # Successful retrieval -- reset the consecutive-failure counter.
        cls = type(self)
        cls._consecutive_retrieval_failures = 0
        cls._last_retrieval_error_type = None
        if not results:
            return "", ""

        # Drop near-identical neighbours (chunk overlap) before showing to
        # the LLM.
        results = _dedupe_results(results)

        # Coverage diversification for chapter-level retrieval: make sure
        # the top-k spans at least 3 distinct sections when possible, so
        # the writer is not locked onto one narrow textbook slice for the
        # whole chapter. Only for chapter-level calls.
        if (section_ids_override is None and not cross_chapter
                and len(results) >= 4):
            distinct_sections = {r.chunk.section_id for r in results}
            if len(distinct_sections) < 3:
                seen_sections = set()
                diverse, deferred = [], []
                for r in results:
                    sid = r.chunk.section_id
                    if sid not in seen_sections:
                        diverse.append(r)
                        seen_sections.add(sid)
                    else:
                        deferred.append(r)
                results = diverse + deferred

        # Build per-excerpt blocks with structured headers under a shared
        # word budget; truncate the last one if it would overflow.
        budget = self._EVIDENCE_WORD_BUDGET
        blocks = []
        for idx, r in enumerate(results, start=1):
            words = r.chunk.text.split()
            if len(words) > budget:
                if budget < 30:  # skip a useless tail-end fragment
                    break
                text = " ".join(words[:budget]) + " …"
            else:
                text = " ".join(words)
            blocks.append(self._excerpt_block(r, idx, len(results), text))
            budget -= len(text.split())
            if budget <= 0:
                break

        evidence_block = (
            self._evidence_directive(artifact, len(blocks))
            + "\n\n".join(blocks)
            + "\n\n" + self._EVIDENCE_RULE + "\n"
        )
        return evidence_block, ""

    def _excerpt_block(self, r, idx, total, text):
        """Format one retrieval result as a structured excerpt block
        (SOURCE / PAGE / KIND / PASSAGE). ``total`` may be an int (flat
        block) or a placeholder string (grouped block)."""
        chunk = r.chunk
        chapter_title = (getattr(chunk, "chapter_title", "") or "").strip()
        section_title = (getattr(chunk, "section_title", "") or "").strip()
        source_line = " / ".join(
            s for s in (chapter_title, section_title) if s
        ) or "(untitled)"
        try:
            page_label = chunk.page_range_label()
        except AttributeError:
            page_label = f"p{getattr(chunk, 'page_start', '?')}"
        kinds = getattr(chunk, "kinds", None) or ["prose"]
        kind_label = "+".join(sorted(kinds))
        bar = "━" * max(0, 50 - len(str(idx)) - len(str(total)))
        return (
            f"━━ EXCERPT {idx} of {total} {bar}\n"
            f"  SOURCE  : {source_line}\n"
            f"  PAGE    : {page_label}\n"
            f"  KIND    : {kind_label}\n"
            f"  PASSAGE :\n"
            f"  «{text}»"
        )

    def _evidence_directive(self, artifact, n_excerpts):
        """The mandatory-rules header (RULE 2/3/6/7) that precedes the
        excerpts -- shared by the flat and grouped evidence blocks."""
        rule = self._EVIDENCE_RULE
        if artifact == "script":
            rule_2 = (
                "  RULE 2 (PARAPHRASE NATURALLY). This is spoken narration — "
                "use plain, conversational language while keeping the textbook's "
                "underlying meaning faithful. Direct quotation is RESERVED for "
                "technical definitions where paraphrase would be lossy "
                "(e.g. precise mathematical statements). Do NOT pepper the "
                "script with quoted fragments — the speaker should sound like a "
                "teacher explaining, not someone reading aloud from a book."
            )
            header_label = "TEXTBOOK GROUNDING — MANDATORY RULES FOR SPOKEN SCRIPT"
        else:  # "slide" or "assessment"
            rule_2 = (
                "  RULE 2 (TEACH IN YOUR OWN WORDS — no quote-dumping). "
                "Write each bullet as clear instructional prose, the way a "
                "lecturer explains a concept — NOT by quoting a sentence from "
                "the book and tacking on a gloss. Lead with the idea stated "
                "plainly, in your own phrasing, using the textbook's facts and "
                "terminology faithfully.\n"
                "  \n"
                "  HARD CONSTRAINTS:\n"
                "    (a) Do NOT open a bullet with a quoted sentence followed "
                "by a dash and an explanation. That reads like a citation "
                "dump, not teaching.\n"
                "    (b) Reserve \"direct quotation\" for a precise definition "
                "or a formula statement where exact wording matters — at most "
                "ONE short quote per slide, and only when paraphrase would "
                "lose precision.\n"
                "    (c) State only what the excerpts support. Add no new "
                "facts; if you cannot say something from the evidence, omit it.\n"
                "    (d) For an algorithm, SHOW its steps as a short numbered "
                "procedure in your own words rather than quoting a description "
                "of it."
            )
            header_label = "TEXTBOOK GROUNDING — MANDATORY RULES"
        return (
            f"{rule}\n"
            f"{header_label}\n"
            f"{rule}\n\n"
            f"You have {n_excerpts} excerpts from the textbook below. They are your "
            "AUTHORITATIVE source for this topic. Follow these rules without "
            "exception:\n\n"
            + rule_2 + "\n\n"
            "  RULE 3 (ABSTAIN IF UNSUPPORTED). If you cannot ground a claim in "
            "ANY excerpt below, either drop the claim or restate what the textbook "
            "DOES cover on that topic. Do NOT make textbook-attributed claims that "
            "the excerpts do not support.\n\n"
            "  RULE 6 (PRESERVE WORKED EXAMPLES). If an excerpt's KIND "
            "header contains \"example\", preserve the concrete trace — "
            "specific data points, iteration steps, intermediate values. "
            "Do NOT reduce it to an abstract definition. Author-curated "
            "decks rely on worked examples to teach algorithm internals; "
            "stripping the numbers loses the lesson.\n\n"
            "  RULE 7 (PRESERVE MATH NOTATION). If an excerpt's KIND "
            "header contains \"equation\", the passage carries math "
            "symbols extractable from the source PDF. Preserve them in "
            "the slide using inline LaTeX ``$\\alpha$``, ``$\\sum_i$``, "
            "``$x_i$`` etc., or as display math ``\\[ ... \\]`` for "
            "stand-alone formulas. Do NOT paraphrase math symbols into "
            "prose (\"the sum of squared distances\") when the source "
            "shows them in notation — preserving the notation is what "
            "makes the slide pedagogically equivalent to the textbook.\n\n"
            + self._EXCERPTS_RULE + "\n\n"
        )

    _GROUPED_PER_SLIDE_K = 3

    def _build_grouped_evidence_block(self, outline, artifact="slide"):
        """Group evidence BY outline slide: each slide-topic gets its own
        labeled set of excerpts, so the writer sees focused per-slide
        context instead of one undifferentiated chapter dump. Retrieves per
        slide-topic (scoped to the bound sections -- cheap index lookups,
        no LLM), dedupes chunks globally so none repeats across slides, and
        shares one rule header + the total word budget. Returns ``("", "")``
        when there is no retriever (vanilla) or no usable outline -- the
        caller then falls back to the flat chapter-level block."""
        if self.retriever is None or not outline:
            return "", ""
        groups = []
        seen_ids = set()
        idx = 0
        budget = self._EVIDENCE_WORD_BUDGET
        for slide in outline:
            if budget <= 0:
                break
            if not isinstance(slide, dict):
                continue
            title = (slide.get("title") or "").strip()
            desc = (slide.get("description") or "").strip()
            q = f"{title}. {desc}".strip(". ")
            if not q:
                continue
            try:
                results = self.retriever.search(
                    q, top_k=self._GROUPED_PER_SLIDE_K,
                    section_ids=self.section_ids,
                )
            except Exception:
                continue
            excerpts = []
            for r in _dedupe_results(results):
                cid = getattr(r.chunk, "chunk_id", None) or id(r.chunk)
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                words = (r.chunk.text or "").split()
                if len(words) > budget:
                    if budget < 30:
                        break
                    text = " ".join(words[:budget]) + " …"
                else:
                    text = " ".join(words)
                idx += 1
                excerpts.append(self._excerpt_block(r, idx, "—", text))
                budget -= len(text.split())
                if budget <= 0:
                    break
            if excerpts:
                label = f"▼ EVIDENCE FOR SLIDE: {title or '(topic)'}"
                groups.append(label + "\n\n" + "\n\n".join(excerpts))
        if not groups:
            return "", ""
        evidence_block = (
            self._evidence_directive(artifact, idx)
            + "\n\n".join(groups)
            + "\n\n" + self._EVIDENCE_RULE + "\n"
        )
        return evidence_block, ""

    # Per-slide section binding: narrow the chapter's bound sections to the
    # best-matched few for one slide before retrieving its evidence.
    _PER_SLIDE_TOP_SECTIONS = 2
    _PER_SLIDE_RETRIEVE_K = 8
    _PER_SLIDE_RRF_K = 60

    def _pick_per_slide_sections(self, slide_query: str):
        """Narrow the chapter's bound section_ids to the top-K sections for
        THIS slide's query. Returns None when no retriever or no chapter
        binding (vanilla path) -- the caller keeps the chapter-wide filter."""
        from collections import defaultdict
        if self.retriever is None or not self.section_ids:
            return None
        try:
            results = self.retriever.search(
                slide_query,
                top_k=self._PER_SLIDE_RETRIEVE_K,
                section_ids=self.section_ids,
            )
        except Exception as e:
            print(f"[grounding] per-slide section pick failed ({e}); using chapter-wide filter")
            return None
        if not results:
            return None
        section_scores = defaultdict(float)
        for rank, r in enumerate(results):
            section_scores[r.chunk.section_id] += 1.0 / (self._PER_SLIDE_RRF_K + rank)
        ranked = sorted(section_scores.items(), key=lambda kv: -kv[1])
        return [sid for sid, _ in ranked[:self._PER_SLIDE_TOP_SECTIONS]]

    def _build_per_slide_evidence(self, slide_query: str, artifact: str = "slide") -> tuple:
        """Narrow the section filter to this slide's best-matched sections,
        then build the evidence block. Falls back to chapter-wide retrieval
        when no narrowing is possible (vanilla path or thin chapter)."""
        per_slide = self._pick_per_slide_sections(slide_query)
        return self._build_evidence_block(
            slide_query, artifact=artifact, section_ids_override=per_slide,
        )

    @staticmethod
    def _with_evidence(evidence_block: str, prompt: str) -> str:
        """Prepend a non-empty evidence block to ``prompt``.

        Returns ``prompt`` UNCHANGED (same object) when the block is empty,
        which is what keeps the vanilla pipeline byte-identical.
        """
        if not evidence_block:
            return prompt
        return evidence_block + "\n" + prompt

    # ------------------------------------------------------------------ #
    # Checkpoint helpers (resume support)                                #
    # ------------------------------------------------------------------ #
    CHECKPOINT_FILENAME = "_checkpoint.json"

    def _checkpoint_path(self) -> str:
        return os.path.join(self.output_dir, self.CHECKPOINT_FILENAME)

    def _save_checkpoint(self, done_steps, last_slide_idx=None):
        """Persist mid-run state so a crash can be resumed.

        Writes atomically via rename to avoid a truncated checkpoint if the
        process dies mid-write.
        """
        payload = {
            "version": 1,
            "done_steps": list(done_steps),
            "last_slide_idx": last_slide_idx,
            "slides_outline": self.slides_outline,
            "latex_dict": {str(k): v for k, v in self.latex_dict.items()},
            "slides_script": {str(k): v for k, v in self.slides_script.items()},
            "assessment_template": {
                str(k): v for k, v in self.assessment_template.items()
            },
            "assessment_content": {
                str(k): v for k, v in self.assessment_content.items()
            },
            "latex_prefix": getattr(self, "latex_prefix", ""),
            "latex_suffix": getattr(self, "latex_suffix", ""),
            "user_feedback": getattr(self, "user_feedback", {}),
            "time_slides": self.time_slides,
            "token_slides": self.token_slides,
            "time_script": self.time_script,
            "token_script": self.token_script,
            "time_assessment": self.time_assessment,
            "token_assessment": self.token_assessment,
        }
        os.makedirs(self.output_dir, exist_ok=True)
        final_path = self._checkpoint_path()
        tmp_path = final_path + ".tmp"
        # Compact separators (no spaces/newlines) — this checkpoint is written
        # after every slide, so keeping it small matters more than readability.
        with open(tmp_path, "w") as f:
            json.dump(payload, f, separators=(",", ":"), default=str)
        os.replace(tmp_path, final_path)

    def _load_checkpoint(self):
        """Return the checkpoint dict and hydrate self.* fields; None if absent."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                ckpt = json.load(f)
        except Exception as e:
            print(f"[resume] Failed to load checkpoint at {path}: {e}")
            return None

        self.slides_outline = ckpt.get("slides_outline", [])
        self.latex_dict = {
            int(k): v for k, v in ckpt.get("latex_dict", {}).items()
        }
        self.slides_script = {
            int(k): v for k, v in ckpt.get("slides_script", {}).items()
        }
        self.assessment_template = {
            int(k): v for k, v in ckpt.get("assessment_template", {}).items()
        }
        self.assessment_content = {
            int(k): v for k, v in ckpt.get("assessment_content", {}).items()
        }
        self.latex_prefix = ckpt.get("latex_prefix", "")
        self.latex_suffix = ckpt.get("latex_suffix", "")
        self.time_slides = ckpt.get("time_slides", 0)
        self.token_slides = ckpt.get("token_slides", 0)
        self.time_script = ckpt.get("time_script", 0)
        self.token_script = ckpt.get("token_script", 0)
        self.time_assessment = ckpt.get("time_assessment", 0)
        self.token_assessment = ckpt.get("token_assessment", 0)
        return ckpt

    def _delete_checkpoint(self):
        """Remove the checkpoint file after successful completion."""
        path = self._checkpoint_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError as e:
                print(f"Warning: could not remove checkpoint {path}: {e}")
    
   
    def run(self, chapter: Dict[str, str], user_feedback: Dict[str, Any]):
        """
        Run the slides deliberation process
        
        Args:
            chapter: Dictionary containing chapter information
            context: Dictionary containing context information
            
        Returns:
            Tuple of (latex_source, slides_script_md, assessment_md)
        """
        print(f"\n{'='*50}\nStarting Slides Deliberation: {self.name}\n{'='*50}\n")
        print(f"Chapter: {chapter['title']}\n")

        # ------------------------------------------------------------------ #
        # Resume: try to load checkpoint first so we hydrate counters from it #
        # rather than zeroing them out.                                       #
        # ------------------------------------------------------------------ #
        done_steps = []
        ckpt = self._load_checkpoint() if self.resume else None
        if ckpt is not None:
            done_steps = list(ckpt.get("done_steps", []))
            print(f"[resume] Loaded checkpoint from {self._checkpoint_path()} "
                  f"— completed steps: {done_steps}")
        else:
            self.time_slides, self.token_slides = 0, 0
            self.time_script, self.token_script = 0, 0
            self.time_assessment, self.token_assessment = 0, 0

        self.user_feedback = user_feedback

        # Step 0: Always re-fetch templates (cheap, deterministic, no LLM)
        self._get_templates()

        # Step 1: Generate slides outline
        if "outline" not in done_steps:
            self._generate_slides_outline(chapter)
            done_steps.append("outline")
            self._save_checkpoint(done_steps)
        else:
            print("[resume] Skipped step 1 (slides outline)")

        # Step 2: Generate initial LaTeX template
        if "initial_latex" not in done_steps:
            self._generate_initial_latex(chapter)
            done_steps.append("initial_latex")
            self._save_checkpoint(done_steps)
        else:
            print("[resume] Skipped step 2 (initial LaTeX)")

        # Step 3: Generate slides script template
        if "script_template" not in done_steps:
            self._generate_slides_script_template()
            done_steps.append("script_template")
            self._save_checkpoint(done_steps)
        else:
            print("[resume] Skipped step 3 (script template)")

        # Step 4: Generate assessment template
        if "assessment_template" not in done_steps:
            self._generate_assessment_template(chapter)
            done_steps.append("assessment_template")
            self._save_checkpoint(done_steps)
        else:
            print("[resume] Skipped step 4 (assessment template)")

        # Step 5: For each slide, generate content, LaTeX, script, and assessment.
        # A slide is considered fully generated when assessment_content has an
        # entry for it (last sub-step 5.4 writes it).
        for slide_idx, slide in enumerate(self.slides_outline):
            if slide_idx in self.assessment_content:
                print(f"[resume] Skipped slide {slide_idx + 1}/{len(self.slides_outline)}: "
                      f"{slide.get('title', '')} — already generated")
                continue

            print(f"\n{'-'*50}\nProcessing Slide {slide_idx + 1}/{len(self.slides_outline)}: {slide['title']}\n{'-'*50}\n")

            # Get context window (current slide plus adjacent slides for context)
            context_slides = self._get_context_slides(slide_idx)

            # Step 5.1: Generate slide draft content
            slide_draft = self._generate_slide_draft(slide, context_slides, chapter)

            # Step 5.2: Generate slide LaTeX code (potentially multiple frames)
            self._generate_slide_latex(slide_idx, slide, slide_draft)

            # Step 5.3: Generate slide script
            self._generate_slide_script(slide_idx, slide, slide_draft)

            # Step 5.4: Generate slide assessment
            self._generate_slide_assessment(slide_idx, slide, slide_draft)

            # Checkpoint after every completed slide
            self._save_checkpoint(done_steps, last_slide_idx=slide_idx)
        
        # Step 6: Compile final LaTeX source
        latex_source = self._compile_latex_source()
        preflight = normalize_beamer_source(latex_source)
        latex_source = preflight.source
        if preflight.changed:
            for message in repair_messages(preflight):
                print(f"[preflight] {message}")
        
        # Step 7: Compile final slides script
        slides_script_md = self._compile_slides_script()
        
        # Step 8: Compile final assessment
        assessment_md = self._compile_assessment()
        
        # Save the results
        latex_path = os.path.join(self.output_dir, f"slides.tex")
        script_path = os.path.join(self.output_dir, f"script.md")
        assessment_path = os.path.join(self.output_dir, f"assessment.md")

        os.makedirs(self.output_dir, exist_ok=True)
        with open(latex_path, "w") as f:
            f.write(latex_source)
        with open(script_path, "w") as f:
            f.write(slides_script_md)
        with open(assessment_path, "w") as f:
            f.write(assessment_md)
        
        print(f"\n{'='*50}\nSlides Deliberation Complete\n{'='*50}\n")
        print(f"LaTeX slides saved to: {latex_path}")
        print(f"Slides script saved to: {script_path}")
        print(f"Assessment saved to: {assessment_path}")

        with open(os.path.join(self.output_dir, "statistics_{}.json").format(self.id), "w") as f:
            json.dump({
                "time_slides": self.time_slides,
                "token_slides": self.token_slides,
                "time_script": self.time_script,
                "token_script": self.token_script,
                "time_assessment": self.time_assessment,
                "token_assessment": self.token_assessment
            }, f, indent=2)

        # Chapter finished successfully — clean up the resume checkpoint.
        self._delete_checkpoint()

    def _get_templates(self):
        """Get LaTeX template"""
        self.latex_template = SlideUtils.get_latex_template(
            catalog=self.catalog
        )
    
    def _generate_slides_outline(self, chapter: Dict[str, str]):
        """Generate slides outline using Instructional Designer agent"""
        instructional_designer = self.agents.get("instructional_designer")
        if not instructional_designer:
            raise ValueError("Instructional Designer agent not found")
        
        # Create a simple outline template example
        outline_template = """[
            {
                "slide_id": 1,
                "title": "Introduction to Topic",
                "description": "Brief overview of the main topic"
            },
            {
                "slide_id": 2,
                "title": "Key Concepts",
                "description": "Explanation of key concepts"
            }
            ]"""
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following chapter information, create a detailed slides outline in JSON format.
        
        Chapter Title: {chapter['title']}
        Chapter Description: {chapter['description']}
        
        User Feedback:
        {json.dumps(self.user_feedback, indent=2)}

        Please generate a comprehensive slides outline with about {self.catalog_dict['slides_length'] / 3} slides covering all important aspects of this chapter.
        The outline should be in JSON format with the following structure:
        
        {outline_template}
        
        Please try to use the simple and common latex grammer to guarantee the LaTeX code can be compiled successfully.
        Your response must be valid JSON that can be parsed programmatically.
        """
        
        # Reset agent history to ensure clean context
        instructional_designer.reset_history()
        
        # Get the response from the agent
        print("Generating slides outline...")
        response, elapsed_time, token_usage = instructional_designer.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_slides += elapsed_time
        self.token_slides += token_usage
        
        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                self.slides_outline = json.loads(json_str)
            else:
                # If no JSON array pattern is found, try direct parsing
                self.slides_outline = json.loads(response)
            
            print(f"Successfully generated outline with {len(self.slides_outline)} slides")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Could not parse JSON response from agent: {e}")
            print("Response:", response)
            # Create a minimal outline as fallback
            self.slides_outline = [
                {"slide_id": 1, "title": "Introduction", "description": "Introduction to " + chapter['title']},
                {"slide_id": 2, "title": "Overview", "description": "Overview of key concepts"},
                {"slide_id": 3, "title": "Conclusion", "description": "Summary and conclusion"}
            ]
    
    def _generate_initial_latex(self, chapter: Dict[str, str]):
        """Generate initial LaTeX template using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following slides outline and LaTeX template, generate initial LaTeX code for a presentation.
        
        Chapter Title: {chapter['title']}
        
        Slides Outline:
        {json.dumps(self.slides_outline, indent=2)}

        User Feedback:
        [For slides]{json.dumps(self.user_feedback['slides'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}

        LaTeX Template:
        ```latex
        {self.latex_template}
        ```
        
        Please generate the initial LaTeX code with frame placeholders for each slide in the outline.
        Each slide can have one or more frames based on content complexity.
        
        Example of frame structures:
        \\begin{{frame}}[fragile]
            \\frametitle{{Slide Title - Part 1}}
            % Content will be added here
        \\end{{frame}}
        
        \\begin{{frame}}[fragile]
            \\frametitle{{Slide Title - Part 2}}
            % Content will be added here
        \\end{{frame}}

        1. Don't use non-English characters directly, e.g. use $\gamma$ instead of γ, $\epsilon$ instead of ε
        2. If any of symbols has a special meaning, add a slash. e.g. use \& instead of &
        3. Colors: only use standard color names (red, blue, teal, gray, ...), colors defined in the provided template, or inline hex via \\textcolor[HTML]{{RRGGBB}}{{...}}. Never invent named colors such as electricblue, and do not add \\usepackage lines or color definitions beyond the provided template

        Your response should be LaTeX code that can be compiled directly.
        """
        

        # Textbook grounding (no-op when self.retriever is None): group the
        # evidence BY outline slide so the writer sees focused per-slide
        # context; fall back to a flat chapter-level block when the outline
        # yields nothing in scope.
        evidence_block, _ = self._build_grouped_evidence_block(
            getattr(self, "slides_outline", None)
        )
        if not evidence_block:
            evidence_block, _ = self._build_evidence_block(
                f"{chapter['title']}. {chapter.get('description', '')}"
            )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print("Generating initial LaTeX template...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_slides += elapsed_time
        self.token_slides += token_usage
        
        # Store the full LaTeX source
        self.full_latex_source = response
        
        # Parse frames to build the LaTeX dictionary
        self._parse_latex_frames(response)
        
        print(f"Successfully generated initial LaTeX template")
    
    def _parse_latex_frames(self, latex_source: str):
        """Parse LaTeX frames into a dictionary, grouping by slide"""
        # Find all frames with their content
        frame_pattern = re.compile(r'\\begin{frame}(.*?)\\end{frame}', re.DOTALL)
        frametitle_pattern = re.compile(r'\\frametitle{(.*?)}', re.DOTALL)
        
        matches = frame_pattern.finditer(latex_source)
        
        self.latex_dict = {}
        current_slide_idx = 0
        
        for i, match in enumerate(matches):
            frame_content = match.group(1)
            title_match = frametitle_pattern.search(frame_content)
            
            title = title_match.group(1).strip() if title_match else f"Frame {i+1}"
            
            # Initialize slide entry if it doesn't exist
            if current_slide_idx not in self.latex_dict:
                self.latex_dict[current_slide_idx] = {
                    "frames": [],
                    "slide_title": title.split(" - ")[0] if " - " in title else title
                }
            
            # Add frame to current slide
            self.latex_dict[current_slide_idx]["frames"].append({
                "full_frame": match.group(0),
                "content": frame_content.strip(),
                "title": title,
                "frame_index": len(self.latex_dict[current_slide_idx]["frames"])
            })
            
            # Simple heuristic: if we have processed enough frames for expected slides
            if len(self.latex_dict[current_slide_idx]["frames"]) >= 1 and current_slide_idx < len(self.slides_outline) - 1:
                # Check if next frame title suggests a new slide
                next_match = None
                for next_match in frame_pattern.finditer(latex_source):
                    if next_match.start() > match.end():
                        break
                
                if next_match:
                    next_content = next_match.group(1)
                    next_title_match = frametitle_pattern.search(next_content)
                    next_title = next_title_match.group(1).strip() if next_title_match else ""
                    
                    # If title doesn't contain current slide title, it's likely a new slide
                    current_base_title = self.latex_dict[current_slide_idx]["slide_title"]
                    if current_base_title not in next_title and not next_title.startswith(current_base_title):
                        current_slide_idx += 1
        
        # Store the parts before and after the frames
        all_frames = ''.join([
            frame["full_frame"] 
            for slide_data in self.latex_dict.values() 
            for frame in slide_data["frames"]
        ])
        parts = latex_source.split(all_frames)
        
        if len(parts) >= 2:
            self.latex_prefix = parts[0]
            self.latex_suffix = parts[1]
        else:
            # Fallback if splitting didn't work as expected
            self.latex_prefix = latex_source.split('\\begin{document}')[0] + '\\begin{document}\n\n\\frame{\\titlepage}\n\n'
            self.latex_suffix = '\n\\end{document}'
    
    def _generate_slides_script_template(self):
        """Generate slides script template using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Create a simple script template example
        script_template = """[
            {
                "slide_id": 1,
                "title": "Introduction to Topic",
                "script": "Welcome to today's lecture on this topic. We're going to cover..."
            },
            {
                "slide_id": 2,
                "title": "Key Concepts",
                "script": "The key concepts we need to understand are..."
            }
            ]"""
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following slides outline, create a template for slides scripts in JSON format.
        
        Slides Outline:
        {json.dumps(self.slides_outline, indent=2)}

        User Feedback:
        [For script]{json.dumps(self.user_feedback['script'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}

        Please generate a script template with placeholders for each slide in the outline.
        The template should be in JSON format with the following structure:
        
        {script_template}
        
        Each script entry should include a brief placeholder description of what would be said when presenting that slide.
        Your response must be valid JSON that can be parsed programmatically.
        """
        

        # Textbook grounding (no-op when self.retriever is None): use the
        # outline as the query; scripts get the softer spoken-narration
        # rule-set.
        outline_query = " ".join(
            sl.get("title", "") for sl in self.slides_outline
        ) if self.slides_outline else ""
        evidence_block, _ = self._build_evidence_block(
            outline_query, artifact="script"
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print("Generating slides script template...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_script += elapsed_time
        self.token_script += token_usage
        
        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                self.slides_script = json.loads(json_str)
                # Convert to dictionary for easier access
                self.slides_script = {item["slide_id"]-1: item for item in self.slides_script}
            else:
                # If no JSON array pattern is found, try direct parsing
                script_list = json.loads(response)
                self.slides_script = {item["slide_id"]-1: item for item in script_list}
            
            print(f"Successfully generated script template for {len(self.slides_script)} slides")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Could not parse JSON response from agent: {e}")
            print("Response:", response)
            # Create a minimal script template as fallback
            self.slides_script = {}
            for i, slide in enumerate(self.slides_outline):
                self.slides_script[i] = {
                    "slide_id": i+1,
                    "title": slide["title"],
                    "script": f"Placeholder script for {slide['title']}"
                }
    
    def _generate_assessment_template(self, chapter: Dict[str, str]):
        """Generate assessment template using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Create a simple assessment template example
        assessment_template = """[
            {
                "slide_id": 1,
                "title": "Introduction to Topic",
                "assessment": {
                "questions": [
                    {
                    "type": "multiple_choice",
                    "question": "Sample question about the topic?",
                    "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                    "correct_answer": "A",
                    "explanation": "Explanation of why this is correct"
                    }
                ],
                "activities": ["Activity description"],
                "learning_objectives": ["Learning objective 1", "Learning objective 2"]
                }
            }
            ]"""
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following chapter information and slides outline, create an assessment template in JSON format.
        
        Chapter Title: {chapter['title']}
        Chapter Description: {chapter['description']}
        
        Slides Outline:
        {json.dumps(self.slides_outline, indent=2)}

        User Feedback:
        [For assessment]{json.dumps(self.user_feedback['assessment'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}

        Please generate an assessment template with placeholders for each slide in the outline.
        The template should include questions, activities, and learning objectives for each slide.
        The template should be in JSON format with the following structure:
        
        {assessment_template}
        
        Assessments should meet the following requirements:
        {self.catalog_dict['assessment_planning']}

        Each assessment entry should include:
        1. Multiple choice questions (with options and correct answers)
        2. Practical activities or exercises
        3. Learning objectives for the slide
        
        Your response must be valid JSON that can be parsed programmatically.
        """
        

        # Textbook grounding (no-op when self.retriever is None). Assessments
        # draw on cross-chapter context (review questions span the course),
        # so search the whole textbook instead of the chapter binding.
        evidence_block, _ = self._build_evidence_block(
            f"{chapter['title']}. {chapter.get('description', '')}",
            artifact="assessment",
            cross_chapter=True,
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print("Generating assessment template...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_assessment += elapsed_time
        self.token_assessment += token_usage
        
        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                assessment_list = json.loads(json_str)
                # Convert to dictionary for easier access
                self.assessment_template = {item["slide_id"]-1: item for item in assessment_list}
            else:
                # If no JSON array pattern is found, try direct parsing
                assessment_list = json.loads(response)
                self.assessment_template = {item["slide_id"]-1: item for item in assessment_list}
            
            print(f"Successfully generated assessment template for {len(self.assessment_template)} slides")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Could not parse JSON response from agent: {e}")
            print("Response:", response)
            # Create a minimal assessment template as fallback
            self.assessment_template = {}
            for i, slide in enumerate(self.slides_outline):
                self.assessment_template[i] = {
                    "slide_id": i+1,
                    "title": slide["title"],
                    "assessment": {
                        "questions": [],
                        "activities": [],
                        "learning_objectives": []
                    }
                }
    
    def _get_context_slides(self, current_idx: int, context_size: int = 1):
        """Get adjacent slides for context"""
        context_slides = []
        
        # Add previous slides if available
        start_idx = max(0, current_idx - context_size)
        for i in range(start_idx, current_idx):
            context_slides.append({
                "position": "previous",
                "slide_id": i+1,
                "info": self.slides_outline[i]
            })
        
        # Add current slide
        context_slides.append({
            "position": "current",
            "slide_id": current_idx+1,
            "info": self.slides_outline[current_idx]
        })
        
        # Add next slides if available
        end_idx = min(len(self.slides_outline), current_idx + context_size + 1)
        for i in range(current_idx + 1, end_idx):
            context_slides.append({
                "position": "next",
                "slide_id": i+1,
                "info": self.slides_outline[i]
            })
        
        return context_slides
    
    def _generate_slide_draft(self, slide: Dict[str, str], context_slides: List[Dict[str, Any]], chapter: Dict[str, str]):
        """Generate detailed slide draft using Teaching Faculty agent"""
        teaching_faculty = self.agents.get("teaching_faculty")
        if not teaching_faculty:
            raise ValueError("Teaching Faculty agent not found")
        
        # Create the prompt for the agent
        prompt = f"""
        Please create detailed educational content for the following slide:
        
        Chapter: {chapter['title']}
        Slide: {slide['title']}
        Description: {slide['description']}
        
        Context (adjacent slides for reference):
        {json.dumps(context_slides, indent=2)}

        User Feedback:
        [For slides]{json.dumps(self.user_feedback['slides'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}
        
        Please generate comprehensive, detailed, and easy-to-understand educational content for this slide.
        Your content should include:
        1. Clear explanations of concepts
        2. Examples or illustrations where appropriate
        3. Key points to emphasize
        4. Any formulas, code snippets, or diagrams that would be helpful, but dont try to include any pictures in the LaTeX code.
        
        Focus on making the content educational, engaging, and aligned with the chapter's learning objectives.
        Note: Your output length needs to be kept within a reasonable range so that it can fit on a single PPT slide.
        """
        

        # Textbook grounding (no-op when self.retriever is None): per-slide
        # retrieval narrowed to the slide's best-matched sections.
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_faculty.reset_history()
        
        # Get the response from the agent
        print(f"Generating detailed content for slide: {slide['title']}...")
        response, elapsed_time, token_usage = teaching_faculty.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_slides += elapsed_time
        self.token_slides += token_usage
        
        return response
    
    def _generate_slide_latex(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate LaTeX code for a slide using Teaching Assistant agent - can generate multiple frames"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get the current LaTeX frames if they exist
        current_frames = self.latex_dict.get(slide_idx, {}).get("frames", [])
        current_frames_text = "\n\n".join([frame["full_frame"] for frame in current_frames]) if current_frames else None
        
        # Use utility function to generate prompt
        prompt = SlideUtils.generate_latex_frame_prompt(
            title=slide['title'],
            content=slide_draft,
            description=slide.get('description'),
            current_frames=current_frames_text,
            user_feedback=self.user_feedback,
            max_frames=3
        )
        

        # Textbook grounding (no-op when self.retriever is None): per-slide
        # narrowed evidence.
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print(f"Generating LaTeX code for slide: {slide['title']}...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_slides += elapsed_time
        self.token_slides += token_usage
        
        # Use utility function to extract frames
        frame_matches = SlideUtils.extract_latex_frames(response)
        
        if frame_matches:
            # Initialize slide entry if it doesn't exist
            if slide_idx not in self.latex_dict:
                self.latex_dict[slide_idx] = {
                    "frames": [],
                    "slide_title": slide['title']
                }
            else:
                # Clear existing frames for this slide
                self.latex_dict[slide_idx]["frames"] = []
                self.latex_dict[slide_idx]["slide_title"] = slide['title']
            
            # Add all frames for this slide
            for i, frame_code in enumerate(frame_matches):
                self.latex_dict[slide_idx]["frames"].append({
                    "full_frame": frame_code,
                    "content": frame_code.replace("\\begin{frame}", "").replace("\\end{frame}", "").strip(),
                    "title": slide['title'] + (f" - Part {i+1}" if len(frame_matches) > 1 else ""),
                    "frame_index": i
                })
            
            print(f"Generated {len(frame_matches)} frame(s) for slide: {slide['title']}")
        else:
            # Fallback if no frames were found
            fallback_frame = f"""\\begin{{frame}}[fragile]
                \\frametitle{{{slide['title']}}}
                {slide.get('description', '')}
            \\end{{frame}}"""
            
            self.latex_dict[slide_idx] = {
                "frames": [{
                    "full_frame": fallback_frame,
                    "content": fallback_frame.replace("\\begin{frame}", "").replace("\\end{frame}", "").strip(),
                    "title": slide['title'],
                    "frame_index": 0
                }],
                "slide_title": slide['title']
            }
            print(f"Generated fallback frame for slide: {slide['title']}")
    
    def _generate_slide_script(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate script for a slide using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get adjacent slide scripts for context
        prev_script = self.slides_script.get(slide_idx-1, {}).get("script", "") if slide_idx > 0 else ""
        current_script = self.slides_script.get(slide_idx, {}).get("script", "")
        next_script = self.slides_script.get(slide_idx+1, {}).get("script", "") if slide_idx < len(self.slides_outline)-1 else ""
        
        # Get all frames for this slide
        frames_info = ""
        if slide_idx in self.latex_dict:
            for i, frame in enumerate(self.latex_dict[slide_idx]["frames"]):
                frames_info += f"Frame {i+1}:\n```latex\n{frame['full_frame']}\n```\n\n"
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following slide content, generate a detailed speaking script for presenting this slide.
        Note: This slide may have multiple frames, so your script should cover all frames smoothly.
        
        Slide Title: {slide['title']}
        Slide Description: {slide['description']}
        
        Detailed Content:
        {slide_draft}
        
        LaTeX Frames for this slide:
        {frames_info}
        
        Context (adjacent slides' scripts for smooth transitions):
        Previous slide script: {prev_script[:200] + "..." if len(prev_script) > 200 else prev_script}
        Current placeholder: {current_script}
        Next slide script: {next_script[:200] + "..." if len(next_script) > 200 else next_script}

        User Feedback:
        [For script]{json.dumps(self.user_feedback['script'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}
        
        Please generate a comprehensive speaking script for this slide that:
        1. Introduces the slide topic
        2. Explains all key points clearly and thoroughly
        3. If multiple frames exist, provides smooth transitions between frames
        4. Provides relevant examples or analogies
        5. Connects to previous or upcoming content
        6. Includes rhetorical questions or engagement points for students
        
        The script should be detailed enough for someone else to present effectively from it.
        If there are multiple frames, clearly indicate when to advance to the next frame.
        """
        

        # Textbook grounding (no-op when self.retriever is None): per-slide
        # narrowed evidence with the spoken-script rule-set.
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}",
            artifact="script",
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print(f"Generating speaking script for slide: {slide['title']}...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_script += elapsed_time
        self.token_script += token_usage
        
        # Update the slides script dictionary
        self.slides_script[slide_idx] = {
            "slide_id": slide_idx + 1,
            "title": slide['title'],
            "script": response,
            "frame_count": len(self.latex_dict.get(slide_idx, {}).get("frames", []))
        }
    
    def _generate_slide_assessment(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate assessment for a slide using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get the current assessment template for this slide
        template = self.assessment_template.get(slide_idx, {})
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following slide content and assessment template, generate detailed assessment content for this slide.
        
        Slide Title: {slide['title']}
        Slide Description: {slide['description']}
        
        Detailed Content:
        {slide_draft}
        
        Assessment Template:
        {json.dumps(template, indent=2)}

        User Feedback:
        [For assessment]{json.dumps(self.user_feedback['assessment'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}
        
        Please generate comprehensive assessment content in JSON format that includes:
        1. Multiple choice questions (3-5 questions) with 4 options each, correct answer, and explanation
        2. Practical activities or exercises related to the slide content
        3. Clear learning objectives for this slide
        4. Discussion questions for student engagement
        
        The assessment should test understanding of the key concepts presented in this slide.
        
        Your response should be in JSON format like:
        {{
            "slide_id": {slide_idx + 1},
            "title": "{slide['title']}",
            "assessment": {{
                "questions": [
                    {{
                        "type": "multiple_choice",
                        "question": "Question text?",
                        "options": ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"],
                        "correct_answer": "A",
                        "explanation": "Explanation text"
                    }}
                ],
                "activities": ["Activity description"],
                "learning_objectives": ["Objective 1", "Objective 2"],
                "discussion_questions": ["Discussion question 1"]
            }}
        }}
        
        Your response must be valid JSON that can be parsed programmatically.
        """
        

        # Textbook grounding (no-op when self.retriever is None): per-slide
        # assessments use cross-chapter retrieval (review questions span the
        # course), so skip the per-slide narrowing here.
        evidence_block, _ = self._build_evidence_block(
            f"{slide['title']}. {slide.get('description', '')}",
            artifact="assessment",
            cross_chapter=True,
        )
        prompt = self._with_evidence(evidence_block, prompt)

        # Reset agent history to ensure clean context
        teaching_assistant.reset_history()
        
        # Get the response from the agent
        print(f"Generating assessment for slide: {slide['title']}...")
        response, elapsed_time, token_usage = teaching_assistant.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_assessment += elapsed_time
        self.token_assessment += token_usage
        
        # Parse the JSON response
        try:
            # Try to extract JSON from the response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                assessment_data = json.loads(json_str)
                self.assessment_content[slide_idx] = assessment_data
            else:
                # If no JSON pattern is found, try direct parsing
                self.assessment_content[slide_idx] = json.loads(response)
            
            print(f"Successfully generated assessment for slide: {slide['title']}")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Could not parse JSON response from agent: {e}")
            print("Response:", response)
            # Create a minimal assessment as fallback
            self.assessment_content[slide_idx] = {
                "slide_id": slide_idx + 1,
                "title": slide['title'],
                "assessment": {
                    "questions": [],
                    "activities": [f"Practice exercise for {slide['title']}"],
                    "learning_objectives": [f"Understand concepts from {slide['title']}"],
                    "discussion_questions": [f"Discuss the implications of {slide['title']}"]
                }
            }
    
    def _compile_latex_source(self) -> str:
        """Compile all LaTeX frames into a complete source document"""
        # Start with the prefix
        prefix = self.latex_prefix if hasattr(self, 'latex_prefix') else ""
        
        # Collect all frames in order
        frames = []
        for i in range(len(self.slides_outline)):
            if i in self.latex_dict:
                for frame in self.latex_dict[i]["frames"]:
                    frames.append(frame["full_frame"])
        
        # Add the suffix
        suffix = self.latex_suffix if hasattr(self, 'latex_suffix') else "\n\\end{document}"
        
        # Use utility function to compile
        return SlideUtils.compile_latex_document(prefix, frames, suffix)
    
    def _compile_slides_script(self) -> str:
        """Compile all slide scripts into a markdown document"""
        script_md = f"# Slides Script: {self.name}\n\n"
        
        for i in range(len(self.slides_outline)):
            if i in self.slides_script:
                script = self.slides_script[i]
                frame_count = script.get("frame_count", 1)
                script_md += f"## Section {script['slide_id']}: {script['title']}\n"
                if frame_count > 1:
                    script_md += f"*({frame_count} frames)*\n\n"
                else:
                    script_md += "\n"
                script_md += f"{script['script']}\n\n"
                script_md += "---\n\n"
        
        return script_md
    
    def _compile_assessment(self) -> str:
        """Compile all assessments into a markdown document"""
        assessment_md = f"# Assessment: {self.name}\n\n"
        
        for i in range(len(self.slides_outline)):
            if i in self.assessment_content:
                assessment = self.assessment_content[i]
                assessment_md += f"## Section {assessment['slide_id']}: {assessment['title']}\n\n"
                
                # Learning Objectives
                if assessment['assessment'].get('learning_objectives'):
                    assessment_md += "### Learning Objectives\n"
                    for obj in assessment['assessment']['learning_objectives']:
                        assessment_md += f"- {obj}\n"
                    assessment_md += "\n"
                
                # Questions
                if assessment['assessment'].get('questions'):
                    assessment_md += "### Assessment Questions\n\n"
                    for idx, q in enumerate(assessment['assessment']['questions'], 1):
                        assessment_md += f"**Question {idx}:** {q['question']}\n\n"
                        for option in q['options']:
                            assessment_md += f"  {option}\n"
                        assessment_md += f"\n**Correct Answer:** {q['correct_answer']}\n"
                        assessment_md += f"**Explanation:** {q['explanation']}\n\n"
                
                # Activities
                if assessment['assessment'].get('activities'):
                    assessment_md += "### Activities\n"
                    for activity in assessment['assessment']['activities']:
                        assessment_md += f"- {activity}\n"
                    assessment_md += "\n"
                
                # Discussion Questions
                if assessment['assessment'].get('discussion_questions'):
                    assessment_md += "### Discussion Questions\n"
                    for question in assessment['assessment']['discussion_questions']:
                        assessment_md += f"- {question}\n"
                    assessment_md += "\n"
                
                assessment_md += "---\n\n"
        
        return assessment_md
    