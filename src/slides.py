import os
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from src.agents import (
    LLM,
    Agent,
)


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

Use LaTeX features like:
- \\begin{{itemize}} for bullet points
- \\begin{{enumerate}} for numbered lists
- \\begin{{block}}{{Title}} for highlighted blocks
- \\begin{{lstlisting}} for code snippets
- \\begin{{equation}} for mathematical formulas
- \\includegraphics[width=0.55\\textwidth]{{/absolute/path/to/figure.png}} for figures from the textbook
- \\begin{{tabular}} for comparison tables from the textbook

PRESERVE FIGURES AND TABLES FROM THE DRAFT: if the Detailed Content above contains
a \\includegraphics{{...}} command pointing to a real file path, you MUST keep it
in the corresponding frame. Do NOT strip or replace it with prose. Same for any
\\begin{{tabular}} blocks. These come from the textbook's figure and table
extraction and are the only way the student sees the actual visual content.

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


_DEDUPE_PREFIX_WORDS = 40

# Visual-content markers (also enumerated on SlidesDeliberation; kept
# here as a module-level constant so the dedupe helper can recognise
# visual chunks without importing the class).
_VISUAL_CHUNK_MARKERS = ("[IMAGE_PATH:", "[LATEX:", "[TABLE:", "[ALGORITHM_STEPS:")


def _is_visual_chunk_text(text: str) -> bool:
    return any(m in text for m in _VISUAL_CHUNK_MARKERS)


# Canonical citation token shape — matches what Chunk.citation_token()
# emits. Anything that LOOKS like a citation (starts with the textbook
# id and ends with a closing bracket) but doesn't match this shape is
# considered malformed.
_CITATION_TOKEN_CANONICAL_RE = __import__("re").compile(
    r"\[([A-Za-z0-9_]+):([A-Za-z0-9._]+):p(\d+)\]"
)


# LaTeX cleanup: regexes used by _clean_latex_artifacts to catch
# common writer-side LaTeX bugs that break PDF conversion.
import re as _re_for_latex_cleanup

# Hallucinated placeholder paths in \includegraphics — the writer
# invented "/path/to/file.png" instead of using the real path from the
# [IMAGE_PATH:] marker. Strip the entire \includegraphics call line so
# the slide still compiles (figure absent rather than broken).
_FAKE_PATH_INCLUDEGRAPHICS_RE = _re_for_latex_cleanup.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{[^}]*(?:/path/to/|\.png\s*\.\.\.|\(your[^}]*)[^}]*\}\s*",
    _re_for_latex_cleanup.IGNORECASE,
)

# Citation tokens accidentally wrapped in \cite{}. The writer emitted
# \cite{han_data_mining_3e:ch1.s1:p01} (BibTeX syntax) which needs a
# bibliography file to compile. Rewrite to the canonical plain-bracket
# form [han_data_mining_3e:ch1.s1:p01].
_BIBTEX_WRAPPED_CITE_RE = _re_for_latex_cleanup.compile(
    r"\\cite\{([^}]+_data_mining_3e:ch\d+(?:\.s\d+)?:p\d+)\}"
)

# Unescaped ampersands in slide TEXT (not in tabular/align). Detect
# lines that contain "& " outside of \begin{tabular}/\begin{align}
# environments. Replace with "\&".
_TABULAR_OR_ALIGN_OPEN = _re_for_latex_cleanup.compile(
    r"\\begin\{(tabular|align|array|matrix|pmatrix|bmatrix)\}"
)
_TABULAR_OR_ALIGN_CLOSE = _re_for_latex_cleanup.compile(
    r"\\end\{(tabular|align|array|matrix|pmatrix|bmatrix)\}"
)


# Citation token escaping for use inside plain LaTeX text. We wrap each
# [textbook:section:page] token in \texttt{...} and escape the underscores
# so LaTeX doesn't treat them as subscript markers.
_CITATION_TOKEN_IN_TEXT_RE = _re_for_latex_cleanup.compile(
    r"(?<!\\texttt\{)\[([a-zA-Z][a-zA-Z0-9_]*:ch\d+(?:\.s\d+)?:p\d+(?:-p\d+)?)\]"
)

# \graphicspath declaration we want in every preamble so .grounding_cache/
# figure paths resolve from the project root regardless of where the
# slides.tex is compiled from. We probe a few common relative ancestors
# of the chapter directory; the absolute project root is intentionally
# omitted so generated slides are self-contained.
_GRAPHICSPATH_INSERT = r"\graphicspath{{./}{../}{../../}{../../../}}"

# VLM-extraction markers that leaked verbatim into the writer's output
# instead of being processed. The writer was supposed to consume
# [DESCRIPTION: ...] / [INSIGHT: ...] markers (as figure captions) and
# convert [IMAGE_PATH: ...] markers into \includegraphics calls. When it
# copy-pastes them as quoted text instead, they show up on the rendered
# slide as raw "[DESCRIPTION: The figure shows...]" — readable but ugly.
# Strip these so the slide narrates the surrounding text cleanly.
_VLM_MARKER_RE = _re_for_latex_cleanup.compile(
    r"\[(IMAGE_PATH|LATEX|TABLE|ALGORITHM_STEPS|DESCRIPTION|INSIGHT)\s*:"
    r"\s*([^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*)\]",
    _re_for_latex_cleanup.IGNORECASE,
)
# Defensive fallback: the writer sometimes emits an UNCLOSED VLM marker
# (e.g. ``[DESCRIPTION: text without the closing bracket"\texttt{...}``).
# The strict regex above requires the closing ``]`` and skips these.
# This fallback catches the opening marker and strips up to the next
# closing-quote-then-backslash sequence (``"\``) which is the most
# common boundary in writer output. Stops at end-of-line otherwise.
_VLM_MARKER_UNCLOSED_RE = _re_for_latex_cleanup.compile(
    r"\[(IMAGE_PATH|LATEX|TABLE|ALGORITHM_STEPS|DESCRIPTION|INSIGHT)\s*:"
    r"\s*[^\n]*?(?=\"\s*\\|\n)",
    _re_for_latex_cleanup.IGNORECASE,
)

