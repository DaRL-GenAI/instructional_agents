"""Heading detection and table-of-contents extraction for markdown sources.

Walks a markdown document and returns the heading hierarchy as a flat list of
HeadingNode entries in source order. Used by ingest_md to drive chapter / section
segmentation when building a Textbook IR.

Target metric: TOC recall >= 0.9 on labeled fixtures (see tests/).
"""

from dataclasses import dataclass
from typing import List

from markdown_it import MarkdownIt


@dataclass
class HeadingNode:
    level: int           # 1 = chapter, 2 = section, 3+ = subsection
    title: str
    line_no: int         # 1-indexed line in the source


def parse_toc(md_text: str) -> List[HeadingNode]:
    """Parse markdown and return all headings in source order."""
    md = MarkdownIt()
    tokens = md.parse(md_text)
    headings: List[HeadingNode] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])  # 'h2' -> 2
            line_no = (tok.map[0] + 1) if tok.map else 0
            # Next token holds the inline content (the title text).
            if i + 1 < len(tokens) and tokens[i + 1].type == "inline":
                title = tokens[i + 1].content.strip()
            else:
                title = ""
            headings.append(HeadingNode(level=level, title=title, line_no=line_no))
            i += 3  # skip heading_open, inline, heading_close
        else:
            i += 1
    return headings
