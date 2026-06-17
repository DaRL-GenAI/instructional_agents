"""Advisory content-fidelity verifier — the citation-free grounding signal.

Replaces the citation-token apparatus. After a chapter's artifacts are written,
this segments the generated slides/script into claims and asks a gpt-4o judge
which claims are NOT supported by the chapter's retrieved textbook evidence. It
LOGS a per-chapter report (``content_verification.json``) — advisory only: it
never edits the artifacts and never blocks the save. Fail-open on any error.

Grounded path only — the slides hook that calls this is gated behind a present
retriever + verifier, so the vanilla (no-textbook) pipeline never touches it.
"""

from __future__ import annotations

import json
import re
from typing import List, Optional

# Sentence boundary; LaTeX command stripper; visual-marker line prefixes.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
_VISUAL_LINE_PREFIXES = ("[IMAGE_PATH:", "[LATEX:", "[TABLE:", "[ALGORITHM_STEPS:")
_MAX_CLAIMS = 50


def _segment_claims(text: str) -> List[str]:
    """Split an artifact into checkable claim strings. Splits on \\item,
    markdown bullets, newlines, and sentence enders; strips LaTeX commands; and
    DROPS pure-figure / visual-marker lines so figures are never judged as
    claims. Capped at ``_MAX_CLAIMS``."""
    if not text:
        return []
    claims: List[str] = []
    norm = re.sub(r"\\item\b", "\n", text)
    norm = re.sub(r"(?m)^\s*[-*•]\s+", "\n", norm)
    for line in norm.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("\\includegraphics") or any(
            p in line for p in _VISUAL_LINE_PREFIXES
        ):
            continue
        for sent in _SENTENCE_SPLIT_RE.split(line):
            s = _LATEX_CMD_RE.sub(" ", sent)
            s = re.sub(r"[{}$\\]", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            if len(s.split()) >= 4:  # skip titles / fragments
                claims.append(s)
            if len(claims) >= _MAX_CLAIMS:
                return claims
    return claims


def _parse_json(resp: str):
    """Defensive JSON parse: try whole, else the first brace-wrapped block."""
    if not resp:
        return {}
    try:
        return json.loads(resp)
    except Exception:
        pass
    m = re.search(r"\{.*\}", resp, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


_VERIFIER_SYSTEM = (
    "You are a content-fidelity checker. Given numbered EVIDENCE excerpts from a "
    "textbook and a numbered list of CLAIMS taken from generated lecture slides, "
    "identify which claims are NOT supported by the evidence (factually "
    "unsupported, contradicted, or invented specifics / topical drift). Reply "
    'with ONLY JSON of the form {"unsupported": [{"index": N, "claim": "...", '
    '"reason": "..."}]}. An empty list means every claim is supported.'
)


class ContentVerifier:
    """Per-chapter advisory content-fidelity check against retrieved evidence."""

    def __init__(self, retriever=None, llm=None, model: str = "gpt-4o"):
        self.retriever = retriever
        self.model = model
        if llm is not None:
            self.llm = llm
        else:
            from src.agents import LLM
            self.llm = LLM(model_name=model)

    def _evidence_block(self, chapter_title: str, section_ids) -> str:
        if self.retriever is None:
            return ""
        try:
            results = self.retriever.search(
                chapter_title, top_k=12, section_ids=section_ids
            )
        except TypeError:
            results = self.retriever.search(chapter_title, top_k=12)
        except Exception:
            return ""
        lines = []
        for i, r in enumerate(results, 1):
            ch = r.chunk
            try:
                pg = ch.page_range_label()
            except Exception:
                pg = ""
            lines.append(
                f"[E{i}] (section {getattr(ch, 'section_title', '')}, {pg}) "
                f"{(ch.text or '')[:400]}"
            )
        return "\n".join(lines)

    def verify_chapter(self, chapter_id, chapter_title, artifacts: dict,
                       section_ids, writer_evidence=None) -> dict:
        """Check the chapter's claims against its evidence. Advisory + log-only:
        never mutates ``artifacts``. Fail-open — any error returns a zero-count
        report with an ``error`` field instead of raising.

        When ``writer_evidence`` is supplied (the exact evidence block the
        writer was given), claims are checked against THAT — i.e. "did the
        writer stay faithful to the context it had?", the correct grounding
        question. Falls back to a fresh chapter-title retrieval only when no
        writer evidence is passed (which re-searches coarsely on the title and
        can false-flag legitimate slides)."""
        report = {
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            "claims_checked": 0,
            "unsupported_claim_count": 0,
            "flagged_claims": [],
            "summary": "",
            "model": self.model,
        }
        claims: List[str] = []
        for text in (artifacts or {}).values():
            claims.extend(_segment_claims(text or ""))
        claims = claims[:_MAX_CLAIMS]
        report["claims_checked"] = len(claims)
        if not claims or self.llm is None:
            report["summary"] = "no claims to check"
            return report
        evidence = (writer_evidence if writer_evidence
                    else self._evidence_block(chapter_title, section_ids))
        numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1))
        user = f"EVIDENCE:\n{evidence}\n\nCLAIMS:\n{numbered}\n\nReturn the JSON."
        try:
            resp, _elapsed, _tokens = self.llm.generate_response(
                [
                    {"role": "system", "content": _VERIFIER_SYSTEM},
                    {"role": "user", "content": user},
                ],
                False,
            )
            data = _parse_json(resp)
            flagged = data.get("unsupported", []) if isinstance(data, dict) else []
            report["flagged_claims"] = flagged[:_MAX_CLAIMS]
            report["unsupported_claim_count"] = len(report["flagged_claims"])
            n, u = report["claims_checked"], report["unsupported_claim_count"]
            report["summary"] = f"{n - u}/{n} claims supported ({u} flagged)"
        except Exception as e:  # fail-open — never block the save
            report["error"] = f"{type(e).__name__}: {e}"
            report["summary"] = "verification failed (fail-open)"
        return report


def report_line(report: dict) -> str:
    """One-line console summary of a verify_chapter report."""
    base = f"[content-verify] {report.get('chapter_id', '?')}: {report.get('summary', '')}"
    return base + (f" — ERROR {report['error']}" if report.get("error") else "")