# Markdown ** bold ** that the writer emitted into the .tex source. LaTeX
# would render this as raw asterisks. Convert to \textbf{...} so it gets
# proper bold formatting in the LaTeX output AND so downstream PPTX
# converters (which strip \textbf{} but read asterisks as literal text)
# don't show "**Data Types**" as visible noise.
_MARKDOWN_BOLD_IN_TEX_RE = _re_for_latex_cleanup.compile(
    r"\*\*([^*\n]+?)\*\*"
)

# Unicode characters the LaTeX default font (ec-lmss10) cannot render.
# Replace with LaTeX-native equivalents. Conservative: only swap unicode
# that frequently appears in writer output and reliably maps to ASCII
# alternatives — leaves complex unicode (Greek letters etc.) for the
# writer to render properly in math mode.
_UNICODE_REPLACEMENTS = {
    "—": "---",   # em-dash → ---
    "–": "--",    # en-dash → --
    "‘": "`",     # left single curly quote → backtick
    "’": "'",     # right single curly quote → apostrophe
    "“": "``",    # left double curly quote → ``
    "”": "''",    # right double curly quote → ''
    "…": "\\ldots{}",  # ellipsis → \ldots{}
}


def _escape_citation_token(match):
    """Helper: wrap a citation token in \\texttt{} so LaTeX
    treats the underscores and colons as monospaced inline text rather
    than math operators."""
    token = match.group(1)
    # Escape underscores so they print as underscores, not subscripts
    escaped = token.replace("_", r"\_")
    return r"\texttt{[" + escaped + r"]}"


def _clean_latex_artifacts(text):
    """LaTeX cleanup: scrub writer-side LaTeX bugs that
    break PDF conversion. Runs alongside _strip_malformed_citation_tokens
    on the final artifact text. Safe-by-default — only fixes
    well-characterized failure patterns; ambiguous edits left alone.

    Fixes:
      1. \\includegraphics{/path/to/file.png} (hallucinated path) →
         remove the entire \\includegraphics line so the slide still
         compiles.
      2. \\cite{han_data_mining_3e:ch1.s1:p01} → bare bracket form
         [han_data_mining_3e:ch1.s1:p01] (BibTeX → inline citation).
      3. Bare ampersands in slide text outside tabular/align → \\&.
      4. Unicode em-dash, en-dash, curly quotes, ellipsis →
         LaTeX-native ASCII equivalents (---, --, ``...'', \\ldots{})
         so the default beamer font (ec-lmss10) can render them.
      5. Citation tokens in plain text → \\texttt{[...]} with escaped
         underscores, so LaTeX doesn't parse the token as math.
         Tokens already inside \\texttt{} are not double-wrapped.
      6. Inject \\graphicspath{...} into the preamble (right after
         \\usepackage{graphicx}) so .grounding_cache/ paths resolve
         from the project root no matter where slides.tex is compiled.
    """
    if not text:
        return text
    # Fix 1: drop hallucinated includegraphics paths
    text = _FAKE_PATH_INCLUDEGRAPHICS_RE.sub("", text)
    # Fix 2: unwrap \cite{} BibTeX wrapping back to plain brackets
    text = _BIBTEX_WRAPPED_CITE_RE.sub(r"[\1]", text)
    # Fix 4a: strip VLM-extraction markers the writer should have processed
    # but copy-pasted as raw text instead. ([DESCRIPTION:], [INSIGHT:],
    # [IMAGE_PATH:], [LATEX:], [TABLE:], [ALGORITHM_STEPS:]) — all become
    # invisible so the surrounding narration reads cleanly.
    text = _VLM_MARKER_RE.sub("", text)
    # Fallback for unclosed markers that the strict regex skipped.
    text = _VLM_MARKER_UNCLOSED_RE.sub("", text)
    # Fix 4b: convert markdown **bold** the writer emitted into the LaTeX
    # body into proper \textbf{...}. The writer occasionally falls back
    # to markdown when it should use LaTeX; LaTeX itself ignores
    # asterisks and they leak as raw "**...**" to any downstream PPTX
    # or HTML render.
    text = _MARKDOWN_BOLD_IN_TEX_RE.sub(r"\\textbf{\1}", text)
    # Fix 4: replace problem unicode characters with LaTeX equivalents
    for src, dst in _UNICODE_REPLACEMENTS.items():
        if src in text:
            text = text.replace(src, dst)
    # Fix 5: wrap citation tokens in \texttt{} with escaped underscores
    text = _CITATION_TOKEN_IN_TEXT_RE.sub(_escape_citation_token, text)
    # Fix 6: inject \graphicspath into the preamble if missing
    if (r"\graphicspath" not in text
            and r"\usepackage{graphicx}" in text):
        text = text.replace(
            r"\usepackage{graphicx}",
            r"\usepackage{graphicx}" + "\n" + _GRAPHICSPATH_INSERT,
            1,
        )
    # Fix 3: escape ampersands outside tabular/align
    lines = text.split("\n")
    in_math_env = 0
    out_lines = []
    for line in lines:
        if _TABULAR_OR_ALIGN_OPEN.search(line):
            in_math_env += 1
        if in_math_env == 0:
            stripped = line.lstrip()
            if not stripped.startswith("%"):
                line = _re_for_latex_cleanup.sub(
                    r"(?<!\\)&", r"\\&", line,
                )
        if _TABULAR_OR_ALIGN_CLOSE.search(line):
            in_math_env = max(0, in_math_env - 1)
        out_lines.append(line)
    return "\n".join(out_lines)


