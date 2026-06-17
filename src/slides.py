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
    \\frametitle{{<distinct topical subtitle for this frame>}}
    % Content goes here
\\end{{frame}}

If you produce multiple frames for one slide, give each frame a DISTINCT topical
subtitle reflecting its specific content (e.g. "K-Means Algorithm",
"K-Means Complexity", "K-Means Limitations") — NOT generic "Part 1",
"Part 2", "Part 3" suffixes.

FORBIDDEN frametitles — these read as placeholders and are a defect.
NEVER emit any of: "Visual Content", "Supporting Visual", "Visual Aid",
"Visual Representation", "Comparison Figures", "Illustration", "Diagram",
or any bare "Figure" / "Image" title. If the primary content of a frame
is a figure, title the frame after WHAT THE FIGURE SHOWS (e.g.
"K-Means: Cluster Assignment by Iteration", not "Visual Content").

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

PRESERVE FIGURES, CAPTIONS AND TABLES FROM THE DRAFT: if the Detailed Content
above contains a \\includegraphics{{...}} command pointing to a real file path,
you MUST keep it in the corresponding frame. Do NOT strip or replace it with
prose. If a \\caption{{...}} line follows the figure in the draft, KEEP it
immediately after the \\includegraphics — it tells the student what the figure
shows. Same for any \\begin{{tabular}} blocks. These come from the textbook's
figure and table extraction and are the only way the student sees the actual
visual content.

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

