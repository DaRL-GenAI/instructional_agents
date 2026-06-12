"""Textbook knowledge base — load a textbook and turn it into chunks.

`TextbookKnowledgeBase.from_path(path)` accepts either a single PDF file, a
markdown file, or a directory of PDF/markdown files. It dispatches to the
right ingester (`src.textbook.ingest_pdf` or `src.textbook.ingest_md`),
holds the resulting `Textbook` IR, and exposes paragraph-aware chunks for
the retriever to index.

This module is deliberately retrieval-agnostic — it builds chunks but does
not score or rank them. The hybrid BM25 + dense retriever lives in
`src.grounding.retriever`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from src.textbook.schema import Chapter, Paragraph, Section, Textbook

# Chunking parameters. Paragraph-aware — a chunk is a contiguous span of
# paragraphs from one section, packed up to roughly TARGET_TOKENS, with
# OVERLAP_TOKENS of overlap between adjacent chunks. Token counts are
# approximated by `len(text.split())` to avoid pulling in `tiktoken`;
# this overestimates a little (≈ 1.3 words per token) which keeps us
# safely under the model's context budget downstream.
TARGET_TOKENS = 512
OVERLAP_TOKENS = 64

# Hard ceiling on chunk text size, enforced AFTER the paragraph-aware
# packing above. Most chunks stay well under TARGET_TOKENS; this ceiling
# only fires on edge cases where a SINGLE source paragraph is already
# huge — long visual captions with embedded descriptions, bibliography-
# style lists emitted whole by the ingester, or pre-formatted blocks that
# the PDF parser couldn't subdivide.
#
# 24000 characters ≈ 6000 tokens of English prose, which sits safely
# under OpenAI's 8192-token-per-input limit on the embedding models
# we use (text-embedding-3-small / -large). Oversized chunks get split
# into sub-chunks on real sentence boundaries (no information loss,
# citation tokens unchanged — sub-chunks share their parent's section
# and page span). See `_split_chunk_if_oversized` below.
MAX_CHUNK_CHARS = 24000


# Inline markers carried by paragraphs that came through the hybrid
# ingester's VLM augmentation. A paragraph containing any of these is
# emitted as its OWN small chunk rather than being bundled with the
# surrounding prose — so a query about a figure / equation / table /
# algorithm ranks the visual chunk directly rather than ranking a
# 500-token chunk that happens to contain the visual element as one
# small fraction.
_VISUAL_MARKERS = (
    "[IMAGE_PATH:", "[LATEX:", "[TABLE:", "[ALGORITHM_STEPS:",
)


def _is_visual_paragraph(p) -> bool:
    """True if the paragraph carries a hybrid-ingester visual marker."""
    return any(m in p.text for m in _VISUAL_MARKERS)


@dataclass
class Chunk:
    """One retrievable unit. Holds enough metadata to build a citation token."""

    chunk_id: str
    text: str
    textbook_id: str
    chapter_id: str
    chapter_title: str
    section_id: str
    section_title: str
    para_ids: List[str]            # contributing source paragraphs
    page_start: int
    page_end: int
    kinds: List[str] = field(default_factory=list)  # paragraph kinds present

    def citation_token(self) -> str:
        """Compact citation marker, suitable for injection into prompts.

        Form: `[textbook_id:section_id:p<page_start>]`. Stable across runs
        for the same source — the retriever, the writer, and the verifier
        all agree on the spelling.
        """
        return f"[{self.textbook_id}:{self.section_id}:p{self.page_start:02d}]"

    def citation_tokens_in_range(self) -> List[str]:
        """All citation tokens that resolve to this chunk.

        A chunk often spans multiple pages (a prose chunk can cover 2-3
        pages). The LLM is allowed to cite ANY page within the chunk's
        page range — the verifier's lookup index registers all such
        tokens against the same underlying chunk, so the LLM's choice
        of page (the one most relevant to its claim) doesn't fail
        resolution.
        """
        return [
            f"[{self.textbook_id}:{self.section_id}:p{page:02d}]"
            for page in range(self.page_start, self.page_end + 1)
        ]

    def page_range_label(self) -> str:
        """Human-readable label for the chunk's page span.

        Single-page chunks render as ``p<page>``; multi-page chunks as
        ``p<start>-p<end>``. Shown in the evidence block so the LLM
        can pick the most relevant page within the span.
        """
        if self.page_start == self.page_end:
            return f"p{self.page_start}"
        return f"p{self.page_start}-p{self.page_end}"

    def token_count(self) -> int:
        return len(self.text.split())


def _word_count(text: str) -> int:
    return len(text.split())


def _split_chunk_if_oversized(
    chunk: "Chunk", max_chars: int = MAX_CHUNK_CHARS
) -> List["Chunk"]:
    """Split a chunk's text on sentence boundaries when it exceeds
    ``max_chars``. Sub-chunks inherit the parent's section / page /
    chapter metadata, so their citation tokens are identical to the
    parent's — the ambiguous-token rescue in ``evaluate.py`` picks the
    best sibling at score time.

    Used as a final pass inside :func:`_paragraph_chunks` to guarantee
    every emitted chunk fits the embedder's per-input size limit
    (8192 tokens on OpenAI's embedding-3 family). Most calls return
    ``[chunk]`` unchanged; only outsized inputs get split.

    No information is dropped:
      - sentence-boundary splitting (via
        :func:`src.grounding.claim_window.split_into_sentences`) so we
        never break a sentence mid-clause;
      - if a SINGLE sentence is itself longer than ``max_chars`` (very
        rare — would have to be a single sentence > ~4000 words), we
        fall back to a hard slice as the absolute last resort and
        emit it with a marker so downstream code can flag the case.
    """
    if len(chunk.text) <= max_chars:
        return [chunk]

    from src.grounding.claim_window import split_into_sentences

    sentences = split_into_sentences(chunk.text)
    sub_chunks: List["Chunk"] = []

    def _new_sub(text: str, sub_idx: int) -> "Chunk":
        return Chunk(
            chunk_id=f"{chunk.chunk_id}_s{sub_idx:02d}",
            text=text,
            textbook_id=chunk.textbook_id,
            chapter_id=chunk.chapter_id,
            chapter_title=chunk.chapter_title,
            section_id=chunk.section_id,
            section_title=chunk.section_title,
            para_ids=list(chunk.para_ids),
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            kinds=list(chunk.kinds),
        )

    buf: List[str] = []
    buf_len = 0
    sub_idx = 0
    for s in sentences:
        # If a single sentence is larger than max_chars on its own,
        # split it at max_chars boundaries — last-resort hard slice.
        # Adds a "[truncated]" marker only to flag the rare case in
        # downstream logs; the text itself is fully preserved across
        # the resulting slices.
        if len(s) > max_chars:
            if buf:
                sub_chunks.append(_new_sub(" ".join(buf), sub_idx))
                sub_idx += 1
                buf, buf_len = [], 0
            for start in range(0, len(s), max_chars):
                slice_text = s[start : start + max_chars]
                sub_chunks.append(_new_sub(slice_text, sub_idx))
                sub_idx += 1
            continue
        if buf and buf_len + len(s) + 1 > max_chars:
            sub_chunks.append(_new_sub(" ".join(buf), sub_idx))
            sub_idx += 1
            buf = [s]
            buf_len = len(s)
        else:
            buf.append(s)
            buf_len += len(s) + 1
    if buf:
        sub_chunks.append(_new_sub(" ".join(buf), sub_idx))
    return sub_chunks


def _paragraph_chunks(section: Section, chapter: Chapter, textbook_id: str) -> Iterable[Chunk]:
    """Pack a section's paragraphs into chunks with two distinct shapes.

    Visual paragraphs (those carrying a hybrid-ingester marker like
    ``[IMAGE_PATH:`` or ``[LATEX:``) are emitted as their OWN
    standalone chunks — they're small (typically 30-150 tokens) and
    should rank directly for visual queries instead of being buried
    in a 500-token prose chunk.

    Non-visual paragraphs are packed greedily up to TARGET_TOKENS as
    before, with OVERLAP_TOKENS of overlap between adjacent prose
    chunks. Visual paragraphs interrupt the prose stream — a prose
    chunk ends at the boundary, the visual chunk fires, then a new
    prose chunk starts after the visual paragraph. Overlap is NOT
    applied across visual paragraphs (their content shouldn't bleed
    into adjacent prose chunks).
    """
    paras = section.paragraphs
    if not paras:
        return

    chunk_idx = 0

    def _emit(buf: List[Paragraph]) -> Chunk:
        nonlocal chunk_idx
        c = Chunk(
            chunk_id=f"{textbook_id}:{section.section_id}:c{chunk_idx:02d}",
            text="\n\n".join(p.text for p in buf),
            textbook_id=textbook_id,
            chapter_id=chapter.chapter_id,
            chapter_title=chapter.title,
            section_id=section.section_id,
            section_title=section.title,
            para_ids=[p.para_id for p in buf],
            page_start=min(p.page for p in buf),
            page_end=max(p.page for p in buf),
            kinds=sorted({p.kind for p in buf}),
        )
        chunk_idx += 1
        return c

    i = 0
    while i < len(paras):
        # Visual paragraphs get their own one-paragraph chunk.
        if _is_visual_paragraph(paras[i]):
            yield from _split_chunk_if_oversized(_emit([paras[i]]))
            i += 1
            continue

        # Pack consecutive non-visual paragraphs up to TARGET_TOKENS.
        # Stop at the first visual paragraph so it can emit its own chunk.
        buf: List[Paragraph] = []
        tokens = 0
        j = i
        while j < len(paras) and not _is_visual_paragraph(paras[j]):
            p_tokens = _word_count(paras[j].text)
            if buf and tokens + p_tokens > TARGET_TOKENS:
                break
            buf.append(paras[j])
            tokens += p_tokens
            j += 1

        if buf:
            yield from _split_chunk_if_oversized(_emit(buf))

        if j >= len(paras):
            break
        # If we stopped at a visual paragraph, advance to it (next loop
        # iteration handles it as a standalone chunk).
        if j < len(paras) and _is_visual_paragraph(paras[j]):
            i = j
            continue
        # Otherwise step forward; back up by ~OVERLAP_TOKENS so adjacent
        # prose chunks share context. Overlap stops at visual paragraphs
        # so their content doesn't bleed into the next prose chunk.
        if j == i:  # no progress (single paragraph > TARGET) — force advance
            j = i + 1
        overlap = 0
        k = j - 1
        while (k > i and overlap < OVERLAP_TOKENS
               and not _is_visual_paragraph(paras[k])):
            overlap += _word_count(paras[k].text)
            k -= 1
        i = max(k + 1, i + 1)


@dataclass
class TextbookKnowledgeBase:
    """A loaded textbook + its retrievable chunks."""

    textbook: Textbook
    chunks: List[Chunk]

    @property
    def textbook_id(self) -> str:
        return self.textbook.textbook_id

    def __len__(self) -> int:
        return len(self.chunks)

    def toc(self, word_budget: int = 400) -> str:
        """Formatted table of contents for prompt injection — see `Textbook.toc`."""
        return self.textbook.toc(word_budget=word_budget)

    @classmethod
    def from_path(cls, path: str | Path, *,
                  textbook_id: Optional[str] = None,
                  title: Optional[str] = None,
                  vlm_extractor=None,
                  ir_cache_dir: Optional[Path] = None,
                  use_ir_cache: bool = True) -> "TextbookKnowledgeBase":
        """Load a textbook from a file or directory and build chunks.

        Auto-dispatches by extension / directory contents:
          - `.pdf` file → PDF ingester (single book)
          - `.md` file → markdown ingester (single file)
          - directory of `*.pdf` → PDF ingester (one-chapter-per-file)
          - directory of `*.md` → markdown ingester (one-chapter-per-file)

        Args:
            vlm_extractor: Optional :class:`VlmExtractor` instance.
                When set AND the source is PDF, ingestion uses the
                hybrid path (PyMuPDF4LLM workhorse + VLM augmentation
                on pages flagged complex by the spatial router).
                When None, the existing plain-text ingester is used —
                vanilla path is byte-identical.
            ir_cache_dir: Where to read / write the cached Textbook IR.
                Defaults to ``<project>/.grounding_cache/``. The cache
                pins the parsed IR to disk on first ingestion so every
                subsequent call against the same source returns
                identical chunks — critical for the hybrid path where
                VLM extraction is not strictly deterministic across
                runs.
            use_ir_cache: If False, bypass the cache entirely and
                always re-ingest. Useful for one-off comparisons.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"textbook path does not exist: {p}")

        derived_id = textbook_id or _derive_id(p)
        derived_title = title or _derive_title(p)

        # Default cache location: <project>/.grounding_cache/
        if ir_cache_dir is None:
            ir_cache_dir = Path(__file__).resolve().parents[2] / ".grounding_cache"

        from src.grounding.ir_cache import load_ir, save_ir

        textbook: Optional[Textbook] = None
        if use_ir_cache:
            textbook = load_ir(ir_cache_dir, derived_id)
            if textbook is not None:
                print(
                    f"[grounding] Loaded IR for '{derived_id}' from cache "
                    f"({len(textbook.chapters)} chapters)."
                )
        if textbook is None:
            textbook = _ingest(p, derived_id, derived_title, vlm_extractor=vlm_extractor)
            if use_ir_cache:
                save_ir(ir_cache_dir, derived_id, textbook)
                print(
                    f"[grounding] Cached IR for '{derived_id}' "
                    f"({len(textbook.chapters)} chapters)."
                )

        chunks: List[Chunk] = []
        for chapter in textbook.chapters:
            for section in chapter.sections:
                chunks.extend(_paragraph_chunks(section, chapter, derived_id))

        # Operational diagnostic: how many chunks were split for the
        # embedder size limit, and what was the largest original input?
        # Surfaces silently-handled edge cases (long visual captions,
        # bibliography blocks) without forcing the operator to dig
        # through logs.
        split_count = sum(1 for c in chunks if "_s" in c.chunk_id.rsplit(":", 1)[-1])
        if split_count:
            max_len = max(len(c.text) for c in chunks)
            print(
                f"[grounding] {split_count} sub-chunks emitted from "
                f"oversized parent chunks (max chunk size after split: "
                f"{max_len} chars, ceiling: {MAX_CHUNK_CHARS}).",
                flush=True,
            )

        return cls(textbook=textbook, chunks=chunks)


def _ingest(p: Path, textbook_id: str, title: str, *, vlm_extractor=None) -> Textbook:
    # Lazy imports so importing this module doesn't pay PyMuPDF startup
    # cost when no textbook is in play.
    if p.is_file() and p.suffix.lower() == ".pdf":
        if vlm_extractor is not None:
            from src.textbook.ingest_pdf_hybrid import ingest_pdf_file_hybrid
            return ingest_pdf_file_hybrid(
                p, textbook_id=textbook_id, title=title,
                vlm_extractor=vlm_extractor,
            )
        from src.textbook.ingest_pdf import ingest_pdf_file
        return ingest_pdf_file(p, textbook_id=textbook_id, title=title)
    if p.is_file() and p.suffix.lower() in {".md", ".markdown"}:
        from src.textbook.ingest_md import ingest_file as ingest_md_file
        return ingest_md_file(p, textbook_id=textbook_id, title=title)
    if p.is_dir():
        pdfs = list(p.glob("*.pdf"))
        mds = list(p.glob("*.md")) + list(p.glob("*.markdown"))
        if pdfs and not mds:
            if vlm_extractor is not None:
                from src.textbook.ingest_pdf_hybrid import ingest_pdf_directory_hybrid
                return ingest_pdf_directory_hybrid(
                    p, textbook_id=textbook_id, title=title,
                    vlm_extractor=vlm_extractor,
                )
            from src.textbook.ingest_pdf import ingest_pdf_directory
            return ingest_pdf_directory(p, textbook_id=textbook_id, title=title)
        if mds and not pdfs:
            from src.textbook.ingest_md import ingest_directory as ingest_md_directory
            return ingest_md_directory(p, textbook_id=textbook_id, title=title)
        if pdfs and mds:
            raise ValueError(
                f"directory {p} contains both PDFs and markdown — mixed sources "
                "are not supported; split into separate textbooks."
            )
        raise ValueError(f"directory {p} contains no .pdf or .md files")
    raise ValueError(f"unsupported textbook path: {p} (need .pdf, .md, or a directory)")


_ID_SAFE = re.compile(r"[^a-z0-9]+")


def _derive_id(p: Path) -> str:
    # `.stem` is purely lexical (works on non-existent paths too), strips a
    # file extension if present, and degrades to `.name` for directories.
    return _ID_SAFE.sub("_", p.stem.lower()).strip("_") or "textbook"


def _derive_title(p: Path) -> str:
    return p.stem.replace("_", " ").replace("-", " ").strip().title() or "Untitled Textbook"