def _strip_malformed_citation_tokens(text: str, textbook_id, valid_tokens=None):
    """Remove malformed citation-shaped tokens from generated text.

    Detects bracketed tokens that START with the configured
    ``textbook_id`` followed by ``:`` but FAIL to match the canonical
    citation shape (textbook_id : section_id : p<page>). Common cases:

      * ``[han_data_mining_3e:c]`` — section truncated mid-word
      * ``[han_data_mining_3e]`` — section + page missing
      * ``[han_data_mining_3e:ch1.s1]`` — page missing
      * ``[han_data_mining_3e:ch99.s99:p01]`` — well-formed but the
        section/page combination doesn't resolve to any chunk in the
        knowledge base. When ``valid_tokens`` is supplied (a set of
        every token the KB recognises), well-formed tokens that
        aren't in the set are stripped too. Without this guard the
        verifier counts them as ``malformed``.

    These would otherwise be counted as ``malformed`` by the verifier
    and inflate the failure-mode bucket. Stripping them at write-time
    leaves the surrounding claim text intact and lets the verifier
    score only the well-formed citations the writer produced.

    When ``textbook_id`` is None / empty (vanilla path) this is a
    no-op — vanilla artifacts contain no citation tokens at all.
    """
    if not textbook_id or not text:
        return text
    import re as _re
    # Match any bracketed token starting with the textbook_id (the prefix
    # has to be followed by either ":" or "]" so we don't accidentally
    # match a substring of a different identifier).
    suspect_re = _re.compile(
        r"\[" + _re.escape(textbook_id) + r"(?::[^\]]*)?\]"
    )
    out_parts = []
    last = 0
    for m in suspect_re.finditer(text):
        tok = m.group(0)
        if _CITATION_TOKEN_CANONICAL_RE.fullmatch(tok):
            # Well-formed; check it actually resolves to a real KB chunk
            # when caller supplied the valid-token set.
            if valid_tokens is None or tok in valid_tokens:
                continue  # leave it alone
            # Else: well-formed but unresolvable → strip it (treated
            # the same as a syntactically broken token).
        # Malformed (syntactic) or unresolvable (semantic):
        # keep everything up to this token, drop the token.
        out_parts.append(text[last:m.start()])
        last = m.end()
        # Also collapse one preceding space if it was attached to the
        # token (e.g. "word [bad_tok]" → "word" not "word ").
        if out_parts and out_parts[-1].endswith(" "):
            out_parts[-1] = out_parts[-1][:-1]
    out_parts.append(text[last:])
    if last == 0:
        return text  # no malformed found; return original
    return "".join(out_parts)


