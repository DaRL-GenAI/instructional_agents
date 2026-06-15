"""
LaTeX Beamer to PPTX Converter

Parses LaTeX Beamer .tex files and generates editable PowerPoint presentations
using pptxgenjs (Node.js) following the PPTX skill workflow.

Architecture: Python parser → JSON → Node.js pptxgenjs → .pptx
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Any

# Path to the Node.js builder script (co-located in src/)
_BUILD_SCRIPT = Path(__file__).resolve().parent / "build_pptx.js"


@dataclass
class SlideElement:
    type: str  # 'text', 'itemize', 'enumerate', 'block', 'alertblock', 'code', 'math', 'tikz', 'columns', 'image', 'caption'
    content: Any = None
    title: str = ''
    language: str = ''
    items: List[Any] = field(default_factory=list)
    children: List['SlideElement'] = field(default_factory=list)


@dataclass
class FrameData:
    title: str = ''
    elements: List[SlideElement] = field(default_factory=list)


def unescape_latex(text: str) -> str:
    """Convert LaTeX escape sequences to plain text."""
    text = re.sub(r'\\&', '&', text)
    text = re.sub(r'\\_', '_', text)
    text = re.sub(r'\\%', '%', text)
    text = re.sub(r'\\#', '#', text)
    text = re.sub(r'\\\\', '\n', text)
    text = re.sub(r'\\textbackslash\b\s*', r'\\', text)
    text = re.sub(r'\\\$', '$', text)
    text = re.sub(r'\\{', '{', text)
    text = re.sub(r'\\}', '}', text)
    text = re.sub(r'~', ' ', text)
    # Convert LaTeX-style backtick quotes to curly quotes:
    #   ``...''   → "..."   (double-backtick + double-apostrophe)
    #   `...'     → '...'   (single-backtick + single-apostrophe)
    # Beamer writers emit these literally; PPTX renders them as raw
    # backticks without conversion. Greedy is safe here because the
    # paired delimiters are distinct enough not to span unrelated text.
    text = re.sub(r"``([^']*?)''", r'"\1"', text)
    text = re.sub(r"`([^']*?)'(?!')", r"'\1'", text)
    # Empty / standalone double-dollar math the writer left behind ($$ with
    # no symbol between). Renders as literal "$$"; drop it.
    text = text.replace('$$', '')
    # LaTeX dash ligatures → unicode. In LaTeX "---" is an em-dash and
    # "--" an en-dash, but the PPTX path shows them as literal hyphens.
    # Convert so the common quote-then-gloss "..." --- gloss separator
    # renders as a real em-dash. Order matters: longest run first.
    text = re.sub(r'(?<!-)---(?!-)', '—', text)
    text = re.sub(r'(?<!-)--(?!-)', '–', text)
    return text


# Markdown-style bold/italic that the writer occasionally produces even
# inside .tex output. **bold** and __bold__ should render as plain bold
# inline text on the slide; in our pipeline they show as raw asterisks.
# Strip the markers and keep the content.
_MARKDOWN_BOLD_RE = re.compile(r'\*\*([^*\n]+?)\*\*')
_MARKDOWN_BOLD_UNDERSCORE_RE = re.compile(r'(?<!\w)__([^_\n]+?)__(?!\w)')
# Markdown italic with a single asterisk pair. Tighter — must not be
# adjacent to whitespace and content must be non-empty.
_MARKDOWN_ITALIC_RE = re.compile(r'(?<![*\w])\*([^*\n]+?)\*(?![*\w])')

# Bare $...$ math fences that survived through to the converter. In the
# native LaTeX → PDF path these would render as math. In our path we
# don't have a math renderer, so they leak as visible "$ 30$" text.
# Strip the fence; keep the content.
_BARE_DOLLAR_MATH_RE = re.compile(r'\$\s*([^$\n]{1,60})\s*\$')


# Markdown _italic_ (single-underscore pairs), e.g. "_k_-means". LaTeX
# treats a bare underscore as a subscript operator; the PPTX path leaks
# it as literal "_k_". Strip the markers, keep the content. Lookbehind
# excludes a preceding backslash (escaped ``\_``) or word char (real
# subscripts ``x_i`` and path underscores ``data_mining``); lookahead
# excludes a trailing word char so ``C_{ij}`` is left alone.
_MARKDOWN_ITALIC_UNDERSCORE_RE = re.compile(
    r"(?<![\\\w])_([A-Za-z][A-Za-z0-9 ()'.,/+-]{0,40}?)_(?![\w])"
)
# Guillemet quote markers (<<"...">>) the writer emits instead of plain
# quotes. Strip the angle pairs, keep the inner text.
_GUILLEMET_RE = re.compile(r'<<+\s*|\s*>>+')


def strip_markdown_artifacts(text: str) -> str:
    """Remove leftover markdown formatting that the writer included in
    .tex output and that LaTeX would have ignored (but the PPTX path
    renders as raw asterisks). Defensive: only matches bounded pairs."""
    text = _MARKDOWN_BOLD_RE.sub(r'\1', text)
    text = _MARKDOWN_BOLD_UNDERSCORE_RE.sub(r'\1', text)
    text = _MARKDOWN_ITALIC_RE.sub(r'\1', text)
    text = _MARKDOWN_ITALIC_UNDERSCORE_RE.sub(r'\1', text)
    text = _GUILLEMET_RE.sub('', text)
    return text


# LaTeX math symbols → unicode, used by clean_math_for_display so an
# equation/align block that survives to the PPTX path renders as readable
# text instead of raw "\begin{align*} \text{...} \\" source.
_MATH_SYMBOL_MAP = {
    r'\rightarrow': '→', r'\Rightarrow': '⇒', r'\leftarrow': '←',
    r'\leq': '≤', r'\geq': '≥', r'\neq': '≠', r'\approx': '≈',
    r'\times': '×', r'\cdot': '·', r'\pm': '±', r'\in': '∈',
    r'\notin': '∉', r'\subseteq': '⊆', r'\subset': '⊂',
    r'\cup': '∪', r'\cap': '∩', r'\sum': 'Σ', r'\prod': 'Π',
    r'\forall': '∀', r'\exists': '∃', r'\infty': '∞',
    r'\partial': '∂', r'\nabla': '∇', r'\sqrt': '√',
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
    r'\epsilon': 'ε', r'\varepsilon': 'ε', r'\theta': 'θ',
    r'\lambda': 'λ', r'\mu': 'μ', r'\sigma': 'σ', r'\phi': 'φ',
    r'\omega': 'ω', r'\pi': 'π', r'\rho': 'ρ', r'\tau': 'τ',
    r'\ldots': '…', r'\dots': '…', r'\cdots': '…',
}


def _convert_math_macros(text: str) -> str:
    """Convert the unambiguous math macros — ``\\frac``, ``\\sqrt``,
    operator names, braced sub/superscripts, and symbols — to readable
    unicode. Safe to run on general slide text (these only occur in math),
    so it also rescues bare formulas the writer emitted without ``$``
    delimiters, which the generic command-stripper would otherwise erase."""
    # \frac{a}{b} → (a)/(b); run twice for one level of nesting
    for _ in range(2):
        text = re.sub(r'\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}', r'(\1)/(\2)', text)
    # \sqrt{x} → √(x)
    text = re.sub(r'\\sqrt\s*\{([^{}]*)\}', r'√(\1)', text)
    text = text.replace('\\sqrt', '√')
    # Operator/function names: drop the backslash, keep the word
    text = re.sub(r'\\(max|min|log|ln|exp|arg|deg|gcd|lim|sup|inf|sin|cos|tan|det|dim|mod)\b', r'\1', text)
    # Braced sub/superscripts: keep the content, drop the marker (2^{n} → 2n)
    text = re.sub(r'[_^]\{([^{}]*)\}', r'\1', text)
    # Symbols → unicode. The negative lookahead stops a short macro matching
    # inside a longer command — e.g. \cap must NOT fire inside \caption.
    for macro, sym in _MATH_SYMBOL_MAP.items():
        text = re.sub(re.escape(macro) + r'(?![a-zA-Z])', sym, text)
    return text


def clean_math_for_display(text: str) -> str:
    """Turn a LaTeX math body into readable plain text.

    pptxgenjs has no math renderer, so math otherwise reaches the slide as
    raw source — ``\\begin{align*} \\text{Initial:} \\& \\quad...`` for a
    block, or ``\\frac{b(o)-a(o)}{\\max...}`` for an inline formula whose
    structural commands the generic command-stripper would erase entirely
    (leaving "s(o) ="). This converts structure (``\\frac``, ``\\text``,
    ``\\quad``, ``&`` alignment, ``\\\\`` rows, sub/superscripts) and maps
    symbols / operator names to unicode so the content stays legible.
    Returns '' when nothing survives."""
    text = _convert_math_macros(text)
    # \text{X} / \mathbf{X} / \mathrm{X} → X
    text = re.sub(r'\\(?:text|mathbf|mathrm|mathit|mathcal|mathbb|boldsymbol|operatorname)\{([^{}]*)\}', r'\1', text)
    # Row separators → newline; spacing macros → space
    text = text.replace('\\\\', '\n')
    text = re.sub(r'\\(?:quad|qquad)', '  ', text)
    text = re.sub(r'\\[,;:! ]', ' ', text)
    # Alignment markers (escaped or bare)
    text = text.replace('\\&', ' ')
    text = re.sub(r'(?<!\\)&', ' ', text)
    text = re.sub(r'\\(?:left|right|big|Big|bigg|Bigg)\b', '', text)
    # Unbraced subscripts/superscripts: keep the symbol, drop the marker
    text = re.sub(r'[_^]([A-Za-z0-9])', r'\1', text)
    # Any remaining \command → drop
    text = re.sub(r'\\[a-zA-Z]+', '', text)
    # Strip LaTeX grouping braces, but NOT escaped set-notation braces
    # (``\{a\}`` must survive as ``{a}``). The lookbehind protects ``\{``;
    # convert those to literal braces afterwards.
    text = re.sub(r'(?<!\\)[{}]', '', text)
    text = text.replace('\\{', '{').replace('\\}', '}')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n+', '\n', text)
    return text.strip()


# Inline / display math delimiters. Content is rendered to readable
# unicode via clean_math_for_display; this MUST run before the generic
# ``\command`` stripper so structural macros (\frac, \max) are converted
# rather than erased. Order: display forms first, then inline.
def render_inline_math(text: str) -> str:
    """Convert ``\\[...\\]``, ``$$...$$``, ``\\(...\\)`` and ``$...$`` to
    readable unicode text. Empty or unpaired delimiters are dropped so a
    stray ``$`` or literal ``\\( K \\)`` never reaches the slide."""
    text = re.sub(r'\\\[(.+?)\\\]', lambda m: clean_math_for_display(m.group(1)), text, flags=re.DOTALL)
    text = re.sub(r'\$\$(.+?)\$\$', lambda m: clean_math_for_display(m.group(1)), text, flags=re.DOTALL)
    text = re.sub(r'\\\((.+?)\\\)', lambda m: clean_math_for_display(m.group(1)), text, flags=re.DOTALL)
    text = re.sub(r'\$(.+?)\$', lambda m: clean_math_for_display(m.group(1)), text)
    # Drop any leftover empty / unpaired delimiters.
    text = text.replace('$$', '').replace('\\(', '').replace('\\)', '')
    text = text.replace('\\[', '').replace('\\]', '')
    text = re.sub(r'(?<!\\)\$', '', text)
    return text


def strip_bare_math_fences(text: str) -> str:
    """Replace ``$ value $`` with just ``value``. The writer sometimes
    used ``$\\geq 30$`` to write "≥ 30"; LaTeX would render this as math
    but the PPTX path can't, so the dollars leak as visible text. Strip
    the fences; keep the inner content."""
    return _BARE_DOLLAR_MATH_RE.sub(r'\1', text)


_PDF_DASH_NAME_RE = re.compile(r'^(.+?)\.pdf-(\d+)-(\d+)(\.[A-Za-z]+)$')
_FIGURE_PAGE_NAME_RE = re.compile(r'^(.+?)[._]p?(\d{3,4})[-_]\d+(\.[A-Za-z]+)$')


def _candidate_figure_basenames(name):
    """Alternative on-disk basenames for a figure the writer may have named
    under the wrong convention. Yields the name itself, then the
    ``<id>.pdf-<page>-<idx>`` → ``<id>_p<page>_<idx>`` normalization that
    matches how figures are actually written to ``.grounding_cache``."""
    if not name:
        return
    yield name
    m = _PDF_DASH_NAME_RE.match(name)
    if m:
        yield f"{m.group(1)}_p{m.group(2)}_{m.group(3)}{m.group(4)}"


def _figure_page_glob(name):
    """Glob for any figure on the same page as ``name`` (last-resort match
    when the exact panel index doesn't exist). Returns '' when the name
    carries no page number."""
    m = _FIGURE_PAGE_NAME_RE.match(name or "")
    if not m:
        return ""
    page = m.group(2)
    return f"*p{page}_*{m.group(3)}"


def strip_latex_formatting(text: str) -> str:
    """Strip LaTeX formatting commands, returning plain text."""
    # Remove commands that take arguments: \cmd{content} -> content
    for cmd in ['textbf', 'textit', 'texttt', 'emph', 'concept', 'hilight', 'underline']:
        text = re.sub(rf'\\{cmd}\{{([^}}]*)\}}', r'\1', text)
    # \textcolor{color}{content} -> content
    text = re.sub(r'\\textcolor\{[^}]*\}\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\colorbox\{[^}]*\}\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\href\{[^}]*\}\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\url\{([^}]*)\}', r'\1', text)
    text = re.sub(r'\\source\{([^}]*)\}', r'Source: \1', text)
    # Remove commands that eat content silently
    text = re.sub(r'\\footnote\{[^}]*\}', '', text)
    # Remove spacing/sizing commands
    text = re.sub(r'\\[vh]space\*?\{[^}]*\}', '', text)
    text = re.sub(r'\\hfill', '', text)
    text = re.sub(r'\\(tiny|small|normalsize|large|Large|LARGE|huge|Huge)\b', '', text)
    text = re.sub(r'\\(bfseries|itshape|ttfamily|mdseries|upshape|rmfamily|sffamily)\b', '', text)
    text = re.sub(r'\\separator', '---', text)
    # Remove counter/label commands
    text = re.sub(r'\\setcounter\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\addtocounter\{[^}]*\}\{[^}]*\}', '', text)
    text = re.sub(r'\\label\{[^}]*\}', '', text)
    text = re.sub(r'\\ref\{[^}]*\}', '', text)
    # Remove \centering, \raggedright, etc.
    text = re.sub(r'\\(centering|raggedright|raggedleft|noindent|newline|linebreak)\b', '', text)
    # Remove \rule{...}{...}
    text = re.sub(r'\\rule\{[^}]*\}\{[^}]*\}', '', text)
    # Remove % comments (LaTeX line comments)
    text = re.sub(r'%[^\n]*', '', text)
    # Remove remaining \begin{...} / \end{...} that leaked through
    text = re.sub(r'\\begin\{[^}]*\}', '', text)
    text = re.sub(r'\\end\{[^}]*\}', '', text)
    # Render inline/display math to readable unicode BEFORE the generic
    # command-strip below, otherwise structural macros inside a formula
    # (\frac, \max, \leq) get erased, leaving fragments like "s(o) =".
    text = render_inline_math(text)
    # Also rescue bare math macros the writer emitted without delimiters
    # (e.g. "s(o) = \frac{...}" on a line with no $); same erase risk.
    text = _convert_math_macros(text)
    # Remove remaining unknown \commands (but preserve \\ as newline).
    # Match optional ``[opt]`` argument first then any number of ``{arg}``
    # groups; that way a leftover ``\includegraphics[width=...]{path}``
    # gets fully stripped rather than leaving the bracket+brace tail as
    # visible text.
    text = re.sub(
        r'\\(?!\\)[a-zA-Z]+\*?(?:\[[^\]\n]*\])?(?:\{[^}]*\})*',
        '', text,
    )
    # Strip markdown leftovers (**bold**, __bold__, *italic*, _italic_).
    text = strip_markdown_artifacts(text)
    return unescape_latex(text).strip()


class LaTeXParser:
    """Parses LaTeX Beamer content into structured FrameData."""

    def __init__(self, source_dir: Optional[Path] = None):
        # Directory that contains the source .tex file. Used as the
        # primary search root when resolving \includegraphics paths
        # like ".grounding_cache/figures/foo.png".
        self.source_dir = Path(source_dir) if source_dir else None

    def _resolve_image_path(self, raw: str) -> Optional[Path]:
        """Resolve an \\includegraphics path to an existing file on disk.

        Search order:
          1. Path as given (absolute or relative to cwd).
          2. Relative to the .tex source directory.
          3. Walk up from source_dir to find ``.grounding_cache`` so
             paths the writer emits as ``.grounding_cache/figures/...``
             resolve from the project root regardless of where the
             .tex lives.

        Returns None if nothing on disk matches — caller silently drops
        the image so the PPTX still renders.
        """
        p = Path(raw)
        # Absolute first
        if p.is_absolute() and p.exists():
            return p.resolve()
        # Relative to current working directory
        if p.exists():
            return p.resolve()
        # Relative to .tex source directory (chapter dir)
        if self.source_dir is not None:
            candidate = self.source_dir / p
            if candidate.exists():
                return candidate.resolve()
            # Walk up looking for a directory that contains the
            # leading segment of the path (commonly ``.grounding_cache``)
            head = p.parts[0] if p.parts else ''
            cur = self.source_dir.resolve()
            for _ in range(6):  # cap the climb
                if (cur / head).exists():
                    candidate = cur / p
                    if candidate.exists():
                        return candidate.resolve()
                cur = cur.parent
                if cur == cur.parent:
                    break
        # Last resort: the writer often emits a figure under the wrong
        # naming convention (``<id>.pdf-0017-03.png`` instead of the
        # on-disk ``<id>_p0017_03.png``) or a non-existent panel index.
        # Find the figures directory and look for a normalized basename,
        # then any figure on the same page — so a near-miss path still
        # renders its figure instead of vanishing.
        figdir = self._figures_dir()
        if figdir is not None:
            for cand in _candidate_figure_basenames(Path(raw).name):
                hit = figdir / cand
                if hit.exists():
                    return hit.resolve()
            page_glob = _figure_page_glob(Path(raw).name)
            if page_glob:
                matches = sorted(figdir.glob(page_glob))
                if matches:
                    return matches[0].resolve()
        return None

    def _figures_dir(self) -> Optional[Path]:
        """Locate ``.grounding_cache/figures`` by walking up from the .tex
        source directory (cached). Returns None if not found."""
        cached = getattr(self, "_figdir_cache", "unset")
        if cached != "unset":
            return cached
        result = None
        base = self.source_dir or Path.cwd()
        cur = Path(base).resolve()
        for _ in range(8):
            cand = cur / ".grounding_cache" / "figures"
            if cand.is_dir():
                result = cand
                break
            if cur == cur.parent:
                break
            cur = cur.parent
        self._figdir_cache = result
        return result

    def parse(self, tex_content: str) -> List[FrameData]:
        """Parse a complete .tex file into a list of frames."""
        frames = []
        # Extract content between \begin{document} and \end{document}
        doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', tex_content, re.DOTALL)
        if not doc_match:
            return frames

        body = doc_match.group(1)

        # Extract individual frames
        frame_pattern = re.compile(
            r'\\begin\{frame\}(?:\[([^\]]*)\])?(?:\{([^}]*)\})?\s*(.*?)\\end\{frame\}',
            re.DOTALL
        )

        for match in frame_pattern.finditer(body):
            options = match.group(1) or ''
            inline_title = match.group(2) or ''
            content = match.group(3).strip()

            # Skip title page frames
            if '\\titlepage' in content or '\\maketitle' in content:
                continue

            frame = self._parse_frame(content, inline_title)
            if frame.title or frame.elements:
                frames.append(frame)

        # Also handle \frame{\titlepage} style
        return frames

    def _parse_frame(self, content: str, inline_title: str = '') -> FrameData:
        """Parse a single frame's content."""
        frame = FrameData()

        # Extract title
        title_match = re.search(r'\\frametitle\{([^}]*)\}', content)
        if title_match:
            frame.title = strip_latex_formatting(title_match.group(1))
            content = content[:title_match.start()] + content[title_match.end():]
        elif inline_title:
            frame.title = strip_latex_formatting(inline_title)

        # Parse the remaining content into elements
        frame.elements = self._parse_content(content)
        return frame

    def _parse_content(self, content: str) -> List[SlideElement]:
        """Parse content into a list of SlideElements."""
        elements = []
        pos = 0
        content = content.strip()

        while pos < len(content):
            # Skip whitespace
            ws_match = re.match(r'\s+', content[pos:])
            if ws_match:
                pos += ws_match.end()
                if pos >= len(content):
                    break

            # Try to match known environments
            matched = False

            # Block environment
            for block_type in ['block', 'alertblock', 'exampleblock']:
                pattern = re.compile(
                    rf'\\begin\{{{block_type}\}}\{{([^}}]*)\}}(.*?)\\end\{{{block_type}\}}',
                    re.DOTALL
                )
                m = pattern.match(content[pos:])
                if m:
                    elem = SlideElement(
                        type='block' if block_type == 'block' else block_type,
                        title=strip_latex_formatting(m.group(1)),
                        children=self._parse_content(m.group(2))
                    )
                    elements.append(elem)
                    pos += m.end()
                    matched = True
                    break

            if matched:
                continue

            # Itemize (depth-aware so nested itemize doesn't get cut at
            # the inner \end{itemize})
            consumed = self._match_balanced_env(content, pos, 'itemize')
            if consumed:
                inner, end_pos = consumed
                items = self._parse_items(inner)
                elements.append(SlideElement(type='itemize', items=items))
                pos = end_pos
                continue

            # Enumerate (same depth-aware match)
            consumed = self._match_balanced_env(content, pos, 'enumerate')
            if consumed:
                inner, end_pos = consumed
                items = self._parse_items(inner)
                elements.append(SlideElement(type='enumerate', items=items))
                pos = end_pos
                continue

            # Code listing
            m = re.match(
                r'\\begin\{lstlisting\}(?:\[([^\]]*)\])?\s*(.*?)\\end\{lstlisting\}',
                content[pos:], re.DOTALL
            )
            if m:
                lang = ''
                if m.group(1):
                    lang_match = re.search(r'language=(\w+)', m.group(1))
                    if lang_match:
                        lang = lang_match.group(1)
                elements.append(SlideElement(type='code', content=m.group(2).strip(), language=lang))
                pos += m.end()
                continue

            # Math environments. pptxgenjs can't typeset math, so flatten
            # the body to readable unicode text rather than dumping raw
            # LaTeX source onto the slide.
            m = re.match(r'\\begin\{(equation\*?|align\*?|gather\*?)\}(.*?)\\end\{\1\}', content[pos:], re.DOTALL)
            if m:
                cleaned = clean_math_for_display(m.group(2).strip())
                if cleaned:
                    elements.append(SlideElement(type='text', content=cleaned))
                pos += m.end()
                continue

            # TikZ
            m = re.match(r'\\begin\{tikzpicture\}(.*?)\\end\{tikzpicture\}', content[pos:], re.DOTALL)
            if m:
                elements.append(SlideElement(type='tikz', content=m.group(1).strip()))
                pos += m.end()
                continue

            # \includegraphics — embed real image files (PNG/JPG/PDF) into the
            # PPTX. Resolves the path relative to the chapter directory if
            # not absolute; falls back to project-root resolution since the
            # writer's prompts emit ".grounding_cache/figures/..." paths from
            # the project root.
            m = re.match(
                r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',
                content[pos:],
            )
            if m:
                raw_path = m.group(1).strip()
                resolved = self._resolve_image_path(raw_path)
                if resolved:
                    elements.append(SlideElement(type='image', content=str(resolved)))
                    pos += m.end()
                else:
                    # Path doesn't resolve: skip the image AND a caption that
                    # immediately follows it, so we don't leave an orphan
                    # "Figure. …" line with no picture above it.
                    pos += m.end()
                    drop = re.match(r'\s*\\caption\*?\{(?:.+?)\}\s*',
                                    content[pos:], re.DOTALL)
                    if drop:
                        pos += drop.end()
                continue

            # \caption{...} — the writer's figure description. Render it as
            # a caption line so figures carry context instead of floating
            # bare. (Outside a figure env \caption doesn't render in beamer,
            # and the generic command-strip would otherwise drop it.) Only
            # kept when the immediately-preceding element is an image —
            # otherwise it's an orphan caption (image failed to resolve).
            m = re.match(r'\\caption\*?\{(.+?)\}\s*', content[pos:], re.DOTALL)
            if m:
                cap = strip_latex_formatting(m.group(1))
                if cap and elements and elements[-1].type == 'image':
                    elements.append(SlideElement(type='caption', content=cap))
                pos += m.end()
                continue

            # Columns
            m = re.match(r'\\begin\{columns\}(.*?)\\end\{columns\}', content[pos:], re.DOTALL)
            if m:
                cols = self._parse_columns(m.group(1))
                elements.append(SlideElement(type='columns', children=cols))
                pos += m.end()
                continue

            # Table
            m = re.match(r'\\begin\{(tabular|table)\}(.*?)\\end\{\1\}', content[pos:], re.DOTALL)
            if m:
                elements.append(SlideElement(type='text', content='[Table - see LaTeX source]'))
                pos += m.end()
                continue

            # Center environment - parse contents
            m = re.match(r'\\begin\{center\}(.*?)\\end\{center\}', content[pos:], re.DOTALL)
            if m:
                inner = self._parse_content(m.group(1))
                elements.extend(inner)
                pos += m.end()
                continue

            # Skip other unknown environments
            m = re.match(r'\\begin\{(\w+)\}(.*?)\\end\{\1\}', content[pos:], re.DOTALL)
            if m:
                pos += m.end()
                continue

            # Text paragraph: consume until next \begin{, \includegraphics,
            # or end of content. \includegraphics needs its own stopper
            # so multiple images in one frame don't all get swallowed by
            # the first text run.
            text_match = re.match(
                r'((?:(?!\\begin\{)(?!\\includegraphics\b)(?!\\caption\b).)+)',
                content[pos:], re.DOTALL,
            )
            if text_match:
                text = text_match.group(1).strip()
                if text:
                    # Skip pure LaTeX commands with no visible text
                    clean = strip_latex_formatting(text)
                    if clean and not re.match(r'^[\s\\]*$', clean):
                        elements.append(SlideElement(type='text', content=clean))
                pos += text_match.end()
                continue

            # Fallback: advance one character
            pos += 1

        return elements

    def _parse_items(self, content: str) -> List[dict]:
        """Parse \\item entries from itemize/enumerate, supporting nesting."""
        items = []

        # Find all \item positions (not inside nested environments)
        item_positions = []
        depth = 0
        i = 0
        while i < len(content):
            # Track nesting depth
            m_begin = re.match(r'\\begin\{(itemize|enumerate)\}', content[i:])
            m_end = re.match(r'\\end\{(itemize|enumerate)\}', content[i:])
            if m_begin:
                depth += 1
                i += m_begin.end()
                continue
            if m_end:
                depth -= 1
                i += m_end.end()
                continue
            # Only match \item at depth 0 (top level of this list)
            m_item = re.match(r'\\item\s*', content[i:])
            if m_item and depth == 0:
                item_positions.append(i + m_item.end())
                i += m_item.end()
                continue
            i += 1

        if not item_positions:
            return items

        # Extract each item's content (from after \item to start of next \item or end)
        for idx, start in enumerate(item_positions):
            if idx + 1 < len(item_positions):
                # Find the \item keyword before the next position
                next_item_match = re.search(r'\\item\s*', content[item_positions[idx + 1] - 10:item_positions[idx + 1] + 1])
                end = item_positions[idx + 1] - len(next_item_match.group()) if next_item_match else item_positions[idx + 1]
                # Simpler: just search backwards for \item
                end = content.rfind('\\item', start, item_positions[idx + 1] + 1)
                if end == -1:
                    end = item_positions[idx + 1]
            else:
                end = len(content)

            part = content[start:end].strip()
            if not part:
                continue

            item = {'text': '', 'subitems': []}

            # Check for nested itemize/enumerate (use greedy match with balanced tracking)
            nested_match = self._find_nested_env(part)
            if nested_match:
                before = part[:nested_match[0]].strip()
                item['text'] = strip_latex_formatting(before)
                item['subitems'] = self._parse_items(nested_match[2])
            else:
                item['text'] = strip_latex_formatting(part)

            # Drop empty items so they don't render as a lone "•" bullet
            # on the slide. We accept "text is empty AND subitems is
            # empty" as the empty signal, and also strip items whose
            # text is only punctuation/whitespace.
            cleaned_text = (item['text'] or '').strip()
            if not cleaned_text and not item['subitems']:
                continue
            # Whitespace-or-punct-only text counts as empty too
            if cleaned_text and not re.search(r'\w', cleaned_text):
                if not item['subitems']:
                    continue
                # Keep subitems but null out the noise text
                item['text'] = ''
            items.append(item)

        return items

    def _match_balanced_env(self, content: str, pos: int, env_name: str):
        """Match \\begin{env}...\\end{env} starting at content[pos] with
        balanced depth tracking. Returns (inner_content, end_pos) or None.
        Used by _parse_content so a nested itemize doesn't get truncated at
        its inner \\end{itemize}."""
        m_open = re.match(rf'\\begin\{{{env_name}\}}', content[pos:])
        if not m_open:
            return None
        search_start = pos + m_open.end()
        depth = 1
        i = search_start
        while i < len(content) and depth > 0:
            m_b = re.match(rf'\\begin\{{{env_name}\}}', content[i:])
            m_e = re.match(rf'\\end\{{{env_name}\}}', content[i:])
            if m_b:
                depth += 1
                i += m_b.end()
            elif m_e:
                depth -= 1
                if depth == 0:
                    inner = content[search_start:i]
                    return (inner, i + m_e.end())
                i += m_e.end()
            else:
                i += 1
        return None

    def _find_nested_env(self, text: str):
        """Find the first nested itemize/enumerate environment, handling balanced nesting.
        Returns (start, end, inner_content) or None."""
        m = re.search(r'\\begin\{(itemize|enumerate)\}', text)
        if not m:
            return None

        env_name = m.group(1)
        start = m.start()
        search_start = m.end()
        depth = 1

        pos = search_start
        while pos < len(text) and depth > 0:
            m_begin = re.match(rf'\\begin\{{{env_name}\}}', text[pos:])
            m_end = re.match(rf'\\end\{{{env_name}\}}', text[pos:])
            if m_begin:
                depth += 1
                pos += m_begin.end()
            elif m_end:
                depth -= 1
                if depth == 0:
                    inner = text[search_start:pos]
                    end = pos + m_end.end()
                    return (start, end, inner)
                pos += m_end.end()
            else:
                pos += 1

        return None

    def _parse_columns(self, content: str) -> List[SlideElement]:
        """Parse \\begin{column} blocks within columns environment."""
        cols = []
        col_pattern = re.compile(
            r'\\begin\{column\}\{[^}]*\}(.*?)\\end\{column\}', re.DOTALL
        )
        for m in col_pattern.finditer(content):
            col_content = self._parse_content(m.group(1))
            cols.append(SlideElement(type='column', children=col_content))
        return cols


class PPTXBuilder:
    """Builds a PPTX by serializing frames to JSON and calling pptxgenjs via Node.js."""

    def __init__(self):
        pass

    @staticmethod
    def _serialize_element(elem: 'SlideElement') -> dict:
        """Recursively serialize a SlideElement to a JSON-safe dict."""
        d = {
            'type': elem.type,
            'content': elem.content,
            'title': elem.title,
            'language': elem.language,
        }
        if elem.items:
            d['items'] = []
            for item in elem.items:
                if isinstance(item, dict):
                    d['items'].append(item)
                else:
                    d['items'].append({'text': str(item)})
        else:
            d['items'] = []

        d['children'] = [PPTXBuilder._serialize_element(c) for c in elem.children]
        return d

    @staticmethod
    def _serialize_frames(frames: List['FrameData']) -> list:
        """Serialize a list of FrameData to JSON-safe list."""
        return [
            {
                'title': f.title,
                'elements': [PPTXBuilder._serialize_element(e) for e in f.elements],
            }
            for f in frames
        ]

    def build(self, frames: List['FrameData'], output_path: str) -> str:
        """Build PPTX by calling Node.js pptxgenjs script."""
        # Find node binary
        node_bin = shutil.which('node')
        if not node_bin:
            raise RuntimeError("Node.js not found. Install Node.js to generate PPTX files.")

        if not _BUILD_SCRIPT.exists():
            raise RuntimeError(f"Build script not found: {_BUILD_SCRIPT}")

        # Resolve output path to absolute
        output_path = str(Path(output_path).resolve())

        # Serialize frames to JSON
        payload = json.dumps({
            'outputPath': output_path,
            'frames': self._serialize_frames(frames),
        }, ensure_ascii=False)

        # Get global npm modules path for NODE_PATH
        env = os.environ.copy()
        try:
            npm_root = subprocess.run(
                ['npm', 'root', '-g'], capture_output=True, text=True, timeout=10
            )
            if npm_root.returncode == 0:
                env['NODE_PATH'] = npm_root.stdout.strip()
        except Exception:
            pass

        # Run pptxgenjs builder
        result = subprocess.run(
            [node_bin, str(_BUILD_SCRIPT)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"pptxgenjs build failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )

        return output_path




class LaTeXToPPTXConverter:
    """Main converter: LaTeX Beamer .tex → .pptx"""

    def __init__(self):
        self.parser = LaTeXParser()

    def convert(self, tex_path: str, output_path: Optional[str] = None) -> str:
        """
        Convert a LaTeX Beamer .tex file to .pptx.

        Args:
            tex_path: Path to the .tex file
            output_path: Output .pptx path. If None, uses same dir with .pptx extension.

        Returns:
            Path to the generated .pptx file
        """
        tex_path = Path(tex_path)
        if not tex_path.exists():
            raise FileNotFoundError(f"TeX file not found: {tex_path}")

        if output_path is None:
            output_path = str(tex_path.with_suffix('.pptx'))

        tex_content = tex_path.read_text(encoding='utf-8')
        # Give the parser the .tex file's directory so it can resolve
        # \includegraphics paths emitted relative to that location or to
        # an ancestor (typically the project root containing
        # .grounding_cache/figures/).
        self.parser.source_dir = tex_path.resolve().parent
        frames = self.parser.parse(tex_content)

        if not frames:
            print(f"Warning: No frames found in {tex_path}")
            return output_path

        builder = PPTXBuilder()
        builder.build(frames, output_path)
        print(f"Generated PPTX: {output_path} ({len(frames)} slides)")
        return output_path

    def convert_directory(self, directory: str) -> List[str]:
        """
        Convert all slides.tex files in chapter subdirectories.

        Scans directory for chapter_*/slides.tex and converts each to slides.pptx
        in the same subdirectory.

        Args:
            directory: Path to the experiment/course directory

        Returns:
            List of generated .pptx file paths
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        generated = []
        tex_files = sorted(dir_path.glob('chapter_*/slides.tex'))

        if not tex_files:
            # Also try root-level .tex files
            tex_files = sorted(dir_path.glob('*.tex'))

        if not tex_files:
            print(f"No .tex files found in {directory}")
            return generated

        for tex_file in tex_files:
            try:
                output = self.convert(str(tex_file))
                generated.append(output)
            except Exception as e:
                print(f"Error converting {tex_file}: {e}")

        print(f"\nConverted {len(generated)}/{len(tex_files)} files to PPTX")
        return generated
