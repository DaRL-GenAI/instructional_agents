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
import unicodedata
from typing import List, Optional

# Sentence boundary; LaTeX command stripper; visual-marker line prefixes.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
# Text-carrying commands are unwrapped (argument kept) BEFORE the generic
# strip, so "\textbf{mode} is ..." yields "mode is ..." rather than " is ...".
_TEXT_WRAP_RE = re.compile(
    r"\\(?:textbf|textit|emph|alert|texttt|textsc|textsl|underline)"
    r"\{([^{}]*)\}")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
# Beamer template residue that survives brace-stripping is never a claim.
_BEAMER_JUNK_RE = re.compile(r"head/foot|\bwd=|\bht=\d|\bdp=\d")
_VISUAL_LINE_PREFIXES = ("[IMAGE_PATH:", "[LATEX:", "[TABLE:", "[ALGORITHM_STEPS:")
# Titles and frame headings are NOT claims: strip the argument of every
# title-carrying command, and the inline title of \begin{frame}[..]{Title}.
_TITLE_CMD_RE = re.compile(
    r"\\(?:frametitle|framesubtitle|section|subsection|subsubsection|title|"
    r"author|date|paragraph)\*?\{(?:[^{}]|\{[^{}]*\})*\}")
_FRAME_INLINE_TITLE_RE = re.compile(
    r"(\\begin\{frame\}(?:\[[^\]]*\])?)\{(?:[^{}]|\{[^{}]*\})*\}")
_MD_HEADING_RE = re.compile(r"(?m)^\s*#+\s.*$")
_BOLD_ONLY_LINE_RE = re.compile(r"(?m)^\s*\*\*[^*]+\*\*\s*$")
# Beamer block titles are headings too: \begin{block}{Title} etc.
_BLOCK_TITLE_RE = re.compile(
    r"(\\begin\{(?:block|alertblock|exampleblock)\})\{(?:[^{}]|\{[^{}]*\})*\}")
# A dangling list introducer asserts nothing ("A few examples include:").
_INTRODUCER_TAIL_RE = re.compile(
    r"\b(?:include|includes|including|such as|as follows|the following|"
    r"consider|are|namely)\s*:?\s*$", re.IGNORECASE)
_TITLE_STOPWORDS = frozenset(
    "a an the of and or in on to for with vs via".split())
# Not factual claims: headless "term: definition" residue (the bolded term was
# a LaTeX arg the stripper removed), mangled math residue, and course
# meta-discourse (learning objectives, agenda talk).
_HEADLESS_RE = re.compile(r"^:")
_MANGLED_RE = re.compile(r"\s,\s|=\s*(?:and|or|,)\b|\(\s*\)")
_IMPERATIVE_RE = re.compile(
    r"^(?:Clarify|Reflect|Identify|Understand|Learn|Discuss|Explore|Recognize|"
    r"Describe|Explain|Apply|Analyze|Evaluate|Develop|Gain|Comprehend|"
    r"Demonstrate|Define|Compare|Master|Summarize|Compute|Calculate|Review|"
    r"Practice|Interpret)\b")
_META_DISCOURSE_RE = re.compile(
    r"^(?:In this (?:section|chapter|week|course|lecture)|"
    r"This (?:section|chapter|week|lecture|course)\b|"
    r"We will\b|Students will\b|Participants will\b|Learners will\b|"
    r"The (?:lecture|session|module) will\b|"
    r"You will (?:learn|be able)\b|Let'?s\b|Welcome\b|Today,? we)")
_MAX_CLAIMS = 50