def _dedupe_results(results):
    """Drop later results whose chunk overlaps a kept earlier chunk.

    Two retrieval results are considered duplicates if EITHER:
      * their full text matches byte-for-byte (rare but possible when
        two chunks happen to be identical), OR
      * their first :data:`_DEDUPE_PREFIX_WORDS` words match the first
        ``_DEDUPE_PREFIX_WORDS`` words of an already-kept chunk
        (catches the common case where chunk N+1 starts with the last
        ~64 tokens of chunk N due to OVERLAP_TOKENS).

    Preserves the retriever's rank order — first occurrence of each
    cluster is kept, later occurrences are dropped. Returns the
    filtered list; never raises.
    """
    if not results:
        return results
    kept = []
    seen_full: set[str] = set()
    seen_prefix: set[str] = set()
    for r in results:
        chunk = r.chunk
        text = chunk.text or ""
        # Visual chunks (those carrying hybrid-ingester markers like
        # [IMAGE_PATH:, [LATEX:, [TABLE:, [ALGORITHM_STEPS:) are
        # exempt from dedup against PROSE chunks: their content role
        # is distinct, they're tiny (50-150 tokens), and silently
        # losing one to dedup against a coincidentally-prefix-matching
        # prose chunk drops a visual-content delivery slot. They CAN
        # still dedup against other visual chunks of the same kind.
        is_visual = _is_visual_chunk_text(text)
        prefix = " ".join(text.split()[:_DEDUPE_PREFIX_WORDS])
        if is_visual:
            # Visual chunks dedup only on byte-identical text — full
            # equality across two visual chunks is the only realistic
            # collision (e.g. a figure caption repeated).
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
                 citation_usage_tracker=None,
                 semantic_gate=None,
                 write_time_verifier=None,
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
        # Diversity cap. When set, retrieval results whose chunks have
        # already been cited cap-many times across the run are dropped
        # from the evidence block, forcing the writer onto fresh chunks.
        # Vanilla path leaves this None and behavior is byte-identical.
        self.citation_usage_tracker = citation_usage_tracker
        # Gate A + Gate B: claim-chunk similarity filter. When set,
        # Gate A pre-filters retrieval results before evidence block
        # construction; Gate B post-filters citation tokens after the
        # writer commits. Vanilla path leaves this None.
        self.semantic_gate = semantic_gate
        # LLM write-time citation verifier. Per-citation YES/NO check
        # after Gate B (semantic) catches the obvious cases for free.
        # Runs LAST in the strip chain.
        self.write_time_verifier = write_time_verifier
        # Per-chapter top_k tuned by the density of chunks in the
        # chapter's bound sections. Dense chapters (many candidate
        # chunks) get a wider window so the LLM sees more options;
        # thin chapters narrow down to avoid pulling tangential
        # content into evidence.
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
    # Word budget for the injected evidence block. Stays well under
    # gpt-4o-mini's 128k context window after the rest of the prompt.
    _EVIDENCE_WORD_BUDGET = 1800   # bumped from 1500 — more evidence room
    _EVIDENCE_TOP_K = 6            # default; per-chapter tuning may override
    _EVIDENCE_TOP_K_MIN = 5        # floor for thin chapters
    _EVIDENCE_TOP_K_MAX = 12       # ceiling — beyond this hits the word budget
    _CHUNKS_PER_TOP_K_STEP = 12    # ~12 chunks of density per top_k step
    _EXAMPLE_SNIPPET_WORDS = 22    # how much of the top excerpt to mirror as the worked example

    # Artifact-type vocabulary for `_build_evidence_block`. The strict
    # rule-set ("slide") applies to slides + assessments — both are
    # READ documents where inline citations don't disrupt the reader.
    # The relaxed rule-set ("script") applies to speaker scripts —
    # SPOKEN narration where back-to-back inline citations and
    # mandatory direct quotation break narrative flow. An earlier
    # uplift re-eval showed slide_scripts:alignment + :coherence
    # dropping monotonically across baselines (-0.66 vs vanilla on each)
    # while the same metrics held / improved on slides + assessments —
    # the differentiated rule-set is the structural fix.
    _ARTIFACT_TYPES = ("slide", "script", "assessment")

    # Inline markers carried by chunks that came through the hybrid
    # ingester's VLM augmentation phase. When any of these appear in
    # the evidence text, _build_evidence_block adds
    # an extra rule block instructing the LLM how to consume them —
    # reproducing equations as LaTeX, including saved figure images
    # via includegraphics, and rendering tables / algorithms in
    # appropriate form for the artifact.
    _VISUAL_MARKERS = ("[IMAGE_PATH:", "[LATEX:", "[TABLE:",
                       "[ALGORITHM_STEPS:", "[DESCRIPTION:", "[INSIGHT:")

    def _compute_top_k_for_chapter(self) -> int:
        """Tune the retriever top_k by the density of bound chunks.

        Returns ``_EVIDENCE_TOP_K`` (the default) when the retriever
        is absent, no sections are bound, or the KB chunks attribute
        is unavailable. Otherwise counts how many chunks belong to
        sections in ``self.section_ids`` and scales: roughly
        ``round(chunks / _CHUNKS_PER_TOP_K_STEP)``, clamped to
        ``[_EVIDENCE_TOP_K_MIN, _EVIDENCE_TOP_K_MAX]``.
        """
        if self.retriever is None or not self.section_ids:
            return self._EVIDENCE_TOP_K
        try:
            kb_chunks = self.retriever.kb.chunks
        except AttributeError:
            return self._EVIDENCE_TOP_K
        bound = sum(
            1 for c in kb_chunks if c.section_id in self.section_ids
        )
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

        Returns ``(evidence_block, citation_rules)`` — both empty strings
        when ``self.retriever is None`` (vanilla path) or retrieval yielded
        nothing in scope. ``evidence_block`` is a chunk of plain text the
        caller prepends to its prompt; ``citation_rules`` is an instruction
        the caller appends.

        ``artifact`` is one of ``"slide" | "script" | "assessment"``; it
        toggles rules 1 + 2 between strict (slide/assessment — cite every
        claim, anchor exactly) and relaxed (script — cite each concept
        once at sentence end, paraphrase naturally). Rules 3 / 4 / 5
        (abstain, exact tokens, cite-correct-excerpt) are universal and
        identical across artifacts.

        Design notes (faithfulness uplift over the prior format):
          * Structured per-excerpt headers (TOKEN / SOURCE / PAGE / PASSAGE)
            give the LLM clear labels to anchor on, vs a flat token+text.
          * Five numbered rules covering the three failure modes the
            verifier surfaced (hallucination, wrong-cite, loose paraphrase),
            plus an abstain rule for unsupported claims.
          * The worked example mirrors a real snippet from the TOP retrieved
            chunk so the LLM has a literal pattern to imitate — not a
            generic placeholder.
          * Script mode (2026-05-27 fix) softens RULE 1 + RULE 2 so
            spoken narration doesn't get peppered with sentence-interrupting
            citation tokens and broken-voice direct quotes.
        """
        if self.retriever is None:
            return "", ""
        if artifact not in self._ARTIFACT_TYPES:
            # Defensive: an unknown artifact label silently falls back to
            # the strict rule-set rather than crashing — prefer over-citing
            # to under-citing if the call site is mis-wired.
            artifact = "slide"
        try:
            # `_evidence_top_k` is set in __init__; defensive fallback
            # to the class default lets bypass-init test skeletons work.
            # Three ways to filter the retrieval result:
            #   * cross_chapter=True (Lever E) — full-KB search; ignore
            #     both the chapter binding and any narrowed pick.
            #   * section_ids_override is a list — Lever D narrowed pick.
            #   * neither — chapter-wide self.section_ids binding.
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
            # Defense-in-depth cost protection: if retrieval has failed
            # the same way many times in a row, the run is no longer
            # producing grounded output but is still spending money on
            # writer + verifier calls. Abort cleanly rather than letting
            # the loop drift indefinitely. Threshold is intentionally
            # generous (allows real transient blips like brief rate
            # limits) but short enough to catch genuinely-broken
            # retrieval before it racks up cost.
            cls = type(self)
            count_attr = "_consecutive_retrieval_failures"
            last_attr = "_last_retrieval_error_type"
            err_type = type(e).__name__
            prev_err = getattr(cls, last_attr, None)
            if prev_err == err_type:
                setattr(cls, count_attr, getattr(cls, count_attr, 0) + 1)
            else:
                setattr(cls, count_attr, 1)
                setattr(cls, last_attr, err_type)
            n = getattr(cls, count_attr, 0)
            print(f"[grounding] retrieval failed ({e}); falling back to vanilla prompt "
                  f"(consecutive {err_type} failures: {n})")
            if n >= 10:
                raise RuntimeError(
                    f"Grounding retrieval failed {n} times in a row with the "
                    f"same error class ({err_type}). Aborting run to prevent "
                    f"further cost (writer + verifier calls keep running even "
                    f"though no grounded evidence is reaching the prompt). "
                    f"Last error: {e!r}"
                )
            return "", ""
        # Successful retrieval — reset the consecutive-failure counter so
        # transient blips earlier in the run don't accumulate spuriously.
        cls = type(self)
        setattr(cls, "_consecutive_retrieval_failures", 0)
        setattr(cls, "_last_retrieval_error_type", None)
        if not results:
            return "", ""

        # Deduplicate near-identical chunks before showing to the LLM.
        # The chunker emits OVERLAP_TOKENS of overlap between adjacent
        # prose chunks, so the retriever can occasionally rank two
        # neighboring chunks both in the top-K. Without dedup the LLM
        # sees redundant content and may cite the wrong instance
        # (manifests as `wrong_chunk_cited` or `loose_paraphrase` in the
        # verifier). We drop later occurrences of any chunk whose text
        # is byte-for-byte equal to an earlier kept chunk OR whose first
        # ~40 words match an earlier kept chunk (catches the overlap
        # case where the start of chunk N+1 equals the end of chunk N).
        results = _dedupe_results(results)

        # Coverage diversification — for chapter-level retrieval (not
        # per-slide), ensure top-k spans at least 3 distinct sections
        # when possible. Counters the pattern where chapter-level
        # evidence over-concentrated on one section, locking the writer
        # onto a narrow textbook slice for the entire chapter's slide
        # drafts. Only fires for chapter-level calls
        # (section_ids_override is None and not cross_chapter).
        if (section_ids_override is None and not cross_chapter
                and len(results) >= 4):
            distinct_sections = {r.chunk.section_id for r in results}
            if len(distinct_sections) < 3:
                # Diversify: keep results sorted by rank but ensure
                # at least 3 distinct sections in top-6. Demote
                # later same-section results below first-section-
                # appearance of new sections.
                seen_sections = set()
                diverse = []
                deferred = []
                for r in results:
                    sid = r.chunk.section_id
                    if sid not in seen_sections:
                        diverse.append(r)
                        seen_sections.add(sid)
                    else:
                        deferred.append(r)
                results = diverse + deferred

        # Gate A — pre-evidence semantic filter: drop results whose
        # chunk text scores below the claim-chunk similarity threshold.
        # Sentence-transformer cosine ($0, CPU). When the gate is None
        # or encoder load failed, this is a no-op.
        gate = getattr(self, "semantic_gate", None)
        if gate is not None:
            results = gate.gate_a_filter_results(query, results)

        # Diversity cap: drop results whose chunk has already been
        # cited cap-many times across the run. When the tracker is None
        # (vanilla path) this is a no-op. Defensive ``getattr`` lets
        # bypass-init test skeletons skip the wiring.
        tracker = getattr(self, "citation_usage_tracker", None)
        if tracker is not None:
            results = [r for r in results if not tracker.is_over_cap(r.chunk)]
            if not results:
                # All candidates were over cap — fall through to vanilla
                # behavior rather than emitting an empty evidence block.
                return "", ""

        # Guarantee visual chunk inclusion for slide / assessment
        # artifacts. An earlier baseline lost 9 of 11 \includegraphics
        # tokens: the forensic replay traced it to visual chunks being
        # crowded out of the top-k by prose chunks that ranked higher.
        # This pass scans the bound section_ids for any visual-marker
        # chunks and ensures at least one reaches the writer by
        # replacing the lowest-ranked prose chunk if needed. Script
        # artifacts skip this (they don't
        # render figures, they narrate them).
        if artifact != "script":
            results = self._inject_visual_chunk_if_available(
                results, effective_section_ids,
            )

        # Build per-excerpt blocks with structured headers. Budget the
        # total word count across all excerpts; truncate the last one if
        # it would overflow.
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
            chapter_title = (getattr(r.chunk, "chapter_title", "") or "").strip()
            section_title = (getattr(r.chunk, "section_title", "") or "").strip()
            source_line = " / ".join(s for s in (chapter_title, section_title) if s) or "(untitled)"
            # Show the page RANGE for multi-page chunks so the LLM can
            # cite the most relevant page within the chunk's span (the
            # verifier index registers every page in the range, so any
            # page-in-range token resolves to this chunk).
            try:
                page_label = r.chunk.page_range_label()
            except AttributeError:
                page_label = f"p{r.chunk.page_start}"
            block = (
                f"━━ EXCERPT {idx} of {len(results)} "
                f"{'━' * max(0, 50 - len(str(idx)) - len(str(len(results))))}\n"
                f"  TOKEN   : {r.chunk.citation_token()}\n"
                f"  SOURCE  : {source_line}\n"
                f"  PAGE    : {page_label}\n"
                f"  PASSAGE :\n"
                f"  «{text}»"
            )
            blocks.append(block)
            budget -= len(text.split())
            if budget <= 0:
                break

        first_token = results[0].chunk.citation_token()
        # Mirror a short snippet of the top excerpt as the worked example —
        # gives the model a literal in-context pattern to imitate rather
        # than a generic placeholder sentence.
        snippet_words = results[0].chunk.text.split()[: self._EXAMPLE_SNIPPET_WORDS]
        example_snippet = " ".join(snippet_words).rstrip(",.;:") + "…"

        # Artifact-conditioned RULES 1 + 2. RULES 3, 4, 5 are universal.
        if artifact == "script":
            rule_1 = (
                "  RULE 1 (CITE EACH CONCEPT, NOT EACH SENTENCE). This is a "
                "SPOKEN SCRIPT, not a written document. Cite the textbook ONCE "
                "per major concept, placed at a natural sentence boundary so "
                "it does not interrupt narrative flow. Avoid back-to-back "
                f"citations. Format: \"...nearest-mean assignment {first_token}.\"\n"
                "  — not \"...nearest-mean {first_token} assignment...\""
            )
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
            footer_intro = (
                "GROUNDING REMINDER (apply while writing this spoken script):"
            )
            footer_rule_1 = (
                f"  • Each major concept gets ONE citation token (e.g. "
                f"{first_token}), placed at a natural sentence boundary."
            )
            footer_rule_2 = (
                "  • Paraphrase naturally in the speaker's voice — direct "
                "quotation only when technical precision demands it."
            )
        else:  # "slide" or "assessment"
            rule_1 = (
                "  RULE 1 (CITE EVERY SOURCED CLAIM). Every factual claim drawn "
                "from an excerpt MUST end with that excerpt's citation token, "
                f"exactly as printed in its header (e.g. {first_token})."
            )
            rule_2 = (
                "  RULE 2 (ANCHOR-THEN-PARAPHRASE — slot-fill template). "
                "For any factual claim — including definitions, formulas, "
                "named concepts, and procedure descriptions — your sentence "
                "MUST follow this exact 3-part structure:\n"
                "       <<verbatim phrase from excerpt>> [citation token] — "
                "<<your one-sentence elaboration, if any>>\n"
                "  \n"
                "  HARD CONSTRAINTS:\n"
                "    (a) <<verbatim phrase>> is a 6-25 word slice copied "
                "letter-for-letter from one of the excerpts above. Do NOT "
                "paraphrase the slice; do NOT add words inside it. Use the "
                "textbook's EXACT WORDING in double quotes.\n"
                "    (b) The citation token comes IMMEDIATELY after the "
                "closing quote, exactly as printed in the excerpt's TOKEN "
                "header.\n"
                "    (c) Your elaboration adds NO NEW FACTS — only "
                "explanation, paraphrase, or example. If you can't elaborate "
                "without inventing facts, leave the elaboration off.\n"
                "    (d) For definitions and formulas, the verbatim quote is "
                "MANDATORY. Loose paraphrase + citation alone will be flagged "
                "as wrong-section-named by the verifier."
            )
            header_label = "TEXTBOOK GROUNDING — MANDATORY RULES"
            footer_intro = "GROUNDING REMINDER (apply while writing):"
            footer_rule_1 = (
                f"  • Every textbook-derived claim ends with its citation token "
                f"(e.g. {first_token})."
            )
            footer_rule_2 = (
                "  • Prefer textbook wording over paraphrase, especially for "
                "definitions and formulas — use \"direct quotes\" where appropriate."
            )

        evidence_block = (
            "════════════════════════════════════════════════════════════════════\n"
            f"{header_label}\n"
            "════════════════════════════════════════════════════════════════════\n\n"
            f"You have {len(blocks)} excerpts from the textbook below. They are your "
            "AUTHORITATIVE source for this topic. Follow these rules without "
            "exception:\n\n"
            + rule_1 + "\n\n"
            + rule_2 + "\n\n"
            "  RULE 3 (ABSTAIN IF UNSUPPORTED). If you cannot ground a claim in "
            "ANY excerpt below, either drop the claim or restate what the textbook "
            "DOES cover on that topic. Do NOT make textbook-attributed claims that "
            "the excerpts do not support.\n\n"
            "  RULE 4 (EXACT TOKENS ONLY). Each citation token must appear EXACTLY "
            "as printed in the excerpt header — no truncation, no modification, "
            "never invented. A token like \"[han_data_mining_3e:c]\" is wrong and "
            "will be flagged.\n\n"
            "  RULE 5 (CITE THE CORRECT EXCERPT). If a claim is supported by "
            "Excerpt 2, cite Excerpt 2's token — not Excerpt 1's. The cited "
            "excerpt must be the one that actually supports the claim.\n\n"
            "Example of a well-formed claim drawn from Excerpt 1:\n"
            f"  \"{example_snippet}\" {first_token}\n\n"
            "═══════════════════════════ EXCERPTS ═══════════════════════════\n\n"
            + "\n\n".join(blocks)
            + "\n\n"
            "════════════════════════════════════════════════════════════════════\n"
        )
        citation_rules = (
            "\n" + footer_intro + "\n"
            + footer_rule_1 + "\n"
            + footer_rule_2 + "\n"
            "  • If you can't find support for a claim in the excerpts above, "
            "do NOT make that claim. State what the textbook covers instead.\n"
            "  • Citation tokens must appear EXACTLY as in the excerpt headers. "
            "Never truncate, modify, or invent tokens.\n"
            "  • Cite the excerpt that actually supports the claim — not "
            "whichever token you happen to remember.\n"
            "  • Any special LaTeX characters from excerpts (& % $ # _ { } ~ ^) "
            "must be escaped in LaTeX output (e.g. \\& \\% \\_).\n"
        )

        # ---- Visual-content rules: only added when the evidence
        # ---- actually contains hybrid-ingester markers. Vanilla
        # ---- chunks contain none of these, so the rules block is empty
        # ---- and the prompt is byte-identical to the prior behavior.
        joined_text = "\n".join(blocks)
        visual_rules = self._build_visual_content_rules(joined_text, artifact)
        if visual_rules:
            evidence_block = evidence_block + visual_rules

        return evidence_block, citation_rules

    def _record_emitted_citations(self, text) -> None:
        """Scan an LLM output for emitted citation tokens and bump the
        diversity-cap counter. No-op on vanilla path (tracker is None)
        or when text is empty. Defensive ``getattr`` lets bypass-init
        test skeletons skip the wiring."""
        tracker = getattr(self, "citation_usage_tracker", None)
        if tracker is None or not text:
            return
        tracker.scan_and_increment(text)

    # Per-slide section binding.
    _PER_SLIDE_TOP_SECTIONS = 2
    _PER_SLIDE_RETRIEVE_K = 8
    _PER_SLIDE_RRF_K = 60

    def _pick_per_slide_sections(self, slide_query: str):
        """Narrow the chapter's bound section_ids to the top-K sections
        for THIS specific slide's query. Returns None when no retriever
        or no chapter binding (vanilla path) — caller keeps the
        chapter-wide filter. A short retrieval pass within the chapter's
        bound sections picks the best per-slide subset.
        """
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
        section_scores: dict[str, float] = defaultdict(float)
        for rank, r in enumerate(results):
            sid = r.chunk.section_id
            section_scores[sid] += 1.0 / (self._PER_SLIDE_RRF_K + rank)
        ranked = sorted(section_scores.items(), key=lambda kv: -kv[1])
        return [sid for sid, _ in ranked[:self._PER_SLIDE_TOP_SECTIONS]]

    def _build_per_slide_evidence(self, slide_query: str, artifact: str = "slide") -> tuple:
        """Wrapper: narrow the section filter to this slide's
        best-matched sections before building the evidence block. Falls
        back to chapter-wide retrieval when no narrowing is possible
        (vanilla path or thin chapter)."""
        per_slide = self._pick_per_slide_sections(slide_query)
        return self._build_evidence_block(
            slide_query, artifact=artifact, section_ids_override=per_slide,
        )

    def _inject_visual_chunk_if_available(self, results, section_ids):
        """Guarantee at least one visual chunk surfaces in the evidence
        block when one exists in scope. Looks for a chunk carrying a
        visual marker (IMAGE_PATH/LATEX/TABLE/ALGORITHM) within the
        bound section_ids. If results already contain a visual chunk,
        returns ``results`` unchanged. Otherwise replaces the
        LOWEST-ranked prose chunk with a visual chunk from scope.
        """
        if not results:
            return results
        retriever = self.retriever
        if retriever is None:
            return results
        # Already have a visual chunk? Done.
        for r in results:
            if any(m in r.chunk.text for m in self._VISUAL_MARKERS):
                return results
        # Search the KB for an in-scope visual chunk
        try:
            kb_chunks = retriever.kb.chunks
        except AttributeError:
            return results
        wanted_sections = (
            set(section_ids) if section_ids is not None
            else {c.section_id for c in kb_chunks}
        )
        # Pick the first visual chunk in scope (prefer the same section
        # as the top result so the figure aligns with the topic)
        top_section = results[0].chunk.section_id if results else None
        preferred = [
            c for c in kb_chunks
            if c.section_id == top_section
            and any(m in c.text for m in self._VISUAL_MARKERS)
        ]
        any_in_scope = [
            c for c in kb_chunks
            if c.section_id in wanted_sections
            and any(m in c.text for m in self._VISUAL_MARKERS)
        ]
        visual_chunk = preferred[0] if preferred else (
            any_in_scope[0] if any_in_scope else None
        )
        if visual_chunk is None:
            return results
        # Build a ScoredChunk-like wrapper carrying the visual chunk
        from dataclasses import dataclass
        @dataclass
        class _VisualInjected:
            chunk: object
        injected = _VisualInjected(chunk=visual_chunk)
        # Hoist the visual chunk to the FRONT of results, replacing the
        # lowest-ranked prose chunk. The block-building loop downstream
        # consumes a fixed word budget (~1800) per chunk in rank order;
        # large prose chunks in math-heavy chapters can exhaust the
        # budget in 4-5 iterations. Appending the visual chunk to the
        # tail meant its IMAGE_PATH/LATEX/TABLE markers never reached
        # the writer's evidence_text, and the visual-content rule block
        # never engaged — producing zero \includegraphics in the slides
        # despite the VLM having extracted a real figure for the page.
        # Putting the visual chunk first guarantees its marker survives
        # into evidence_text even when later prose chunks get truncated
        # or skipped.
        return [injected] + list(results[:-1])

    def _build_visual_content_rules(self, evidence_text: str, artifact: str) -> str:
        """Return an extra rule block for hybrid-ingester visual markers.

        Detects which visual markers are present in the evidence
        excerpts and emits artifact-specific instructions telling the
        LLM how to consume each. Returns an empty string when no
        markers are present (vanilla path) so the rules block is fully
        opt-in.

        Markers and their artifact-conditioned handling:

        ``[IMAGE_PATH: ...]``  (figure_cap chunks)
            slide / assessment → include via ``\\includegraphics``.
            script → describe the figure verbally using the adjacent
            ``[DESCRIPTION: ...]`` / ``[INSIGHT: ...]`` markers.

        ``[LATEX: ...]``  (equation chunks)
            slide / assessment → render as display math via ``\\[ ... \\]``.
            script → describe the formula in plain English using the
            adjacent ``[DESCRIPTION: ...]`` marker; do NOT speak raw
            LaTeX aloud.

        ``[TABLE: ...]``  (table chunks)
            slide / assessment → render as a LaTeX ``tabular``.
            script → narrate the key rows verbally.

        ``[ALGORITHM_STEPS: ...]``  (algorithm chunks)
            slide / assessment → render as an enumerated list (or
            ``algorithm2e`` block if the slide deck supports it).
            script → narrate the steps in order.
        """
        present = {m for m in self._VISUAL_MARKERS if m in evidence_text}
        if not present:
            return ""

        rule_lines = [
            "\n",
            "═══════════════════════════ VISUAL CONTENT RULES ═══════════════════════════",
            "Some excerpts above carry inline markers from hybrid PDF extraction.",
            "Consume them as follows for THIS artifact.",
            "**MANDATORY — these are not optional; failure to follow them is a defect.**",
        ]

        if "[IMAGE_PATH:" in present:
            if artifact in ("slide", "assessment"):
                rule_lines.append(
                    "  • [IMAGE_PATH: /path/to/file.png] → **MANDATORY**: include "
                    "the figure on the slide via "
                    "\\includegraphics[width=0.55\\textwidth]{/path/...}. "
                    "Use the EXACT path from the marker. Place it centered or "
                    "in a column layout next to descriptive bullets. Do NOT "
                    "tell the student to 'see the textbook' — the actual image "
                    "is included via the path. A slide whose evidence carries an "
                    "[IMAGE_PATH:] marker and emits NO \\includegraphics is a "
                    "defect that the verifier will flag."
                )
            else:  # script
                rule_lines.append(
                    "  • [IMAGE_PATH: ...] → the figure appears in the slide. "
                    "Narrate what the student is looking at, using the adjacent "
                    "[DESCRIPTION: ...] and [INSIGHT: ...] markers as the basis "
                    "for the verbal description."
                )

        if "[LATEX:" in present:
            if artifact in ("slide", "assessment"):
                rule_lines.append(
                    "  • [LATEX: ...] → render the formula on the slide via "
                    "display math \\[ ... \\]. Use the LaTeX EXACTLY as given. "
                    "Do NOT paraphrase the formula in words instead of "
                    "rendering it — the LaTeX is your source of truth."
                )
            else:
                rule_lines.append(
                    "  • [LATEX: ...] → describe the formula in plain English "
                    "using the adjacent [DESCRIPTION: ...] marker. Do NOT "
                    "speak raw LaTeX aloud (the listener can't see backslashes)."
                )

        if "[TABLE:" in present:
            if artifact in ("slide", "assessment"):
                rule_lines.append(
                    "  • [TABLE: ...] → render as a LaTeX \\begin{tabular} on "
                    "the slide. Headers in bold, rows in order. Use \\toprule, "
                    "\\midrule, \\bottomrule for clean separation."
                )
            else:
                rule_lines.append(
                    "  • [TABLE: ...] → narrate the key rows verbally; do not "
                    "read every cell aloud."
                )

        if "[ALGORITHM_STEPS:" in present:
            if artifact in ("slide", "assessment"):
                rule_lines.append(
                    "  • [ALGORITHM_STEPS: ...] → render as a LaTeX "
                    "enumerated list on the slide, preserving step numbering."
                )
            else:
                rule_lines.append(
                    "  • [ALGORITHM_STEPS: ...] → narrate the steps in order, "
                    "in plain language."
                )

        if "[DESCRIPTION:" in present or "[INSIGHT:" in present:
            rule_lines.append(
                "  • [DESCRIPTION: ...] and [INSIGHT: ...] markers provide the "
                "pedagogical content. Use the description for WHAT a figure / "
                "equation / table shows, and the insight for WHY it matters."
            )

        rule_lines.append(
            "═════════════════════════════════════════════════════════════════════════════\n"
        )
        return "\n" + "\n".join(rule_lines)

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
        
        # Step 7: Compile final slides script
        slides_script_md = self._compile_slides_script()
        
        # Step 8: Compile final assessment
        assessment_md = self._compile_assessment()
        
        # Save the results
        latex_path = os.path.join(self.output_dir, f"slides.tex")
        script_path = os.path.join(self.output_dir, f"script.md")
        assessment_path = os.path.join(self.output_dir, f"assessment.md")

        os.makedirs(self.output_dir, exist_ok=True)
        # Build the set of EVERY citation token the KB recognises so
        # the stripper can drop well-formed-but-non-resolving tokens
        # the writer occasionally hallucinates (e.g. plausible-looking
        # [han_data_mining_3e:ch99.s99:p01] that doesn't exist).
        valid_tokens = None
        if self.retriever is not None:
            try:
                kb_chunks = self.retriever.kb.chunks
                valid_tokens = set()
                for c in kb_chunks:
                    try:
                        valid_tokens.update(c.citation_tokens_in_range())
                    except AttributeError:
                        valid_tokens.add(c.citation_token())
            except Exception as e:
                print(f"[grounding] Could not build valid-token set "
                      f"({type(e).__name__}: {e}); skipping KB-existence check.")
                valid_tokens = None
        # Strip malformed citation-shaped tokens before saving so the
        # downstream verifier doesn't waste judge calls on truncated
        # tokens like "[textbook_id:c]" or "[textbook_id]". The LLM's
        # claim text stays; only the broken token is removed.
        latex_source = _strip_malformed_citation_tokens(
            latex_source, self.textbook_id, valid_tokens=valid_tokens,
        )
        slides_script_md = _strip_malformed_citation_tokens(
            slides_script_md, self.textbook_id, valid_tokens=valid_tokens,
        )
        assessment_md = _strip_malformed_citation_tokens(
            assessment_md, self.textbook_id, valid_tokens=valid_tokens,
        )
        # LaTeX cleanup pass — fixes hallucinated \includegraphics
        # paths, BibTeX-wrapped citations, and ampersand-escape bugs
        # that broke PDF compilation in earlier baselines. Only affects
        # LaTeX output (slides.tex); markdown unchanged.
        latex_source = _clean_latex_artifacts(latex_source)

        # Gate B — post-emit semantic strip. For each citation token
        # remaining in the final artifacts, computes claim-chunk
        # similarity and strips tokens below the gentle threshold (0.30).
        # Catches "wrong-section-named" cites the writer committed to
        # despite Gate A's pre-filter — different signal than the
        # diversity cap and the malformed-token strip.
        gate = getattr(self, "semantic_gate", None)
        if gate is not None:
            latex_source = gate.gate_b_strip_low_similarity(latex_source)
            slides_script_md = gate.gate_b_strip_low_similarity(slides_script_md)
            assessment_md = gate.gate_b_strip_low_similarity(assessment_md)

        # LLM write-time verifier. Runs LAST after malformed strip +
        # Gate B semantic strip have caught the cheap-to-detect cases.
        # For each remaining citation, asks gpt-4o-mini "does this
        # excerpt support this claim? YES/NO" and strips on NO.
        # Cost: ~$0.0001/cite × ~1000 surviving cites ≈ $0.10-0.15/run.
        verifier = getattr(self, "write_time_verifier", None)
        if verifier is not None:
            print(f"[grounding] running write-time verifier on final artifacts...")
            latex_source = verifier.strip_unsupported(latex_source)
            slides_script_md = verifier.strip_unsupported(slides_script_md)
            assessment_md = verifier.strip_unsupported(assessment_md)
            print(f"[grounding] {verifier.report()}")
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
        self._record_emitted_citations(response)
        
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

        # Textbook grounding (no-op when self.retriever is None).
        evidence_block, citation_rules = self._build_evidence_block(
            f"{chapter['title']}. {chapter.get('description', '')}"
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

        Your response should be LaTeX code that can be compiled directly.
        """
        
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
        self._record_emitted_citations(response)
        
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

        # Textbook grounding: use the outline as the query so script lines
        # can be supported by the textbook excerpts. Script artifact uses
        # the SOFTER rule-set (cite-each-concept-once, paraphrase-naturally)
        # since this is spoken narration where inline citations break flow.
        outline_query = " ".join(
            s.get("title", "") for s in self.slides_outline
        ) if self.slides_outline else ""
        evidence_block, citation_rules = self._build_evidence_block(
            outline_query, artifact="script"
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

        Your response must be valid JSON that can be parsed programmatically.
        """
        
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
        self._record_emitted_citations(response)
        
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
        
        # Assessments draw on cross-chapter context (review questions
        # span the syllabus). Use the full KB instead of the chapter's
        # bound section_ids. No-op when off.
        evidence_block, citation_rules = self._build_evidence_block(
            f"{chapter['title']}. {chapter.get('description', '')}",
            artifact="assessment",
            cross_chapter=True,
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

        Your response must be valid JSON that can be parsed programmatically.
        """
        
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
        self._record_emitted_citations(response)
        
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

        # Grounding: per-slide retrieval narrowed to the slide's
        # best-matched sections within the chapter binding (no-op when
        # self.retriever is None — vanilla path).
        evidence_block, citation_rules = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

        Focus on making the content educational, engaging, and aligned with the chapter's learning objectives.
        Note: Your output length needs to be kept within a reasonable range so that it can fit on a single PPT slide.
        """

        teaching_faculty.reset_history()
        print(f"Generating detailed content for slide: {slide['title']}...")
        response, elapsed_time, token_usage = teaching_faculty.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        self.time_slides += elapsed_time
        self.token_slides += token_usage
        self._record_emitted_citations(response)

        return response

    def _generate_slide_latex(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate LaTeX code for a slide using Teaching Assistant agent - can generate multiple frames"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")

        # Get the current LaTeX frames if they exist
        current_frames = self.latex_dict.get(slide_idx, {}).get("frames", [])
        current_frames_text = "\n\n".join([frame["full_frame"] for frame in current_frames]) if current_frames else None

        # Use utility function to generate the base prompt
        base_prompt = SlideUtils.generate_latex_frame_prompt(
            title=slide['title'],
            content=slide_draft,
            description=slide.get('description'),
            current_frames=current_frames_text,
            user_feedback=self.user_feedback,
            max_frames=3
        )

        # Grounding: wrap with per-slide narrowed evidence (no-op when
        # self.retriever is None — vanilla path).
        evidence_block, citation_rules = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )
        prompt = f"{evidence_block}\n{base_prompt}\n{citation_rules}"
        
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
        self._record_emitted_citations(response)
        
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

        # Grounding: per-slide narrowed retrieval (no-op when
        # self.retriever is None — vanilla path).
        # Script artifact uses softer rules — spoken narration, not text.
        evidence_block, citation_rules = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}",
            artifact="script",
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

        The script should be detailed enough for someone else to present effectively from it.
        If there are multiple frames, clearly indicate when to advance to the next frame.
        """
        
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
        self._record_emitted_citations(response)
        
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

        # Grounding: per-slide assessments use cross-chapter retrieval
        # (review questions span the course). Skip per-slide narrowing
        # here. No-op when self.retriever is None.
        evidence_block, citation_rules = self._build_evidence_block(
            f"{slide['title']}. {slide.get('description', '')}",
            artifact="assessment",
            cross_chapter=True,
        )

        # Create the prompt for the agent
        prompt = f"""
        {evidence_block}
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
        {citation_rules}

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
        self._record_emitted_citations(response)
        
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
    