# Unescaped ampersands in slide TEXT (not in tabular/align). Detect
# lines that contain "& " outside of \begin{tabular}/\begin{align}
# environments. Replace with "\&".
_TABULAR_OR_ALIGN_OPEN = _re_for_latex_cleanup.compile(
    r"\\begin\{(tabular|align|array|matrix|pmatrix|bmatrix)\}"
)
_TABULAR_OR_ALIGN_CLOSE = _re_for_latex_cleanup.compile(
    r"\\end\{(tabular|align|array|matrix|pmatrix|bmatrix)\}"
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

# Markdown _italic_ (single-underscore pairs) the writer emitted into the
# .tex body. In LaTeX a bare ``_`` is a subscript operator and errors in
# text mode; in the PPTX path it leaks as literal "_k_". Convert to
# \emph{...}. The lookbehind excludes a preceding backslash (already
# escaped ``\_``) or word character (real subscripts like ``x_i`` and
# path underscores like ``data_mining``); the lookahead excludes a
# trailing word character so ``C_{ij}`` is left untouched.
_MARKDOWN_ITALIC_USCORE_IN_TEX_RE = _re_for_latex_cleanup.compile(
    r"(?<![\\\w])_([A-Za-z][A-Za-z0-9 ()'.,/+-]{0,40}?)_(?![\w])"
)

# Guillemet-style quote markers (<<"quote">>) the writer emits instead of
# plain quotes. Not valid LaTeX text; strip the angle pairs, keep content.
_GUILLEMET_IN_TEX_RE = _re_for_latex_cleanup.compile(r"<<+\s*|\s*>>+")

# Empty display math the writer left behind — ``\[ \]`` or an orphaned
# ``\[`` / ``\]`` on its own line. Renders as visible noise; strip it.
# Non-empty $$…$$ / \[…\] display math is intentionally NOT stripped here
# (the PPTX converter flattens its content to readable unicode).
_EMPTY_DISPLAY_MATH_RE = _re_for_latex_cleanup.compile(r"\\\[\s*\\\]")

# Broken cross-references — the writer emits ``\ref{fig:...}`` but the
# pipeline never ``\label{}``s anything, so the reference resolves to
# nothing (rendering "Figure ?? " or, after a naive strip, "Figure
# provides …"). "Figure \ref{...}" → "the figure"; a bare \ref → "".
_FIGURE_REF_RE = _re_for_latex_cleanup.compile(
    r"\b(Figure|Table|Equation|Eq\.?)\s*~?\s*\\(?:eqref|ref)\{[^}]*\}",
    _re_for_latex_cleanup.IGNORECASE,
)
_BARE_REF_RE = _re_for_latex_cleanup.compile(r"\\(?:eqref|ref)\{[^}]*\}")


def _figure_ref_replacement(match):
    word = match.group(1).lower().rstrip(".")
    word = "equation" if word in ("eq", "equation") else word
    return "the " + word
_ORPHAN_DISPLAY_DELIM_RE = _re_for_latex_cleanup.compile(
    r"(?m)^[ \t]*\\[\[\]][ \t]*$"
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


def _clean_latex_artifacts(text):
    """LaTeX cleanup: scrub writer-side LaTeX bugs that
    break PDF conversion. Runs on the final artifact text.
    Safe-by-default — only fixes well-characterized failure patterns;
    ambiguous edits left alone.

    Fixes:
      1. \\includegraphics{/path/to/file.png} (hallucinated path) →
         remove the entire \\includegraphics line so the slide still
         compiles.
      3. Bare ampersands and percent signs in slide text outside
         tabular/align → \\& / \\% (an unescaped % is a LaTeX line-comment
         that silently drops the rest of the line, e.g. "80% of buyers").
      4. Unicode em-dash, en-dash, curly quotes, ellipsis →
         LaTeX-native ASCII equivalents (---, --, ``...'', \\ldots{})
         so the default beamer font (ec-lmss10) can render them.
      6. Inject \\graphicspath{...} into the preamble (right after
         \\usepackage{graphicx}) so .grounding_cache/ paths resolve
         from the project root no matter where slides.tex is compiled.
    """
    if not text:
        return text
    # Fix 1: drop hallucinated includegraphics paths
    text = _FAKE_PATH_INCLUDEGRAPHICS_RE.sub("", text)
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
    # Fix 4c: convert markdown _italic_ (single-underscore pairs) into
    # \emph{...} so it renders italic in LaTeX and clean text in PPTX
    # rather than leaking as literal "_k_".
    text = _MARKDOWN_ITALIC_USCORE_IN_TEX_RE.sub(r"\\emph{\1}", text)
    # Fix 4d: strip guillemet quote markers (<<"...">>) and empty /
    # orphaned display-math delimiters — writer artifacts that render as
    # visible noise. Non-empty $$…$$ / \[…\] display math is left intact:
    # the PPTX converter flattens its content to readable unicode, and
    # stripping the fences here would feed bare \frac{…} to the
    # converter's command-stripper, which erases it (leaving "s(o) =").
    text = _GUILLEMET_IN_TEX_RE.sub("", text)
    text = _EMPTY_DISPLAY_MATH_RE.sub("", text)
    text = _ORPHAN_DISPLAY_DELIM_RE.sub("", text)
    # Fix 4e: rewrite broken figure/table cross-references so they read
    # naturally instead of leaving "Figure  provides …".
    text = _FIGURE_REF_RE.sub(_figure_ref_replacement, text)
    text = _BARE_REF_RE.sub("", text)
    # Fix 4: replace problem unicode characters with LaTeX equivalents
    for src, dst in _UNICODE_REPLACEMENTS.items():
        if src in text:
            text = text.replace(src, dst)
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
                # Escape a literal percent in prose ("80%" → "80\%"). A bare
                # % is a LaTeX line-comment, so "80% of buyers" silently
                # dropped everything after it at render. Skips an already
                # escaped \%; same class of fix as the ampersand escape above.
                line = _re_for_latex_cleanup.sub(
                    r"(?<!\\)%", r"\\%", line,
                )
        if _TABULAR_OR_ALIGN_CLOSE.search(line):
            in_math_env = max(0, in_math_env - 1)
        out_lines.append(line)
    return "\n".join(out_lines)


_SECTION_TITLE_DECOR_RE = re.compile(
    r"\*+|`+|\[|\]|^\s*\d+(?:\.\d+)*\s+"  # bold/italic/code, brackets, leading "N.N "
)


def _normalize_section_title(title):
    """Strip markdown decoration and leading section numbers from a
    raw IR section title so it reads as a clean topic name.

    Input: ``"10.2 **[Partitioning Methods]**"``  →  ``"Partitioning Methods"``
    Input: ``"3.4 Data Reduction"``               →  ``"Data Reduction"``
    Input: ``"Bibliographic Notes"``              →  ``"Bibliographic Notes"``

    The ingester preserves textbook formatting verbatim; outline-prompt
    consumers want a clean topic phrase the LLM treats as a coverage
    requirement.
    """
    if not title:
        return ""
    cleaned = title.strip()
    # Drop leading section number like "10.2 " or "3.4.1 "
    cleaned = re.sub(r"^\s*\d+(?:\.\d+)*\s+", "", cleaned)
    # Strip markdown markers and bracket decoration
    cleaned = re.sub(r"\*+|`+", "", cleaned)
    cleaned = cleaned.replace("[", "").replace("]", "")
    # Drop a trailing book-page-number remnant like " 444" pymupdf4llm
    # sometimes glues onto a heading.
    cleaned = re.sub(r"\s+\d+\s*$", "", cleaned)
    return cleaned.strip()


_CONTENT_TOKEN_STOP = frozenset({
    "the", "and", "for", "are", "with", "this", "that", "from", "into",
    "based", "such", "which", "each", "their", "these", "those", "other",
    "using", "used", "can", "may", "also", "where", "when", "data",
    "method", "methods", "cluster", "clusters", "clustering", "figure",
    "shows", "show", "example", "section", "chapter", "objects", "object",
}, )


def _content_tokens(text):
    """Lowercased content tokens (≥3 chars, stopwords + generic
    domain filler dropped). Used to score figure-to-slide relevance by
    term overlap. Empty input → empty set."""
    if not text:
        return set()
    raw = re.findall(r"[a-z][a-z\-]{2,}", text.lower())
    return {t for t in raw if t not in _CONTENT_TOKEN_STOP and len(t) >= 4}


_SECTION_NUMBER_RE = re.compile(r"\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _section_order_key(title, fallback_idx):
    """Sort key that orders sections by the numeric prefix in their
    title (``10.1`` < ``10.2`` < ``10.6`` < ``11.1``) so the outline
    follows the textbook's section sequence rather than chunk-arrival
    order. Sections with no leading number (references, bibliographic
    notes) sort last, then fall back to first-seen order for stability."""
    m = _SECTION_NUMBER_RE.match(title or "")
    if m and m.group(1):
        return (
            int(m.group(1)),
            int(m.group(2) or 0),
            int(m.group(3) or 0),
            fallback_idx,
        )
    return (9999, 9999, 9999, fallback_idx)


def _extract_topic_names(chunks):
    """Return the ordered list of distinct, normalized ``section_title``
    values across the supplied chunks.

    Textbook section titles are the textbook author's own naming for
    every covered topic. Lifting them from the IR — after normalizing
    out the markdown bold / bracket / section-number decoration the
    ingester preserves — gives the outline agent a clean coverage
    requirement. Works on any textbook the ingester can parse.
    """
    if not chunks:
        return []
    seen = []
    seen_set = set()
    for c in chunks:
        title = _normalize_section_title(getattr(c, "section_title", ""))
        if title and title not in seen_set:
            seen.append(title)
            seen_set.add(title)
    return seen


def _section_word_counts(chunks):
    """Return {section_id: total word count} across the supplied chunks.

    Used by the slide-outline prompt to allocate the slide budget
    proportional to each section's coverage in the textbook (so BIRCH —
    9 author slides — gets more outline slots than K-Modes, which gets 1).
    """
    counts: dict = {}
    for c in chunks:
        sid = c.section_id
        if not sid:
            continue
        counts[sid] = counts.get(sid, 0) + len((c.text or "").split())
    return counts


# Slide-budget scaling (grounded path). The configured slide count is treated
# as the budget for a typical chapter of _BUDGET_REFERENCE_SECTIONS bound
# sections; chapters that bind more/less content scale up/down within
# [_BUDGET_MIN_SCALE, _BUDGET_MAX_SCALE] so a content-rich chapter (e.g.
# clustering, ~12 sections) gets more slides than a thin one — without the
# per-chapter cost running away. Reference is set slightly above the historical
# default so the course-wide total stays close to the configured budget.
_BUDGET_REFERENCE_SECTIONS = 8
_BUDGET_MIN_SCALE = 0.7
_BUDGET_MAX_SCALE = 1.3


def _scaled_slide_budget(base_target: int, n_sections: int) -> int:
    """Scale the per-chapter slide budget by how many textbook sections are
    bound (more content -> more slides) relative to a reference chapter,
    clamped so per-chapter cost stays bounded. Falls back to ``base_target``
    when no sections are bound (vanilla / off-textbook chapters)."""
    if n_sections <= 0:
        return base_target
    scaled = round(base_target * n_sections / _BUDGET_REFERENCE_SECTIONS)
    return max(
        round(_BUDGET_MIN_SCALE * base_target),
        min(round(_BUDGET_MAX_SCALE * base_target), scaled),
    )


_EXAMPLE_ID_RE = re.compile(
    r"\bExample\s+(\d+\.\d+)\b[^.]{0,180}",
    re.IGNORECASE,
)


def _extract_example_identifiers(chunks):
    """Return ordered ``[(identifier, topic_summary), ...]`` for every
    distinct ``Example N.M`` found in the supplied chunks.

    The PDF ingester tags chunks containing an ``Example N.M`` header as
    ``kind='example'``; this helper pulls the explicit identifier plus
    a short topic descriptor straight out of the chunk text so the
    outline prompt can list them as concrete required slides (versus
    just naming the parent section, which the agent treats as more of
    the same topic). Dedup preserves first-seen order.

    Returns at most one entry per ``Example`` identifier; the topic
    string is the trailing text from the same paragraph, lightly
    cleaned.
    """
    seen = {}
    order = []
    for c in chunks:
        if "example" not in (getattr(c, "kinds", set()) or set()):
            continue
        text = c.text or ""
        for m in _EXAMPLE_ID_RE.finditer(text):
            ident = f"Example {m.group(1)}"
            if ident in seen:
                continue
            trailing = m.group(0)[len(m.group(0).split(None, 2)[0]) + 1 + len(m.group(1)) + 1:]
            topic = re.sub(r"^[\s.:—\-_]+", "", trailing).strip()
            topic = re.sub(r"[*_]+", "", topic).strip()
            topic = re.sub(r"\s+", " ", topic)
            if len(topic) > 110:
                topic = topic[:110].rsplit(" ", 1)[0] + "…"
            seen[ident] = topic or "(see textbook)"
            order.append(ident)
    return [(ident, seen[ident]) for ident in order]


def _section_depth_signals(chunks):
    """Return per-section richness signals for the outline prompt.

    Returns {section_id: {title, words, chunks, examples, equations,
    figures, order_idx}} where order_idx preserves the first-seen
    section order so the outline can render in source order rather
    than by descending size.

    Beyond raw word count, the writer's depth allocation should react
    to the count of distinct teachable artifacts each section carries
    (each example deserves a slide; each equation block deserves a
    slot; each figure anchors a visual slide). Word count alone
    under-weights dense algorithm sections that pack many short
    paragraphs.
    """
    out: dict = {}
    for idx, c in enumerate(chunks):
        sid = c.section_id
        if not sid:
            continue
        entry = out.setdefault(sid, {
            "title": _normalize_section_title(getattr(c, "section_title", "")),
            "words": 0,
            "chunks": 0,
            "examples": 0,
            "equations": 0,
            "figures": 0,
            "order_idx": idx,
        })
        entry["words"] += len((c.text or "").split())
        entry["chunks"] += 1
        kinds = getattr(c, "kinds", set()) or set()
        if "example" in kinds:
            entry["examples"] += 1
        if "equation" in kinds:
            entry["equations"] += 1
        if "figure_cap" in kinds:
            entry["figures"] += 1
    return out


_INCLUDEGRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}"
)


def _extract_includegraphics(text):
    """Return the list of full ``\\includegraphics[..]{path}`` commands
    that appear in ``text``. Used to detect figure references the
    Teaching Faculty's slide_draft emitted so the orchestrator can
    re-inject them into the Teaching Assistant's frames if the TA
    dropped them during the LaTeX rewrite (a recurring attention-budget
    failure)."""
    if not text:
        return []
    return _INCLUDEGRAPHICS_RE.findall(text)


# A figure placement = the \includegraphics line plus an optional \caption line
# right after it. Used to dedupe an image the matcher placed on more than one
# slide (each with an invented caption).
_FIGURE_PLACEMENT_RE = re.compile(
    r"[ \t]*\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}[^\n]*\n"
    r"(?:[ \t]*\\caption\{[^}]*\}[^\n]*\n)?"
)


def _dedupe_repeated_figures(text):
    """Keep each image's FIRST placement in the deck and strip later ones — the
    \\includegraphics together with its \\caption, so no orphan caption is left
    behind. The figure matcher can pick the same image for several slides; a
    figure reused 3x with three different invented captions is a defect. Matched
    by image basename. No-op when the deck has no figures."""
    if not text or "\\includegraphics" not in text:
        return text
    seen = set()

    def _repl(m):
        key = m.group(1).strip().rsplit("/", 1)[-1]
        if key in seen:
            return ""
        seen.add(key)
        return m.group(0)

    return _FIGURE_PLACEMENT_RE.sub(_repl, text)


_FRAMETITLE_RE = re.compile(r"\\frametitle\{([^}]*)\}")
_NAV_SKIP_TITLES = frozenset(
    {"learning objectives", "key takeaways", "outline", "agenda", "summary"}
)

_FRAME_RE = re.compile(r"\\begin\{frame\}(?:\[[^\]]*\])?(.*?)\\end\{frame\}", re.S)


def _drop_empty_frames(text):
    """Remove frames that render blank — a frametitle with no figure and no
    text body. The writer sometimes emits a figure-dedicated slide ("Diagram:
    ...", "Illustration of ...") that never receives a figure, leaving an
    empty frame that ships as a blank slide. Run after the figure passes
    (which can empty a frame by stripping its only image) and before
    navigation insertion (so the agenda/recap never list a dropped slide).
    No-op when every frame carries content."""
    if not text or "\\begin{frame}" not in text:
        return text

    def _has_content(body):
        if "\\includegraphics" in body:
            return True
        b = _FRAMETITLE_RE.sub("", body)                # drop the title
        b = re.sub(r"\\(begin|end)\{[^}]*\}", "", b)    # env delimiters (name isn't content)
        b = re.sub(r"\[[^\]]*\]", "", b)                # bracket options like [fragile]
        b = re.sub(r"\\[a-zA-Z]+\*?", "", b)            # command tokens, keep braced text
        b = re.sub(r"[{}]", "", b)                      # remaining braces
        return bool(re.search(r"[A-Za-z0-9]", b))

    return _FRAME_RE.sub(
        lambda m: m.group(0) if _has_content(m.group(1)) else "", text
    )


def _insert_navigation_frames(text):
    """Insert a 'Learning Objectives' frame after the opening slide and a 'Key
    Takeaways' recap at the end, derived from the deck's own topic titles. The
    soft-prompt instruction for these is unreliable, so this guarantees the
    author-style scaffolding deterministically. No-op on a deck with no frames."""
    if not text or "\\begin{frame}" not in text:
        return text
    titles = _FRAMETITLE_RE.findall(text)
    topics = []
    for t in titles[1:]:  # skip the opening slide's title
        tl = re.sub(r"\s+", " ", t).strip()
        if not tl or tl.lower() in _NAV_SKIP_TITLES or tl in topics:
            continue
        topics.append(tl)
    if not topics:
        return text
    n = min(6, len(topics))
    step = max(1, len(topics) // n)
    chosen = topics[::step][:6]
    items = "\n".join(f"\\item {t}" for t in chosen)
    obj_frame = (
        "\\begin{frame}\n\\frametitle{Learning Objectives}\n"
        "By the end of this chapter, you should be able to understand and apply:\n"
        "\\begin{itemize}\n" + items + "\n\\end{itemize}\n\\end{frame}\n\n"
    )
    rec_frame = (
        "\n\\begin{frame}\n\\frametitle{Key Takeaways}\n"
        "This chapter covered:\n"
        "\\begin{itemize}\n" + items + "\n\\end{itemize}\n\\end{frame}\n"
    )
    end1 = text.find("\\end{frame}")
    if end1 != -1:
        cut = end1 + len("\\end{frame}")
        text = text[:cut] + "\n\n" + obj_frame + text[cut:]
    doc_end = text.rfind("\\end{document}")
    if doc_end != -1:
        text = text[:doc_end] + rec_frame + text[doc_end:]
    else:
        text = text + rec_frame
    return text


# A bullet / line that promises a visual but supplies none — "...can be
# illustrated graphically:", "...as shown below:", "Visual Representation:
# ... depicted here:". When the enclosing frame has no \includegraphics,
# this dangling promise renders as a near-empty slide with a trailing
# colon. Matched only at the end of a line so genuine "as follows:" lists
# (which have items after them) are untouched.
_FIGURE_PROMISE_LINE_RE = re.compile(
    r"(?im)^.*\b(?:illustrated|shown|depicted|visualized|represented|"
    r"displayed|seen|drawn)\b[^.\n]*\b(?:graphically|below|here|in the "
    r"(?:figure|diagram|image|plot)|as follows)\b[^.\n]*:\s*$"
)
# Also catch a bare "Visual Representation: <one clause>:" lead-in with a
# trailing colon and no following content on the line.
_VISUAL_LEADIN_LINE_RE = re.compile(
    r"(?im)^\s*(?:\\item\s+)?(?:visual representation|visual aid|"
    r"illustration|graphic(?:al)? (?:representation|depiction))\b[^.\n]*:\s*$"
)

# Deictic figure-pointer language — phrases that point AT a figure rather than
# describe one in the abstract: "the following figure", "the figure below", "in
# the following figure, we illustrate …", "in Figure 1.9", "we include a
# relevant figure", "refer to the accompanying figure". On a frame with no
# resolving figure (the guard in _strip_dangling_figure_promises) such a pointer
# is necessarily dangling. Indefinite "a figure that shows …" is NOT a pointer
# and is deliberately excluded.
_DEICTIC_FIGURE = (
    r"(?:in |on )?the following figure|"
    r"the figure below|figure below|"
    r"the (?:above|adjacent|accompanying|preceding) figure|"
    r"this figure|that figure|"
    r"(?:refer to|see|consider|note) (?:the )?(?:accompanying |following |above )?"
    r"(?:figure|diagram|illustration|image|plot)|"
    r"in (?:figure|fig\.?)\s*\d+(?:\.\d+)?|"
    r"(?:we|i) (?:include|provide|present|add|show|illustrate|depict|visualize)"
    r"[^.\n]*\bfigure|"
    r"(?:this|the) figure\b[^.\n]*\b(?:shows|highlights|depicts|illustrates|"
    r"displays|represents|provides|presents|demonstrates|captures|reveals|"
    r"indicates|visualizes|visualises|conveys|summarizes|summarises|"
    r"reflects|portrays|outlines)|"
    r"as (?:shown|depicted|illustrated) in the figure"
)
# A LINE that BEGINS with a figure pointer is a pure promise — drop the whole
# line, including any continuation clause ("… It shows three clusters:").
_FIGURE_PROMISE_LEADING_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:\\item\s+)?(?:" + _DEICTIC_FIGURE + r")\b.*$"
)
# A figure pointer that appears MID-line, AFTER a real sentence — strip only
# that one sentence (bounded by the surrounding periods) so the real leading
# sentence on the same line is preserved (don't blank a content slide that
# merely ends with a dangling "The following figure illustrates …").
_FIGURE_REFERENCE_SENTENCE_RE = re.compile(
    r"(?im)[^.\n]*\b(?:" + _DEICTIC_FIGURE + r")\b[^.\n]*[.:]"
)