def _segment_claims(text: str, limit: Optional[int] = _MAX_CLAIMS) -> List[str]:
    """Split an artifact into checkable claim strings. Splits on \\item,
    markdown bullets, newlines, and sentence enders; strips LaTeX commands; and
    DROPS pure-figure / visual-marker lines so figures are never judged as
    claims.

    Stops at ``limit`` claims; pass ``limit=None`` to segment the whole text,
    which is how the caller learns how much of a document the capped
    verification actually covered."""
    if not text:
        return []
    claims: List[str] = []
    # Claims live in sentences, not headings: drop titles/frames first.
    text = _TITLE_CMD_RE.sub(" ", text)
    text = _FRAME_INLINE_TITLE_RE.sub(r"\1", text)
    text = _MD_HEADING_RE.sub(" ", text)
    text = _BOLD_ONLY_LINE_RE.sub(" ", text)
    text = _BLOCK_TITLE_RE.sub(r"\1", text)
    norm = re.sub(r"\\item\b", "\n", text)
    norm = re.sub(r"(?m)^\s*[-*•]\s+", "\n", norm)
    for line in norm.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("%"):  # LaTeX comment, not content
            continue
        if line.startswith("\\includegraphics") or any(
            p in line for p in _VISUAL_LINE_PREFIXES
        ):
            continue
        for sent in _SENTENCE_SPLIT_RE.split(line):
            sent = _TEXT_WRAP_RE.sub(r"\1", sent)
            sent = _TEXT_WRAP_RE.sub(r"\1", sent)  # one nesting level
            s = _LATEX_CMD_RE.sub(" ", sent)
            s = re.sub(r"[{}$\\]", "", s)
            s = re.sub(r"\s+", " ", s).strip()
            if _BEAMER_JUNK_RE.search(s):
                continue
            words = s.split()
            alpha = sum(1 for w in words if re.search(r"[a-zA-Z]{2,}", w))
            if len(words) < 4 or alpha < 3:  # too short to be a sentence
                continue
            if s.endswith(":") or _INTRODUCER_TAIL_RE.search(s):
                continue  # list lead-in, not a claim
            if (_HEADLESS_RE.match(s) or _MANGLED_RE.search(s)
                    or _IMPERATIVE_RE.match(s) or _META_DISCOURSE_RE.match(s)):
                continue  # headless/mangled residue or course meta-discourse
            if len(words) <= 8 and not s[-1] in ".!?":
                caps = [w for w in words if w.lower() not in _TITLE_STOPWORDS]
                if caps and sum(1 for w in caps if w[:1].isupper()) / len(caps) >= 0.6:
                    continue  # Title-Case heading bullet, not a claim
            claims.append(s)
            if limit is not None and len(claims) >= limit:
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
    "You are a content-fidelity checker. Given EVIDENCE excerpts from a "
    "textbook and a numbered list of CLAIMS taken from generated lecture "
    "slides, return a verdict for EVERY claim. A claim counts as supported "
    "only if the evidence itself backs it — being true in the world is not "
    "enough. Reply with ONLY JSON of the form "
    '{"claims": [{"index": N, "verdict": "supported", "quote": "..."}, '
    '{"index": M, "verdict": "unsupported", "reason": "..."}]}. '
    'For every supported verdict, "quote" MUST be a verbatim passage copied '
    "from the EVIDENCE (at least 4 words) that backs the claim; a supported "
    "verdict without a verbatim quote is invalid. For every unsupported "
    "verdict, give a brief reason (factually unsupported, contradicted, or "
    "invented specifics / topical drift)."
)

# Quote-anchored passes: a "supported" verdict must carry a verbatim evidence
# quote, checked deterministically after normalization. Anything shorter than
# _QUOTE_MIN_WORDS could anchor spuriously ("of the data").
_QUOTE_MIN_WORDS = 4
# Second-chance passes are asked about a handful of claims at a time so the
# judge can actually re-read the source for each one.
_SECOND_CHANCE_BATCH = 15

_REQUOTE_SYSTEM = (
    "You are a quotation checker. You are given EVIDENCE (source text) and "
    "numbered CLAIMS previously judged as supported by it. Your ONLY task: "
    "for each claim, COPY the exact contiguous passage from the EVIDENCE (at "
    "least 4 words, character for character) that backs it. Do not "
    "paraphrase, do not merge separate sentences. If no contiguous passage "
    "backs the claim, mark it unsupported. Reply with ONLY JSON: "
    '{"claims": [{"index": N, "verdict": "supported", "quote": "..."} or '
    '{"index": N, "verdict": "unsupported", "reason": "..."}]}'
)
_RECHECK_SYSTEM = (
    "You are a support finder. You are given EVIDENCE (source text) and "
    "numbered CLAIMS previously flagged as NOT supported. Search the evidence "
    "carefully: support may be phrased differently, use a different example, "
    "or sit far from related passages. If a contiguous passage (at least 4 "
    "words) genuinely backs the claim, reply supported and COPY that passage "
    "exactly. Otherwise confirm unsupported. Reply with ONLY JSON: "
    '{"claims": [{"index": N, "verdict": "supported", "quote": "..."} or '
    '{"index": N, "verdict": "unsupported", "reason": "..."}]}'
)


