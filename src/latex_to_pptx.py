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
    type: str  # 'text', 'itemize', 'enumerate', 'block', 'alertblock', 'code', 'math', 'tikz', 'columns'
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
    return text


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
    # Remove remaining unknown \commands (but preserve \\ as newline)
    text = re.sub(r'\\(?!\\)[a-zA-Z]+\*?(?:\{[^}]*\})*', '', text)
    # Inline math: keep as-is (raw LaTeX)
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
        return None

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

            # Itemize
            m = re.match(r'\\begin\{itemize\}(.*?)\\end\{itemize\}', content[pos:], re.DOTALL)
            if m:
                items = self._parse_items(m.group(1))
                elements.append(SlideElement(type='itemize', items=items))
                pos += m.end()
                continue

            # Enumerate
            m = re.match(r'\\begin\{enumerate\}(.*?)\\end\{enumerate\}', content[pos:], re.DOTALL)
            if m:
                items = self._parse_items(m.group(1))
                elements.append(SlideElement(type='enumerate', items=items))
                pos += m.end()
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

            # Math environments
            m = re.match(r'\\begin\{(equation\*?|align\*?|gather\*?)\}(.*?)\\end\{\1\}', content[pos:], re.DOTALL)
            if m:
                elements.append(SlideElement(type='math', content=m.group(2).strip()))
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
                # If the path doesn't resolve, silently skip (no broken image)
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
                r'((?:(?!\\begin\{)(?!\\includegraphics\b).)+)',
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

            if item['text'] or item['subitems']:
                items.append(item)

        return items

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