def _frame_has_resolving_figure(frame):
    """True if the frame carries an \\includegraphics whose path exists on
    disk — i.e. a figure that will actually render."""
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", frame):
        if os.path.exists(m.group(1)):
            return True
    return False


def _strip_dangling_figure_promises(text):
    """Remove figure-promise / figure-reference lines from frames that
    carry no rendering figure.

    The Faculty sometimes writes "...the steps can be illustrated
    graphically:" or "refer to the accompanying figure" on a slide where
    no figure is present (no marker, or an \\includegraphics whose path
    doesn't resolve), leaving a dangling pointer to a picture that never
    appears. Operating per frame, this drops such lines ONLY when the
    frame has no figure that actually renders. Returns the text unchanged
    on the vanilla path (no such promises)."""
    if not text or "\\begin{frame}" not in text:
        return text

    def _process_frame(match):
        frame = match.group(0)
        if _frame_has_resolving_figure(frame):
            return frame  # a real figure renders — leave the text alone
        frame = _FIGURE_PROMISE_LINE_RE.sub("", frame)
        frame = _VISUAL_LEADIN_LINE_RE.sub("", frame)
        frame = _FIGURE_PROMISE_LEADING_LINE_RE.sub("", frame)
        frame = _FIGURE_REFERENCE_SENTENCE_RE.sub("", frame)
        # No figure on this frame resolves to a real file, so any
        # \includegraphics here is a hallucinated path / external URL (the
        # real ones were guarded above) and any \caption is now orphaned.
        # Strip both so a frame left with nothing but a figure that never
        # appears is recognised as empty by _drop_empty_frames downstream
        # (it treats a bare \includegraphics as content, so the dead command
        # must go for the empty-frame drop to fire).
        frame = re.sub(
            r"[ \t]*\\includegraphics(?:\[[^\]]*\])?\{[^}]*\}[^\n]*\n?", "", frame
        )
        frame = re.sub(r"[ \t]*\\caption\*?\{[^{}]*\}[^\n]*\n?", "", frame)
        return frame

    return re.sub(
        r"\\begin\{frame\}.*?\\end\{frame\}",
        _process_frame, text, flags=re.DOTALL,
    )