def _norm_for_anchor(text: str) -> str:
    """Normalize for verbatim-quote matching: fold unicode compatibility forms
    (PDF ligatures like ﬁ → fi), lowercase, non-alphanumerics to single
    spaces. Tolerates punctuation/whitespace/LaTeX-residue differences while
    still requiring real verbatim overlap."""
    folded = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def _quote_anchored(quote: str, evidence_norm: str) -> bool:
    q = _norm_for_anchor(quote)
    if len(q.split()) < _QUOTE_MIN_WORDS:
        return False
    if q in evidence_norm:
        return True
    # PDF extraction leaves glued words ("Google'sFlu Trends") that break
    # space-sensitive matching; compare letter sequences with spaces removed.
    # Paraphrase and fabrication still fail — the character stream must match.
    return q.replace(" ", "") in evidence_norm.replace(" ", "")


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

    def bound_section_text(self, section_ids) -> str:
        """Full text of every chunk in the bound sections, in book order.

        This is the strongest evidence the pipeline can offer a judge without
        an external file: the complete source the chapter was allowed to draw
        from, rather than a handful of retrieved excerpts. Judging against a
        narrow excerpt window saturates — generic claims find backing and
        specific ones fail for reasons unrelated to the writer — so callers
        that can afford the tokens should prefer this."""
        kb = getattr(self.retriever, "kb", None)
        if kb is None or not section_ids:
            return ""
        wanted = set(section_ids)
        chunks = [c for c in kb.chunks if c.section_id in wanted]
        chunks.sort(key=lambda c: (getattr(c, "page_start", 0) or 0,
                                   c.chunk_id))
        seen, parts = set(), []
        for c in chunks:
            t = (c.text or "").strip()
            if t and t not in seen:
                seen.add(t)
                parts.append(t)
        return "\n\n".join(parts)

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

    def _second_chance(self, system: str, items, evidence: str,
                       evidence_norm: str) -> dict:
        """One focused re-judge of `items` (claim dicts). Returns
        index -> {"supported": bool, "quote": str, "reason": str}.
        Fail-open: a failed batch simply yields no entries, leaving the
        first-pass verdict in place."""
        out = {}
        for start in range(0, len(items), _SECOND_CHANCE_BATCH):
            batch = items[start:start + _SECOND_CHANCE_BATCH]
            numbered = "\n".join(f"{i + 1}. {c['claim']}"
                                 for i, c in enumerate(batch))
            try:
                resp, _e, _t = self.llm.generate_response(
                    [{"role": "system", "content": system},
                     {"role": "user", "content":
                         f"EVIDENCE:\n{evidence}\n\nCLAIMS:\n{numbered}\n\n"
                         "Return the JSON."}],
                    False,
                )
                data = _parse_json(resp)
            except Exception:
                continue
            verdicts = data.get("claims") if isinstance(data, dict) else None
            for v in verdicts if isinstance(verdicts, list) else []:
                if not isinstance(v, dict):
                    continue
                try:
                    i = int(v.get("index"))
                except (TypeError, ValueError):
                    continue
                if not 1 <= i <= len(batch):
                    continue
                quote = str(v.get("quote") or "")
                supported = (
                    str(v.get("verdict", "")).strip().lower() == "supported"
                    and _quote_anchored(quote, evidence_norm))
                out[batch[i - 1]["index"]] = {
                    "supported": supported, "quote": quote,
                    "reason": str(v.get("reason") or ""),
                    "verdict_raw": str(v.get("verdict") or "")}
        return out

    def verify_chapter(self, chapter_id, chapter_title, artifacts: dict,
                       section_ids, writer_evidence=None,
                       full_source_text=None, second_chances=False,
                       limit=_MAX_CLAIMS) -> dict:
        """Check the chapter's claims against its evidence. Advisory + log-only:
        never mutates ``artifacts``. Fail-open — any error returns a zero-count
        report with an ``error`` field instead of raising.

        Evidence precedence: ``full_source_text`` (the complete bound source —
        the sharpest protocol, see ``bound_section_text``), then
        ``writer_evidence`` (the exact block the writer was given, which asks
        "did the writer stay faithful to the context it had?"), then a fresh
        chapter-title retrieval as a last resort (coarse; can false-flag
        legitimate slides).

        ``second_chances`` adds two focused re-judges — accepted-but-unquoted
        claims are asked to copy the passage exactly, and flagged claims are
        searched for once more before being confirmed. Both directions are
        needed because a judge quotes loosely on a first pass and also misses
        support that sits far from the related passages. They cost extra LLM
        calls proportional to the number of problem claims, so they are
        opt-in; a measurement-grade run should enable them.

        ``limit`` caps how many claims are checked (document order). Pass
        ``None`` to check every claim — receipts record ``claims_segmented``
        and ``claims_capped`` either way so coverage is never implied.

        Judging is quote-anchored: the judge must return a verdict for every
        claim, and a "supported" verdict only counts if it carries a verbatim
        evidence quote that actually appears in the evidence (checked
        deterministically after normalization). Unanchored or missing verdicts
        are flagged, with ``flag_kind`` distinguishing ``judged_unsupported`` /
        ``unanchored_pass`` / ``no_verdict``. Anchored passes are recorded in
        ``supported_claims`` with their quotes, so every pass is auditable. A
        reply without per-claim verdicts gets one corrective retry; if the
        judge still replies in the old list-the-unsupported format, that lenient
        result is accepted but marked ``judge_protocol: "legacy_fallback"``."""
        bound = list(section_ids or [])
        report = {
            "chapter_id": chapter_id,
            "chapter_title": chapter_title,
            # Grounding state. ``grounded`` is False when the contract bound no
            # sections — the chapter was written WITHOUT retrieved evidence
            # (the abstain path), so a low/absent score here means "not
            # grounded", not "unfaithful". Recording absence explicitly keeps
            # the report honest: a reader can tell the two cases apart.
            "grounded": bool(bound),
            "bound_sections": bound,
            "claims_checked": 0,
            "unsupported_claim_count": 0,
            "flagged_claims": [],
            "summary": "",
            "model": self.model,
        }
        claims: List[str] = []
        for text in (artifacts or {}).values():
            claims.extend(_segment_claims(text or "", limit=None))
        # Coverage disclosure: verification is capped at _MAX_CLAIMS claims in
        # document order, so later content may be unchecked. Record what was
        # segmented vs what was checked instead of silently truncating.
        report["claims_segmented"] = len(claims)
        report["claims_capped"] = limit is not None and len(claims) > limit
        if limit is not None:
            claims = claims[:limit]
        report["claims_checked"] = len(claims)
        if not claims or self.llm is None:
            report["summary"] = "no claims to check"
            return report
        evidence = (full_source_text or writer_evidence
                    or self._evidence_block(chapter_title, section_ids))
        report["evidence_source"] = (
            "full_source_text" if full_source_text
            else "writer_evidence" if writer_evidence
            else "title_retrieval")
        numbered = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1))
        user = f"EVIDENCE:\n{evidence}\n\nCLAIMS:\n{numbered}\n\nReturn the JSON."
        report["judge_protocol"] = "quote_anchored_v1"
        try:
            messages = [
                {"role": "system", "content": _VERIFIER_SYSTEM},
                {"role": "user", "content": user},
            ]
            resp, _elapsed, _tokens = self.llm.generate_response(messages, False)
            data = _parse_json(resp)
            verdicts = data.get("claims") if isinstance(data, dict) else None
            if not isinstance(verdicts, list) or not verdicts:
                # One corrective retry: the anchor check needs per-claim
                # verdicts; without them every pass would count as unanchored
                # and format non-compliance would masquerade as infidelity.
                messages = messages + [
                    {"role": "assistant", "content": resp or ""},
                    {"role": "user", "content": (
                        "Your reply was not in the required format. Return "
                        'ONLY the JSON object {"claims": [...]} with one '
                        "verdict per claim, quoting the evidence verbatim for "
                        'every "supported" verdict.')},
                ]
                resp, _elapsed, _tokens = self.llm.generate_response(messages, False)
                data = _parse_json(resp)
                verdicts = data.get("claims") if isinstance(data, dict) else None
            if not isinstance(verdicts, list) or not verdicts:
                # Old-style {"unsupported": [...]} reply twice: accept the
                # lenient result rather than mass-flag on format grounds, but
                # record that these passes are NOT quote-anchored.
                report["judge_protocol"] = "legacy_fallback"
                flagged = (data.get("unsupported", [])
                           if isinstance(data, dict) else [])
                report["flagged_claims"] = flagged[:_MAX_CLAIMS]
            else:
                by_index = {}
                for v in verdicts:
                    if not isinstance(v, dict):
                        continue
                    try:
                        by_index.setdefault(int(v.get("index")), v)
                    except (TypeError, ValueError):
                        continue
                evidence_norm = _norm_for_anchor(evidence)
                flagged, supported = [], []
                for i, claim in enumerate(claims, 1):
                    v = by_index.get(i)
                    if v is None:
                        flagged.append({
                            "index": i, "claim": claim,
                            "flag_kind": "no_verdict",
                            "reason": "judge returned no verdict for this claim",
                        })
                    elif str(v.get("verdict", "")).strip().lower() == "supported":
                        quote = str(v.get("quote") or "")
                        if _quote_anchored(quote, evidence_norm):
                            supported.append(
                                {"index": i, "claim": claim, "quote": quote})
                        else:
                            flagged.append({
                                "index": i, "claim": claim, "quote": quote,
                                "flag_kind": "unanchored_pass",
                                "reason": ("supported verdict without a "
                                           "verbatim evidence quote"),
                            })
                    else:
                        flagged.append({
                            "index": i, "claim": claim,
                            "flag_kind": "judged_unsupported",
                            "reason": str(v.get("reason") or ""),
                        })
                if second_chances:
                    unanchored = [f for f in flagged
                                  if f["flag_kind"] == "unanchored_pass"]
                    others = [f for f in flagged
                              if f["flag_kind"] != "unanchored_pass"]
                    requoted = self._second_chance(
                        _REQUOTE_SYSTEM, unanchored, evidence, evidence_norm)
                    rechecked = self._second_chance(
                        _RECHECK_SYSTEM, others, evidence, evidence_norm)
                    kept, stats = [], {"requoted": 0, "retracted": 0,
                                       "flags_recovered": 0}
                    for f in flagged:
                        r = (requoted if f["flag_kind"] == "unanchored_pass"
                             else rechecked).get(f["index"])
                        if r and r["supported"]:
                            entry = {"index": f["index"], "claim": f["claim"],
                                     "quote": r["quote"]}
                            if f["flag_kind"] == "unanchored_pass":
                                entry["requoted"] = True
                                stats["requoted"] += 1
                            else:
                                entry["recovered_flag"] = True
                                stats["flags_recovered"] += 1
                            supported.append(entry)
                        elif (r and f["flag_kind"] == "unanchored_pass"
                                and r.get("verdict_raw", "").lower()
                                == "unsupported"):
                            kept.append({
                                "index": f["index"], "claim": f["claim"],
                                "flag_kind": "judged_unsupported",
                                "reason": r["reason"] or "retracted on re-quote",
                                "retracted_pass": True})
                            stats["retracted"] += 1
                        else:
                            kept.append(f)
                    flagged = sorted(kept, key=lambda x: x["index"])
                    supported.sort(key=lambda x: x["index"])
                    report["second_chance_stats"] = stats
                    report["judge_protocol"] = "quote_anchored_v2_symmetric"
                report["flagged_claims"] = flagged
                report["supported_claims"] = supported
                report["flag_kinds"] = {}
                for f in flagged:
                    k = f["flag_kind"]
                    report["flag_kinds"][k] = report["flag_kinds"].get(k, 0) + 1
            report["unsupported_claim_count"] = len(report["flagged_claims"])
            n, u = report["claims_checked"], report["unsupported_claim_count"]
            cov = (f" of {report['claims_segmented']} segmented"
                   if report["claims_capped"] else "")
            state = "" if report["grounded"] else " [chapter not grounded]"
            report["summary"] = (
                f"{n - u}/{n} claims supported ({u} flagged){cov}{state}")
        except Exception as e:  # fail-open — never block the save
            report["error"] = f"{type(e).__name__}: {e}"
            report["summary"] = "verification failed (fail-open)"
        return report


def report_line(report: dict) -> str:
    """One-line console summary of a verify_chapter report."""
    base = f"[content-verify] {report.get('chapter_id', '?')}: {report.get('summary', '')}"
    return base + (f" — ERROR {report['error']}" if report.get("error") else "")