_IMAGE_PATH_MARKER_RE = re.compile(
    r"\[IMAGE_PATH:\s*([^\]]+)\]|!\[\]\(([^)]+)\)"
)


def _build_real_figure_filenames(kb_chunks):
    """Set of image FILENAMES that come from ``figure_cap`` chunks but NOT
    from ``equation`` chunks. Used to gate caption injection: an equation
    crop must not receive a "Figure N.M" caption (it is a formula, not a
    figure). Empty input → empty set."""
    fig, eq = set(), set()
    for c in kb_chunks or []:
        kinds = getattr(c, "kinds", set()) or set()
        if "figure_cap" not in kinds and "equation" not in kinds:
            continue
        target = fig if "figure_cap" in kinds and "equation" not in kinds else eq
        for m in _IMAGE_PATH_MARKER_RE.finditer(c.text or ""):
            name = (m.group(1) or m.group(2) or "").strip().rsplit("/", 1)[-1]
            if name:
                target.add(name)
    return fig - eq


def _dedupe_outline_titles(outline):
    """Drop later slides whose title duplicates an earlier one (normalized:
    lowercased, punctuation/whitespace collapsed). Keeps the first
    occurrence and preserves order. Used on the grounded outline where the
    designer occasionally emits two identically-titled slides."""
    if not outline:
        return outline
    seen = set()
    out = []
    for slide in outline:
        title = (slide.get("title") or "") if isinstance(slide, dict) else ""
        key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(slide)
    return out


def _first_image_path(text):
    """First image path in a chunk's text — from an ``[IMAGE_PATH: ...]``
    marker or a markdown ``![](...)`` reference. Returns '' when none."""
    if not text:
        return ""
    m = _IMAGE_PATH_MARKER_RE.search(text)
    if not m:
        return ""
    return (m.group(1) or m.group(2) or "").strip()


def _build_figure_caption_by_path(kb_chunks):
    """Map image FILENAME -> its OWN caption, pairing each figure's
    ``[IMAGE_PATH: ...]`` with the ``Figure N: <caption>`` text in the SAME
    chunk (atomic — the caption travels with its image). Preferred over the
    page-based map, which returns the first caption on a page and so
    mis-captions multi-figure pages. Empty input → empty map."""
    out = {}
    for c in kb_chunks or []:
        text = c.text or ""
        pm = _IMAGE_PATH_MARKER_RE.search(text)
        if not pm:
            continue
        fname = (pm.group(1) or pm.group(2) or "").strip().rsplit("/", 1)[-1]
        if not fname:
            continue
        cm = re.search(
            r"Figure\s+[\d.]+\*{0,2}\s*[:.]?\s*(.+)", text[: pm.start()], re.S
        )
        if not cm:
            continue
        cap = re.sub(r"[*_]+", "", cm.group(1)).strip()
        if cap:
            out[fname] = cap
    return out


def _caption_for_figure_path(path, by_path=None):
    """Textbook caption for a figure path — **strictly atomic**. Returns ONLY
    the caption that shipped in the SAME chunk as this exact image (``by_path``,
    keyed on filename); if this image has no paired caption, returns ``""`` and
    the figure renders bare (the converter still adds a generic "Figure."
    label). There is deliberately NO page-based fallback: a page lookup can only
    guess among the captions on that page, which is exactly how a scatter plot
    ends up under a "data characterization" label — a confidently-wrong caption
    is worse than none. Strict atomicity means zero downstream guessing."""
    if not by_path:
        return ""
    return by_path.get((path or "").rsplit("/", 1)[-1], "")


def _inject_missing_figure_captions(text, figure_filenames=None,
                                    by_path=None):
    """Add a ``\\caption{}`` after any ``\\includegraphics`` that has none,
    sourced from the textbook's **atomic** caption for THAT exact image
    (``by_path`` — the caption that shipped in the same chunk as the image), so
    a caption can never describe a different figure. An image with no paired
    caption is left bare. Writer-supplied captions are left untouched.

    Two guards keep captions honest:
      * the image path must RESOLVE on disk — a caption for a missing
        image would render as an orphan "Figure. …" line; and
      * when ``figure_filenames`` is supplied, the image must be a real
        figure (not an equation crop), so a formula never gets a
        "Figure N.M" caption.

    No-op when there is no caption source or no figures."""
    if not text or not by_path or "\\includegraphics" not in text:
        return text
    out = []
    pos = 0
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", text):
        out.append(text[pos:m.end()])
        pos = m.end()
        tail = text[m.end():m.end() + 220]
        nxt = re.search(r"\\caption|\\includegraphics|\\end\{frame\}", tail)
        if nxt is not None and nxt.group(0) == "\\caption":
            continue  # writer already captioned this figure
        path = m.group(1)
        if not os.path.exists(path):
            continue  # missing image — captioning it makes an orphan line
        if figure_filenames is not None:
            name = path.rsplit("/", 1)[-1]
            if name not in figure_filenames:
                continue  # equation crop / non-figure — don't label it "Figure"
        cap = _caption_for_figure_path(path, by_path=by_path)
        if cap:
            cap_tex = (cap.replace("&", "\\&").replace("%", "\\%")
                          .replace("_", "\\_").replace("#", "\\#"))
            out.append("\n    \\caption{" + cap_tex + "}")
    out.append(text[pos:])
    return "".join(out)


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
                 content_verifier=None,
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
        # Advisory content-fidelity verifier. When set (grounded path only),
        # the finished artifacts are judged against retrieved evidence after
        # the save and a report is logged. Log-only — never mutates artifacts.
        # Vanilla path leaves this None and behavior is byte-identical.
        self.content_verifier = content_verifier
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

    # Artifact-type vocabulary for `_build_evidence_block`. The strict
    # rule-set ("slide") applies to slides + assessments — both are
    # READ documents. The relaxed rule-set ("script") applies to
    # speaker scripts — SPOKEN narration where mandatory direct
    # quotation breaks narrative flow, so RULE 2 softens to "paraphrase
    # naturally."
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

        Returns ``(evidence_block, "")`` — the second element is always an
        empty string (the 2-tuple shape is kept so callers need no signature
        change). ``evidence_block`` is empty too when ``self.retriever is
        None`` (vanilla path) or retrieval yielded nothing in scope; it is a
        chunk of plain text the caller prepends to its prompt.

        ``artifact`` is one of ``"slide" | "script" | "assessment"``; it
        toggles RULE 2 (paraphrase / teach-in-own-words) between the slide
        and spoken-script phrasings. RULES 3 / 6 / 7 (abstain, preserve
        worked examples, preserve math notation) are universal.

        Design notes:
          * Structured per-excerpt headers (SOURCE / PAGE / KIND / PASSAGE)
            give the LLM clear labels to anchor on, vs a flat text dump.
          * Visual-content rules (the [IMAGE_PATH:] -> \\includegraphics
            directive) are appended only when the evidence carries hybrid-
            ingester markers, so vanilla prompts are unaffected.
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
            # writer calls. Abort cleanly rather than letting the loop
            # drift indefinitely. Threshold is intentionally generous
            # (allows real transient blips like brief rate limits) but
            # short enough to catch genuinely-broken retrieval before it
            # racks up cost.
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
                    f"further cost (writer calls keep running even though no "
                    f"grounded evidence is reaching the prompt). "
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
        # sees redundant content. We drop later occurrences of any chunk
        # whose text is byte-for-byte equal to an earlier kept chunk OR
        # whose first ~40 words match an earlier kept chunk (catches the
        # overlap case where the start of chunk N+1 equals the end of
        # chunk N).
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
                results, effective_section_ids, query=query,
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
            blocks.append(self._excerpt_block(r, idx, len(results), text))
            budget -= len(text.split())
            if budget <= 0:
                break

        # Artifact-conditioned RULE 2 (teach / paraphrase). RULES 3, 6, 7
        # are universal.
        evidence_block = (
            self._evidence_directive(artifact, len(blocks))
            + "\n\n".join(blocks)
            + "\n\n"
            "════════════════════════════════════════════════════════════════════\n"
        )

        # ---- Visual-content rules: only added when the evidence
        # ---- actually contains hybrid-ingester markers. Vanilla
        # ---- chunks contain none of these, so the rules block is empty
        # ---- and the prompt is byte-identical to the prior behavior.
        joined_text = "\n".join(blocks)
        visual_rules = self._build_visual_content_rules(joined_text, artifact)
        if visual_rules:
            evidence_block = evidence_block + visual_rules

        return evidence_block, ""

    def _excerpt_block(self, r, idx, total, text):
        """Format one retrieval result as a structured excerpt block
        (SOURCE / PAGE / KIND / PASSAGE). ``total`` may be an int (flat block)
        or a placeholder string (grouped block)."""
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
        kind_label = "+".join(kinds)
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
        excerpts — shared by the flat and grouped evidence blocks."""
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
            "════════════════════════════════════════════════════════════════════\n"
            f"{header_label}\n"
            "════════════════════════════════════════════════════════════════════\n\n"
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
            "═══════════════════════════ EXCERPTS ═══════════════════════════\n\n"
        )

    _GROUPED_PER_SLIDE_K = 3

    def _build_grouped_evidence_block(self, outline, artifact="slide"):
        """Group evidence BY outline slide: each slide-topic gets its own
        labeled set of excerpts, so the writer sees focused per-slide context
        instead of one undifferentiated chapter dump. Retrieves per
        slide-topic (scoped to the bound sections — cheap index lookups, no
        LLM), dedupes chunks globally so none repeats across slides, and shares
        one rule header + the total word budget. Returns ``("", "")`` when
        there is no retriever (vanilla) or no usable outline — the caller then
        falls back to the flat chapter-level block."""
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
            + "\n\n"
            "════════════════════════════════════════════════════════════════════\n"
        )
        joined_text = "\n".join(groups)
        visual_rules = self._build_visual_content_rules(joined_text, artifact)
        if visual_rules:
            evidence_block = evidence_block + visual_rules
        return evidence_block, ""

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

    # At most one injected figure per slide — author-deck slides carry a
    # single focused figure, and cramming several tiny mismatched crops
    # onto one slide (the v9 failure mode) reads far worse than one
    # well-chosen figure.
    _VISUAL_INJECT_CAP = 1
    # Minimum content-token overlap for a cross-section figure to be
    # injected onto a slide. Same-section figures bypass this gate.
    _VISUAL_RELEVANCE_MIN_OVERLAP = 2

    def _caption_embedding(self, caption):
        """Cached unit-norm embedding of a textbook figure caption. Returns
        None if embedding is unavailable. Captions repeat across slides, so
        caching keeps the per-run embedding cost to one call per caption."""
        import numpy as np
        cache = getattr(self, "_fig_caption_emb_cache", None)
        if cache is None:
            cache = self._fig_caption_emb_cache = {}
        if caption not in cache:
            try:
                v = self.retriever.embedder.embed([caption])[0]
                cache[caption] = v / (float(np.linalg.norm(v)) + 1e-9)
            except Exception:
                cache[caption] = None
        return cache[caption]

    def _figure_caption_relevance(self, candidates, query):
        """Return ``{id(chunk): cosine}`` of each candidate visual chunk
        against the slide query.

        For a FIGURE chunk the chunk text is just an ``[IMAGE_PATH:]``
        marker (semantically empty), so its page-matched caption
        ("Figure 10.15: DBSCAN algorithm") is the signal that tells a
        DBSCAN figure from an OPTICS one. For an EQUATION (or other
        marker-only) chunk there is no figure caption, but the chunk's
        own prose IS meaningful, so it is used directly — this keeps the
        BCubed "Correctness" formula off the Silhouette slide. Empty dict
        when embeddings are unavailable (caller falls back to token
        overlap)."""
        import numpy as np
        try:
            kb_chunks = self.retriever.kb.chunks
        except AttributeError:
            return {}
        bymap = getattr(self, "_fig_caption_by_path_cache", None)
        if bymap is None:
            bymap = _build_figure_caption_by_path(kb_chunks)
            self._fig_caption_by_path_cache = bymap
        try:
            qv = self.retriever.embedder.embed([query])[0]
            qv = qv / (float(np.linalg.norm(qv)) + 1e-9)
        except Exception:
            return {}
        scores = {}
        for c in candidates:
            path = _first_image_path(c.text)
            rep = _caption_for_figure_path(path, by_path=bymap) if path else ""
            if not rep:
                # Equation / uncaptioned chunk: embed its own prose
                # (drop the visual markers first).
                rep = re.sub(
                    r"\[(?:IMAGE_PATH|LATEX|TABLE|ALGORITHM_STEPS|"
                    r"DESCRIPTION|INSIGHT)[^\]]*\]", "", c.text or "")
                rep = re.sub(r"!\[\]\([^)]*\)", "", rep).strip()[:300]
            if not rep:
                continue
            cv = self._caption_embedding(rep)
            if cv is not None:
                scores[id(c)] = float(np.dot(qv, cv))
        return scores

    def _inject_visual_chunk_if_available(self, results, section_ids, query=None):
        """Hoist the single most slide-relevant in-scope visual chunk
        (IMAGE_PATH / LATEX / TABLE / ALGORITHM_STEPS marker) to the FRONT
        of ``results``, up to ``_VISUAL_INJECT_CAP``.

        The block-builder loop downstream consumes a fixed word budget per
        chunk in rank order; putting the visual chunk first guarantees its
        marker survives into the evidence text even when later prose chunks
        get truncated.

        Figure choice is by EMBEDDING similarity of each candidate's
        textbook caption to the slide query (so a DBSCAN slide gets the
        DBSCAN figure, not the OPTICS one that shares its section), falling
        back to content-token overlap when embeddings are unavailable.
        Same-section figures are preferred; cross-section figures must
        clear the overlap gate. Lower-ranked prose chunks are dropped to
        keep the result count stable.

        Returns ``results`` unchanged when retrieval is empty, the
        retriever is None (vanilla path), or no visual chunks exist in
        scope.
        """
        if not results or self.retriever is None:
            return results
        try:
            kb_chunks = self.retriever.kb.chunks
        except AttributeError:
            return results

        cap = self._VISUAL_INJECT_CAP

        def has_marker(c):
            return any(m in c.text for m in self._VISUAL_MARKERS)

        existing_visuals = sum(1 for r in results if has_marker(r.chunk))
        if existing_visuals >= cap:
            return results

        wanted_sections = (
            set(section_ids) if section_ids is not None
            else {c.section_id for c in kb_chunks}
        )
        top_section = results[0].chunk.section_id
        seen = {id(r.chunk) for r in results}

        # Relevance reference for the token-overlap fallback / cross-section
        # gate: content tokens of the slide's best retrieved chunks.
        ref_tokens: set = set()
        for r in results[:3]:
            ref_tokens |= _content_tokens(r.chunk.text)
            ref_tokens |= _content_tokens(getattr(r.chunk, "section_title", ""))

        def _overlap(c):
            return len(ref_tokens & _content_tokens(c.text))

        same_section = [
            c for c in kb_chunks
            if c.section_id == top_section and has_marker(c) and id(c) not in seen
        ]
        cross_section = [
            c for c in kb_chunks
            if c.section_id in wanted_sections and c.section_id != top_section
            and has_marker(c) and id(c) not in seen
            and _overlap(c) >= self._VISUAL_RELEVANCE_MIN_OVERLAP
        ]

        # Primary ranking: caption↔query embedding similarity. Fall back to
        # token overlap when embeddings/captions are unavailable.
        emb = (self._figure_caption_relevance(same_section + cross_section, query)
               if query else {})

        def _rank(c):
            return emb.get(id(c), _overlap(c))

        same_section.sort(key=_rank, reverse=True)
        cross_section.sort(key=_rank, reverse=True)
        candidates: list = same_section + cross_section

        to_inject = candidates[:cap - existing_visuals]
        if not to_inject:
            return results

        from dataclasses import dataclass

        @dataclass
        class _VisualInjected:
            chunk: object

        injected = [_VisualInjected(chunk=c) for c in to_inject]
        # Drop the lowest-ranked prose chunks so the result count is
        # stable; injected visuals go to the front.
        kept_prose = list(results[: max(0, len(results) - len(to_inject))])
        return injected + kept_prose

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
                    "[IMAGE_PATH:] marker MUST emit a \\includegraphics for it."
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
        # LaTeX cleanup pass — fixes hallucinated \includegraphics
        # paths, unicode, and ampersand-escape bugs that broke PDF
        # compilation in earlier baselines. Only affects LaTeX output
        # (slides.tex); markdown unchanged.
        latex_source = _clean_latex_artifacts(latex_source)
        # Drop dangling "...illustrated graphically:" promises on frames
        # that carry no figure, so a missing [IMAGE_PATH:] marker doesn't
        # leave a near-empty slide with a trailing colon. Grounded path
        # only — vanilla frames carry no figure markers, so this stays a
        # no-op there and vanilla output is preserved byte-for-byte.
        if self.retriever is not None:
            # A figure appears once per deck — keep its first placement and strip
            # later \includegraphics (+ caption) so the same image isn't reused
            # across slides with invented captions. Run before the dangling-promise
            # strip so a slide that loses its duplicate figure gets cleaned up.
            latex_source = _dedupe_repeated_figures(latex_source)
            latex_source = _strip_dangling_figure_promises(latex_source)
            # Caption any figure the writer left bare, using the textbook's
            # OWN caption for THAT exact image (atomic — paired in the same IR
            # chunk). Only real, on-disk figures get captioned (not equation
            # crops or missing images); an image with no paired caption stays
            # bare rather than borrow a neighbour's.
            try:
                kb_chunks = self.retriever.kb.chunks
                caption_by_path = _build_figure_caption_by_path(kb_chunks)
                figure_filenames = _build_real_figure_filenames(kb_chunks)
                latex_source = _inject_missing_figure_captions(
                    latex_source, figure_filenames,
                    by_path=caption_by_path,
                )
            except AttributeError:
                pass

            # Drop frames the writer emitted as figure-dedicated ("Diagram:
            # ...", "Illustration of ...") that never received a figure — they
            # ship as blank slides. After the figure passes (which can empty a
            # frame) and before nav insertion (so the agenda never lists one).
            latex_source = _drop_empty_frames(latex_source)

            # Insert author-style navigation scaffolding deterministically (the
            # soft-prompt request for it is unreliable): a Learning Objectives
            # agenda after the opener and a Key Takeaways recap at the end.
            latex_source = _insert_navigation_frames(latex_source)

        # Advisory content-fidelity check on the finished, figure-cleaned
        # artifacts. Judges generated claims against the chapter's retrieved
        # evidence and logs a report — advisory only, never mutates the files.
        # Grounded path only; gated so the vanilla pipeline never runs it.
        if self.retriever is not None and getattr(self, "content_verifier", None) is not None:
            try:
                from src.grounding.content_verifier import report_line
                report = self.content_verifier.verify_chapter(
                    self.id,
                    chapter.get("title", self.name),
                    {"slides": latex_source, "script": slides_script_md},
                    self.section_ids,
                    writer_evidence=getattr(self, "_writer_evidence", None),
                )
                print(report_line(report))
                with open(
                    os.path.join(self.output_dir, "content_verification.json"), "w"
                ) as f:
                    json.dump(report, f, indent=2)
            except Exception as e:
                print(f"[grounding] content verifier failed (advisory): {e}")

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
        """Generate slides outline using Instructional Designer agent.

        Augments the outline prompt with textbook-derived signals when a
        retriever is wired in:
          * Algorithm names extracted from the chapter's bound chunks
            become required slide topics (gap 1).
          * Per-section word counts seed budget hints so heavier
            sections get more outline slots than thin ones (gap 3).
          * Comparison-slide pattern hints force "X vs Y" coverage where
            adjacent algorithms naturally pair (gap 10).
        """
        instructional_designer = self.agents.get("instructional_designer")
        if not instructional_designer:
            raise ValueError("Instructional Designer agent not found")

        outline_template = """[
            {"slide_id": 1, "title": "<concrete topic from the textbook chapter>",
             "description": "<one-sentence specific summary>"}
            ]"""

        base_target = int(self.catalog_dict.get("slides_length", 30)) // 3
        target_count = base_target

        textbook_hints = ""
        if self.retriever is not None and self.section_ids:
            # Scale the slide budget by how much textbook content is bound to
            # this chapter instead of a flat course-wide count, so a rich
            # chapter gets more slides than a thin one (grounded path only).
            target_count = _scaled_slide_budget(base_target, len(self.section_ids))
            try:
                kb_chunks = self.retriever.kb.chunks
                bound = [c for c in kb_chunks if c.section_id in self.section_ids]
            except AttributeError:
                bound = []
            topics = _extract_topic_names(bound)
            depth = _section_depth_signals(bound)
            example_identifiers = _extract_example_identifiers(bound)
            if depth:
                weighted = {
                    sid: (
                        d["words"]
                        + 25 * d["examples"]
                        + 15 * d["equations"]
                        + 10 * d["figures"]
                    )
                    for sid, d in depth.items()
                }
                total = sum(weighted.values()) or 1
                ordered = sorted(
                    depth.items(),
                    key=lambda kv: _section_order_key(
                        kv[1]["title"], kv[1]["order_idx"]
                    ),
                )
                allocations = []
                for sid, d in ordered:
                    share = weighted[sid] / total
                    slots = max(1, round(share * target_count))
                    flags = []
                    if d["examples"]:
                        flags.append(f"{d['examples']} ex")
                    if d["equations"]:
                        flags.append(f"{d['equations']} eq")
                    if d["figures"]:
                        flags.append(f"{d['figures']} fig")
                    extras = f" ({', '.join(flags)})" if flags else ""
                    allocations.append(
                        f"  - {sid} \"{d['title']}\": ~{slots} slides — "
                        f"{d['words']} words, {d['chunks']} chunks{extras}"
                    )
                budget_block = (
                    "SECTION BUDGET (slides MUST appear in the order below; "
                    "this mirrors the textbook's section order. Allocate "
                    "depth proportionally — sections rich in examples, "
                    "equations, or figures deserve more slots than thin "
                    "narrative sections):\n" + "\n".join(allocations)
                )
            else:
                budget_block = ""
            if topics:
                topic_block = (
                    "TOPIC COVERAGE — give each textbook topic below that "
                    f"fits the chapter \"{chapter['title']}\" its own "
                    "dedicated slide, with the topic's name in the title, "
                    "in the order shown (the textbook's own order). "
                    "Improvising generic \"Introduction Part 1/2/3\" titles "
                    "in place of these named topics is a defect. BUT if a "
                    "listed topic is clearly from a DIFFERENT subject than "
                    f"\"{chapter['title']}\" (a stray binding — e.g. a "
                    "preprocessing or classification topic in a clustering "
                    "chapter), SKIP it; do not create an off-topic slide:\n  "
                    + " → ".join(topics)
                )
            else:
                topic_block = ""
            if example_identifiers:
                example_lines = [
                    f"  - \"Example: {ident} — {topic}\""
                    for ident, topic in example_identifiers[:12]
                ]
                example_block = (
                    "REQUIRED WORKED-EXAMPLE SLIDES — the textbook carries "
                    "the worked examples below. EACH one MUST appear as a "
                    "separate slide whose title starts with \"Example:\". "
                    "Preserve the numerical trace (cluster centers, "
                    "iteration counts, intermediate values — not "
                    "paraphrased prose). Use the exact titles shown:\n"
                    + "\n".join(example_lines)
                )
            else:
                example_block = ""
            if len(topics) >= 2:
                comparison_block = (
                    "COMPARISON SLIDES — for any pair of related topics, "
                    "include a side-by-side comparison slide. Author-"
                    "curated decks rely on these to highlight trade-offs."
                )
            else:
                comparison_block = ""
            forbidden_block = (
                "FORBIDDEN SLIDE TITLES — substring match. ANY title that "
                "CONTAINS the words \"Visual\", \"Visualization\", "
                "\"Illustration\", \"Figure Illustration\", or \"Diagram\" "
                "as a descriptor noun is a defect. Adding a topic prefix "
                "or suffix does NOT make it acceptable. Concrete escape "
                "attempts you must NOT make:\n"
                "  - \"Visual Representation of Clustering\" ✗\n"
                "  - \"DBSCAN Visual Representation\" ✗\n"
                "  - \"Figure Illustration of DBI\" ✗\n"
                "  - \"K-Means Visualization\" ✗\n"
                "  - \"Algorithm Diagram\" ✗\n"
                "Every slide title MUST name the specific concept, "
                "algorithm, or worked example the slide teaches. If a "
                "figure is the primary content, title the slide after "
                "WHAT THE FIGURE SHOWS (e.g. \"K-Means: Cluster "
                "Assignment by Iteration\", \"DBSCAN: Density-Reachable "
                "Cluster Growth\"). Proper-noun usage of \"Voronoi "
                "Diagram\" or similar named concepts is allowed."
            )
            structure_block = (
                "DECK STRUCTURE — the FIRST slide MUST introduce the "
                "chapter topic: a plain-language definition plus what the "
                "lecture will cover. Do NOT open with a references, "
                "bibliography, or \"literature overview\" slide — those "
                "belong at the very end, if at all, and are not the "
                "lecture's content. Walk the sections in the numeric order "
                "given in the SECTION BUDGET. Aim for substantive, DENSE "
                "slides: each content slide should carry 4–6 teaching bullets "
                "that fill the slide — a slide with only 1–2 short bullets and "
                "large empty space is a defect; deepen it with the textbook's "
                "detail (definitions, steps, trade-offs, a worked number) or "
                "merge it with a neighbour.\n"
                "NO REDUNDANCY — every slide must teach NEW material. Do "
                "NOT repeat the chapter overview, the \"what is "
                "clustering\" definition, the hierarchical-methods "
                "overview, or the evaluation introduction across multiple "
                "slides. Two slides must never share the same title. Once a "
                "concept has its slide, move on — do not circle back to it "
                "near the end of the deck."
            )
            navigation_block = (
                "NAVIGATION & RECAP — author-curated lecture decks scaffold "
                "the learner. In ADDITION to the content slides include: "
                "(1) a \"Learning Objectives\" slide right after the opening "
                "intro, listing 3-5 measurable things the learner will be "
                "able to do; (2) a \"Key Takeaways\" recap slide at the very "
                "end summarizing the chapter's main results in 4-6 bullets. "
                "For a long chapter, add a one-line section-divider slide at "
                "each major section boundary. These are concise scaffolding, "
                "not new content."
            )
            audience_block = (
                "AUDIENCE & APPROPRIATENESS — write for one consistent learner "
                "level (infer it from the chapter's framing; do not drift "
                "between trivial and expert-terse). For every content slide:\n"
                "  - Define each technical term the FIRST time it appears, in "
                "one plain clause (e.g. \"a centroid (the mean point of a "
                "group)\"). Assume no prior vocabulary.\n"
                "  - Anchor each abstract idea with ONE concrete example or "
                "everyday analogy beside the formal statement — not only the "
                "textbook's numerical worked-examples.\n"
                "  - Teach the WHY or mechanism in at least one bullet, so a "
                "learner could reconstruct the idea, not just list facts."
            )
            textbook_hints = "\n\n".join(
                b for b in (
                    structure_block, audience_block, navigation_block,
                    topic_block, example_block, comparison_block,
                    forbidden_block, budget_block,
                ) if b
            )

        prompt = f"""
        Create a slides outline in JSON for the chapter below.

        Chapter Title: {chapter['title']}
        Chapter Description: {chapter['description']}

        User Feedback:
        {json.dumps(self.user_feedback, indent=2)}

        {textbook_hints}

        Generate about {target_count} slides covering the chapter in depth.
        Output strict JSON in this shape:

        {outline_template}

        Use simple, common LaTeX. Your response must be parseable JSON.
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

            # Drop duplicate-title slides the outline agent sometimes emits
            # (e.g. two "Applications of Cluster Analysis"); grounded path
            # only, so vanilla output is untouched.
            if self.retriever is not None:
                self.slides_outline = _dedupe_outline_titles(self.slides_outline)

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

        # Textbook grounding (no-op when self.retriever is None). Group the
        # evidence BY outline slide so the writer sees focused per-slide
        # context instead of one chapter-wide dump; fall back to the flat
        # chapter-level block when there's no outline / retriever / in-scope
        # results (preserves the vanilla no-op).
        evidence_block, _ = self._build_grouped_evidence_block(
            getattr(self, "slides_outline", None)
        )
        if not evidence_block:
            evidence_block, _ = self._build_evidence_block(
                f"{chapter['title']}. {chapter.get('description', '')}"
            )
        # Remember the exact evidence the writer was given so the content
        # verifier can check "did the writer stay faithful to THIS context?"
        # rather than re-retrieving coarsely on the chapter title.
        self._writer_evidence = evidence_block

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

        1. Don't use non-English characters directly, e.g. use $\\gamma$ instead of γ, $\\epsilon$ instead of ε
        2. If any of symbols has a special meaning, add a slash. e.g. use \\& instead of &

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
        # the SOFTER rule-set (paraphrase-naturally) since this is spoken
        # narration where a stiff written voice breaks flow.
        outline_query = " ".join(
            s.get("title", "") for s in self.slides_outline
        ) if self.slides_outline else ""
        evidence_block, _ = self._build_evidence_block(
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
        evidence_block, _ = self._build_evidence_block(
            f"{chapter['title']}. {chapter.get('description', '')}",
            artifact="assessment",
            cross_chapter=True,
        )

        # Grounded-path-only assessment-quality directives (author-curated
        # standard). Gated so the vanilla assessment prompt stays byte-identical.
        quality_block = ""
        if self.retriever is not None:
            quality_block = (
                "ASSESSMENT QUALITY — author-curated standard:\n"
                "- VARIETY: do NOT make every item multiple-choice. For each "
                "slide, mix in at least one short-answer, scenario/application, "
                "or compute-this item alongside any MCQ, and span cognitive "
                "levels (recall, application, analysis) rather than all recall.\n"
                "- FEEDBACK: for every multiple-choice item, explain why EACH "
                "distractor is wrong (a per-option rationale), not only why the "
                "correct answer is right, and point back to the relevant slide "
                "or section for remediation.\n"
                "- RUBRICS: every open-ended activity or discussion MUST ship "
                "with a short grading rubric (criteria + what full marks look "
                "like) and explicit deliverables, not a bare prompt.\n\n        "
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
        {quality_block}

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
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )

        # On grounded runs, the evidence block surfaces real cropped
        # figures via [IMAGE_PATH:] markers; the Faculty should reach
        # for them on every slide where a visual would teach better
        # than prose. Vanilla path receives no markers, so the line
        # below is harmless when ``self.retriever is None``.
        figure_directive = (
            "4. Figures from the textbook: when an excerpt above carries an "
            "[IMAGE_PATH: ...] marker, INCLUDE the figure with "
            "``\\includegraphics[width=0.55\\textwidth]{<exact path from the marker>}``. "
            "A figure must NEVER appear bare. Two things are MANDATORY for "
            "every figure you include:\n"
            "   (a) a bullet that INTRODUCES it — say in plain words what the "
            "figure shows and why it matters to this slide's point, BEFORE "
            "the \\includegraphics line;\n"
            "   (b) a ``\\caption{<one sentence describing what the reader is "
            "looking at>}`` line IMMEDIATELY AFTER the \\includegraphics, "
            "using the [DESCRIPTION: ...] marker text if the excerpt supplies "
            "one. A figure with no caption and no introduction reads as a "
            "random image and is a defect.\n"
            "   Keep your 3–5 concept bullets as usual; the figure supports "
            "them. If NO excerpt carries an [IMAGE_PATH: ...] marker, do NOT "
            "mention, promise, or gesture at a figure — write self-contained "
            "prose instead. Never end a bullet with \"as illustrated below\", "
            "\"can be shown graphically\", or a dangling colon expecting a "
            "picture that will not be there."
            if self.retriever is not None else
            "4. Any formulas, code snippets, or diagrams that would be helpful, but dont try to include any pictures in the LaTeX code."
        )

        # Clean-formatting directive — grounded path only (vanilla output
        # stays byte-identical). The textbook excerpts carry markdown
        # decoration (``_k_``, ``**bold**``, ``<<…>>``) from the source IR;
        # without this the Faculty copies it verbatim and it leaks onto the
        # rendered slide. Pair with RULE 2 (teach in your own words) and the
        # save-chain sanitizer.
        style_directive = (
            "\n5. Formatting: write clean prose for LaTeX slides. Do NOT use "
            "markdown syntax — no _underscores_ for emphasis, no **asterisks** "
            "for bold, no << >> quote markers, no `---` as a sentence "
            "separator. For mathematical symbols use LaTeX math mode "
            "(``$k \\leq n$``), never bare underscores. Write whole, "
            "self-contained sentences a student can read at a glance."
            if self.retriever is not None else ""
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
        {figure_directive}{style_directive}

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
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}"
        )
        # Adjacent-slide context — only injected on the grounded path
        # so the vanilla pipeline (no --use-textbook flag) stays
        # byte-identical to upstream behavior.
        adjacency_block = ""
        if self.retriever is not None:
            prev_outline = self.slides_outline[slide_idx - 1] if slide_idx > 0 else None
            next_outline = self.slides_outline[slide_idx + 1] if slide_idx + 1 < len(self.slides_outline) else None
            adjacency_lines = []
            if prev_outline:
                adjacency_lines.append(
                    f"Previous slide: {prev_outline.get('title', '')} — "
                    f"{prev_outline.get('description', '')[:120]}"
                )
            if next_outline:
                adjacency_lines.append(
                    f"Next slide:     {next_outline.get('title', '')} — "
                    f"{next_outline.get('description', '')[:120]}"
                )
            if adjacency_lines:
                adjacency_block = (
                    "\nAdjacent-slide context (for narrative continuity — feel free to "
                    "reference \"as discussed earlier\" / \"we will see next\"):\n  "
                    + "\n  ".join(adjacency_lines) + "\n"
                )
        prompt = f"{evidence_block}\n{base_prompt}{adjacency_block}"
        
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

        # Backstop the TA's attention-budget failure on figure preservation.
        # The Teaching Faculty's slide_draft often contains real
        # ``\includegraphics{...}`` commands sourced from the textbook's
        # VLM-extracted figures. The TA's prompt asks for preservation,
        # but with seven competing instructions the TA frequently drops
        # them. When the draft carries figures the rewritten frames lack,
        # append the missing commands to the last frame deterministically
        # so the visual content reaches slides.tex.
        draft_paths = _extract_includegraphics(slide_draft)
        if draft_paths and frame_matches:
            kept_paths = set(_extract_includegraphics("\n".join(frame_matches)))
            missing = [p for p in draft_paths if p not in kept_paths]
            if missing:
                last = frame_matches[-1]
                injection = "\n    " + "\n    ".join(
                    f"\\includegraphics[width=0.55\\textwidth]{{{p}}}"
                    for p in missing
                )
                frame_matches[-1] = last.replace(
                    "\\end{frame}", injection + "\n\\end{frame}", 1,
                )
                print(
                    f"[grounding] re-injected {len(missing)} draft figure(s) "
                    f"the TA dropped: {[p.rsplit('/',1)[-1] for p in missing]}"
                )

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
            
            # Extract the writer's actual \frametitle when available so
            # the metadata title reflects the distinct subtitle the TA
            # chose for each frame (e.g. "K-Means Algorithm", "K-Means
            # Complexity") rather than a mechanical "Slide - Part N"
            # suffix that read as draft artifacts in earlier baselines.
            for i, frame_code in enumerate(frame_matches):
                m = re.search(r"\\frametitle\{([^}]+)\}", frame_code)
                title = m.group(1).strip() if m else slide['title']
                self.latex_dict[slide_idx]["frames"].append({
                    "full_frame": frame_code,
                    "content": frame_code.replace("\\begin{frame}", "").replace("\\end{frame}", "").strip(),
                    "title": title,
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
        evidence_block, _ = self._build_per_slide_evidence(
            f"{slide['title']}. {slide.get('description', '')}",
            artifact="script",
        )

        # Grounded path adds the "expand, don't paraphrase" directive so
        # the script complements the slide instead of reading it aloud.
        # Vanilla path keeps the upstream-style enumerated guidance to
        # preserve byte-identical output without --use-textbook.
        if self.retriever is not None:
            script_directive = (
                "The audience can SEE the slide bullets in front of them — your job\n"
                "is to ADD value the slide can't carry on its own:\n"
                "1. Domain insight / why-this-matters framing the bullets don't spell out\n"
                "2. Real-world parallels or analogies that ground abstract definitions\n"
                "3. Smooth transitions between frames and to / from adjacent slides\n"
                "4. Where students typically stumble on this topic — what to flag\n"
                "5. Rhetorical prompts that pull the audience into the next slide\n\n"
                "Do NOT paraphrase the bullets back at the audience — that wastes\n"
                "their attention. Reading the slide out loud is the failure mode this\n"
                "script must avoid."
            )
        else:
            script_directive = (
                "Please generate a comprehensive speaking script for this slide that:\n"
                "1. Introduces the slide topic\n"
                "2. Explains all key points clearly and thoroughly\n"
                "3. If multiple frames exist, provides smooth transitions between frames\n"
                "4. Provides relevant examples or analogies\n"
                "5. Connects to previous or upcoming content\n"
                "6. Includes rhetorical questions or engagement points for students\n\n"
                "The script should be detailed enough for someone else to present effectively from it.\n"
                "If there are multiple frames, clearly indicate when to advance to the next frame."
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

        {script_directive}
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
        evidence_block, _ = self._build_evidence_block(
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
    