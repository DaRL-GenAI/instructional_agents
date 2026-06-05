import os
import json
import re
from typing import List, Dict, Optional, Any
from openai import OpenAI
from pathlib import Path
import pandas as pd
from src.agents import LLM
import argparse

class ValidationAgent:
    """
    Validation agent for evaluating course materials from different perspectives
    """
    def __init__(self, role: str, llm: LLM):
        self.role = role
        self.llm = llm
        self.prompts = {
            "Program Chair": {
                "system": """You are a Program Chair evaluating course materials. Your focus is on:
                - Academic rigor and standards
                - Alignment with program requirements
                - Quality of educational design
                - Assessment validity and reliability
                - Overall coherence and structure
                Please provide detailed evaluation and constructive feedback."""
            },
            "Test Student": {
                "system": """You are a Test Student evaluating course materials. Your focus is on:
                - Clarity and understandability
                - Engagement and motivation
                - Learning support and guidance
                - Practical applicability
                - Accessibility and user experience
                Please provide feedback from a student's perspective."""
            }
        }
    
    def evaluate_content(self, file_type: str, filename: str, content: str) -> str:
        """
        Evaluate content based on the agent's role
        
        Args:
            file_type: Type of file (Learning Objectives, Syllabus, Assessment, Slide Content, Slide Scripts)
            filename: Name of the file being evaluated
            content: Content to evaluate
            
        Returns:
            Evaluation report in markdown format
        """
        system_prompt = self.prompts[self.role]["system"]
        
        user_prompt = f"""
        Please evaluate the following {file_type} from the file "{filename}":

        Content:
        {content}

        Please provide:
        1. Overall Assessment
        2. Strengths
        3. Areas for Improvement
        4. Specific Recommendations
        5. Rating (1-5 scale)

        Format your response in markdown.
        """
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        response, elapsed_time, token_usage = self.llm.generate_response(messages, stream=False)
        return response

class EvaluationAgent:
    """
    Evaluation agent for scoring course materials based on specific metrics
    """
    def __init__(self, llm: LLM):
        self.llm = llm
        self.metrics = {
            "learning_objectives": {
                "clarity": "Learning objectives are stated clearly in understandable language.",
                "measurability": "Learning objectives use measurable verbs to define observable outcomes.",
                "appropriateness": "Learning objectives are appropriate for the student level (introductory, intermediate, advanced)."
            },
            "syllabus": {
                "coherence": "The course introduction presents the purpose and structure logically and smoothly.",
                "coverage": "The syllabus comprehensively lists the intended learning objectives.",
                "organization": "The schedule or modular course structure is organized and easy to navigate.",
                "accessibility": "Technology requirements, learner support, and navigation information are clearly accessible.",
                "transparency_of_policies": "Academic policies and expectations are presented clearly and understandably."
            },
            "assessment": {
                "alignment": "Assessments are directly aligned with learning objectives.",
                "clarity": "Clear instructions are provided for completing assessments.",
                "availability": "Rubrics or scoring criteria are made available to learners.",
                "formative_feedback": "Formative assessments and feedback opportunities are provided.",
                "variety": "Assessments use multiple methods to allow learners to demonstrate their understanding."
            },
            "slide_content": {
                "alignment": "Instructional materials support achievement of learning objectives.",
                "appropriateness": "Materials are appropriate for learner needs and course level.",
                "accuracy": "Content reflects current knowledge and practices, and is accurate.",
                "attribution": "Materials include correct citations and licensing information."
            },
            "slide_scripts": {
                "alignment": "Scripts are aligned with corresponding slide content.",
                "coherence": "Scripts maintain clear, coherent, and logically sequenced explanations.",
                "engagement": "Scripts include examples or techniques that enhance engagement and understanding.",
                "attribution": "External references in scripts are properly cited and licensed."
            }
        }

    
    def score_single_metric(self, file_type: str, filename: str, content: str, metric: str) -> int:
        """
        Score a single metric for a file (returns only a number 1-5)
        
        Args:
            file_type: Type of file
            filename: Name of the file
            content: Content to evaluate
            metric: Specific metric to score
            
        Returns:
            Score (1-5)
        """
        cot_prompt = """Your output should be format as JSON like:
        {"THOUGHT": "Your thought process here", "SCORE": 2.0}

        In THOUGHT, please first briefly discuss your intuitions and reasoning for the evaluation.
        Detail your high-level arguments, necessary choices and desired outcomes of the review.
        Do not make generic comments here, but be specific to your current paper.
        Treat this as the note-taking phase of your review.

        In SCORE, respond with ONLY the rating number (1.0 ~ 5.0). No other text or explanation.

        NOTE: Don't always give it a high score, try to think how much time you spend on this content to polish it for use if you are a faculty.
        """
        prompt = f"""
        Evaluate the {metric} of the following {file_type} content from file "{filename}".
        
        Rate this content on the metric "{metric}" using a scale of 1.0 ~ 5.0 (you can use decimal values).
        - 5.0: Perfect
        - 4.0: Excellent
        - 3.0: Good
        - 2.0: Fair
        - 1.0: Poor

        {cot_prompt}

        Content:
        {content}
        """
        
        messages = [
            {"role": "system", "content": "You are an educational content evaluator. Provide only numerical scores."},
            {"role": "user", "content": prompt}
        ]
        
        max_retries = 3  # 最多重试3次
        retries = 0

        while retries < max_retries:
            response, elapsed_time, token_usage = self.llm.generate_response(messages, stream=False)

            try:
                result = json.loads(response)
                score = float(result.get("SCORE", 3.0))
                if 1.0 <= score <= 5.0:
                    return score
                else:
                    print(f"Invalid score {score} for {metric} in {file_type}. Retrying...")
            except Exception as e:
                print(f"Failed to parse score from response: {response}. Error: {e}. Retrying...")

            retries += 1

        # 如果重试后仍然失败，默认返回3.0
        print(f"Max retries reached. Defaulting to 3.0 for {metric} in {file_type}.")
        return 3.0


    def evaluate_files(self, file_data: Dict[str, List[Dict]]) -> Dict:
        """
        Evaluate all files and generate summary statistics
        
        Args:
            file_data: Dictionary with file types as keys and list of file info as values
            
        Returns:
            Dictionary containing scores and statistics
        """
        results = {}
        all_scores = []  # List to store all scores for the overall summary

        print("Starting evaluation of course materials...")
        print(f"Total file types to evaluate: {[ len(files) for file_type, files in file_data.items() if files]}")

        for file_type, files in file_data.items():
            if not files:  # Skip empty file lists
                continue

            type_results = []
            metrics = self.metrics.get(file_type, [])

            for file_info in files:
                filename = file_info['filename']
                content = file_info['content']

                file_scores = {}
                for metric in metrics.keys():
                    score = self.score_single_metric(file_type, filename, content, f"{metric}: {metrics[metric]}")
                    file_scores[metric] = score
                    print(f"Scored {filename} - {metric}: {score}")

                type_results.append({
                    'filename': filename,
                    'scores': file_scores,
                    'average': sum(file_scores.values()) / len(file_scores) if file_scores else 0
                })

                # Add scores to the overall list for summary
                for score in file_scores.values():
                    all_scores.append(score)

            # Calculate summary statistics for each file type
            if type_results:
                type_all_scores = []
                for result in type_results:
                    type_all_scores.extend(result['scores'].values())

                results[file_type] = {
                    'files': type_results,
                    'summary': {
                        'total_files': len(type_results),
                        'average_score': sum(type_all_scores) / len(type_all_scores) if type_all_scores else 0,
                        'max_score': max(type_all_scores) if type_all_scores else 0,
                        'min_score': min(type_all_scores) if type_all_scores else 0
                    }
                }

        # Calculate overall summary statistics
        if all_scores:
            results['overall_summary'] = {
                "summary": {
                    'total_files': sum(len(files) for files in file_data.values()),
                    'average_score': sum(all_scores) / len(all_scores),
                    'max_score': max(all_scores),
                    'min_score': min(all_scores)
                    }
            }

        return results


# Citation tokens emitted by the grounded generation pipeline look like
# `[textbook_id:section_id:p<page>]`, e.g. `[han_data_mining_3e:ch6.s3:p15]`.
# textbook_id and section_id are restricted to [A-Za-z0-9._] by the IR builders,
# so the regex below matches everything well-formed and nothing else.
CITATION_TOKEN_RE = re.compile(r"\[([A-Za-z0-9_]+):([A-Za-z0-9._]+):p(\d+)\]")


# Failure-mode buckets the judge picks from when a citation is < 4 / 5.
# Telling the buckets apart matters: each one points at a different
# lever (retrieval, prompting, generation discipline).
FAILURE_MODE_VALUES = (
    "retrieval_bad",      # The chunk isn't on the same topic as the claim → fix retrieval.
    "hallucination",      # Chunk is on-topic but claim adds specifics it doesn't contain → fix prompting + rejection sampling.
    "loose_paraphrase",   # Chunk supports the gist, claim drifts in wording → fix wording-anchor rule.
    "wrong_chunk_cited",  # A different excerpt in the same retrieval would have supported the claim → fix attribution discipline.
    "good",               # No failure — supported (score ≥ 4).
    "judge_uncertain",    # Judge couldn't pick; counted but not blamed on any lever.
)


# Per-sentence relevance trim helper. When the judge gets the WHOLE
# 500-token chunk, it can be hard to pinpoint which sentence is
# supposed to support the claim, and the score gets noisy. Trimming
# the chunk to the most-overlapping sentence + neighbours sharpens
# the judge's input.
_TRIM_MAX_CHARS = 1500       # safety cap on the final excerpt
_TRIM_WINDOW_SENTENCES = 3   # neighbours on each side of the best sentence
_TRIM_MIN_CHUNK_CHARS = 400  # don't bother trimming chunks shorter than this
_WORD_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")


def _normalise_words(text: str) -> set[str]:
    """Lowercase the alphanumeric words of length ≥ 3 in text."""
    return {m.group(0).lower() for m in _WORD_RE.finditer(text)}


def _trim_chunk_to_relevant_passage(chunk_text: str, claim: str) -> str:
    """Trim the chunk to the sentences most relevant to the claim.

    Splits the chunk into sentences, scores each by the number of
    content-word overlaps with the claim, and returns a window of
    :data:`_TRIM_WINDOW_SENTENCES` sentences on each side of the
    highest-scoring sentence. Falls back to a head-truncate when
    overlap-scoring can't identify a clear best (zero overlap on
    every sentence) so the judge still has something to work with.

    Short chunks (< _TRIM_MIN_CHUNK_CHARS) are returned unmodified;
    no point trimming what's already small.
    """
    if not chunk_text or len(chunk_text) < _TRIM_MIN_CHUNK_CHARS:
        return chunk_text[:_TRIM_MAX_CHARS]
    if not claim:
        return chunk_text[:_TRIM_MAX_CHARS]

    sentences = _SENT_SPLIT_RE.split(chunk_text)
    if len(sentences) < 2:
        return chunk_text[:_TRIM_MAX_CHARS]

    claim_words = _normalise_words(claim)
    if not claim_words:
        return chunk_text[:_TRIM_MAX_CHARS]

    best_idx = -1
    best_score = -1
    for i, s in enumerate(sentences):
        score = len(claim_words & _normalise_words(s))
        if score > best_score:
            best_score = score
            best_idx = i

    if best_score == 0:
        # No overlap anywhere — fall back to the chunk head.
        return chunk_text[:_TRIM_MAX_CHARS]

    lo = max(0, best_idx - _TRIM_WINDOW_SENTENCES)
    hi = min(len(sentences), best_idx + _TRIM_WINDOW_SENTENCES + 1)
    excerpt = " ".join(sentences[lo:hi]).strip()
    return excerpt[:_TRIM_MAX_CHARS]


class GroundingAgent:
    """Score citation faithfulness against an ingested textbook.

    For each citation token found in a piece of generated content, look
    up the chunk it references in the textbook KB, then ask the LLM
    whether that chunk supports the claim sitting around the citation.
    Aggregate to:

      * **citation_precision** — fraction of citations whose chunk
        actually supports the cited claim (score ≥ 4 / 5).
      * **faithfulness** — average 1-5 RAGAS-style score across all
        resolved citations.
      * **malformed_citations** — count of tokens that don't resolve to
        any chunk in the KB (typo, model hallucination of a section ID,
        truncated output, etc.).
      * **unsupported_citations** — citations scoring < 3.
      * **failure_mode_counts** — for each unsupported / loosely-supported
        citation, the judge categorises *why* it failed (retrieval-bad,
        hallucination, loose paraphrase, wrong chunk cited). Pinpoints
        which lever to pull next when faithfulness is below target.

    Citation recall (did the model cite every factual claim?) would
    require atomic-claim extraction, which is a bigger LLM-heavy step;
    out of scope for this first version.
    """

    # Window of characters around each citation token to use as the
    # "claim" sent to the judge LLM. Best-effort trims to sentence
    # boundaries where possible. Wider window = more context but also
    # more tokens per scoring call.
    CLAIM_WINDOW_CHARS = 220

    # Self-consistency knob (default 1 = no voting, matches pre-existing
    # behavior). When >1, each citation gets scored ``n_samples`` times
    # and the aggregate is taken — median for the numeric SCORE,
    # majority-vote for the FAILURE_MODE. Tightens the ±0.16 per-call
    # judge noise floor at the cost of N× verifier eval API spend.
    # Vanilla single-call behavior preserved as the default so existing
    # tests + downstream consumers see no behavior change.
    DEFAULT_N_SAMPLES = 1

    def __init__(self, llm: LLM, knowledge_base: Any, n_samples: int = DEFAULT_N_SAMPLES):
        self.llm = llm
        self.kb = knowledge_base
        if n_samples < 1:
            raise ValueError(f"n_samples must be >= 1, got {n_samples}")
        self.n_samples = n_samples
        # Pre-index every chunk by EVERY citation token that should
        # resolve to it. A multi-page chunk (page_start < page_end)
        # registers one entry per page in its range so the LLM can
        # cite any page within the chunk and have its citation
        # resolve correctly. Single-page chunks register exactly one
        # entry (identical to the prior behaviour).
        self._chunk_by_token: Dict[str, Any] = {}
        for c in knowledge_base.chunks:
            # citation_tokens_in_range yields one token per page in the
            # chunk's range; for single-page chunks it returns a single
            # token equal to citation_token().
            try:
                tokens = c.citation_tokens_in_range()
            except AttributeError:
                # Older Chunk shape without the method — fall back to
                # the single canonical token.
                tokens = [c.citation_token()]
            for tok in tokens:
                # Don't overwrite if another chunk has already claimed
                # this token (rare; could happen if two sections happen
                # to overlap on a boundary page). First write wins.
                self._chunk_by_token.setdefault(tok, c)

    # ----- public API ----------------------------------------------------

    def score_text(self, filename: str, text: str) -> Dict[str, Any]:
        """Score every citation in `text`. Returns a summary dict.

        When `text` has no citations, the summary's aggregate fields are
        ``None`` (not 0.0) so a downstream report can distinguish
        "nothing to verify" from "everything failed verification."
        """
        citations = self._extract_citations(text)
        if not citations:
            return {
                "filename": filename,
                "n_citations": 0,
                "n_supported": 0,
                "n_unsupported": 0,
                "n_malformed": 0,
                "faithfulness": None,
                "citation_precision": None,
                "per_citation": [],
            }

        per: List[Dict[str, Any]] = []
        for cite in citations:
            per.append(self._score_one(cite, text))

        resolved = [s for s in per if not s["malformed"]]
        n_malformed = sum(1 for s in per if s["malformed"])
        n_supported = sum(1 for s in resolved if (s["score"] or 0.0) >= 4.0)
        n_unsupported = sum(1 for s in resolved if (s["score"] or 0.0) < 3.0)
        avg = (
            sum(s["score"] for s in resolved) / len(resolved)
            if resolved else None
        )

        # Bucket failure modes across the resolved (non-malformed) citations.
        # Useful for diagnosing which lever to pull next when the precision
        # number is below target.
        failure_mode_counts: Dict[str, int] = {m: 0 for m in FAILURE_MODE_VALUES}
        for s in resolved:
            mode = (s.get("failure_mode") or "judge_uncertain")
            if mode not in failure_mode_counts:
                mode = "judge_uncertain"
            failure_mode_counts[mode] += 1

        return {
            "filename": filename,
            "n_citations": len(per),
            "n_supported": n_supported,
            "n_unsupported": n_unsupported,
            "n_malformed": n_malformed,
            "faithfulness": avg,
            "citation_precision": (
                n_supported / len(resolved) if resolved else None
            ),
            "failure_mode_counts": failure_mode_counts,
            "per_citation": per,
        }

    # ----- internals -----------------------------------------------------

    def _extract_citations(self, text: str) -> List[Dict[str, Any]]:
        """Find every `[textbook_id:section_id:p<page>]` token in `text`."""
        out = []
        for m in CITATION_TOKEN_RE.finditer(text):
            out.append({
                "token": m.group(0),
                "textbook_id": m.group(1),
                "section_id": m.group(2),
                "page": int(m.group(3)),
                "start": m.start(),
                "end": m.end(),
            })
        return out

    def _score_one(self, cite: Dict[str, Any], text: str) -> Dict[str, Any]:
        """Look up the cited chunk, ask the LLM to rate 1-5 + categorise failure."""
        chunk = self._chunk_by_token.get(cite["token"])
        claim = self._claim_window(text, cite)

        if chunk is None:
            # Token doesn't resolve. Could be a typo, hallucinated section
            # ID, or a truncated token (we saw `[han_data_mining_3e:c]`
            # in real B1 output). Flag but don't score.
            return {
                **cite,
                "malformed": True,
                "score": None,
                "claim": claim,
                "rationale": "Citation token does not resolve to any chunk in the textbook.",
                "failure_mode": None,
                "chunk_section_id": None,
                "chunk_section_title": None,
            }

        # Use the aggregate method so that when self.n_samples > 1, the
        # citation gets scored multiple times with majority-vote
        # aggregation. When n_samples == 1 (the default), this is a thin
        # passthrough to _llm_score with no behavior change.
        score, rationale, failure_mode = self._llm_score_aggregate(claim, chunk.text)
        return {
            **cite,
            "malformed": False,
            "score": score,
            "claim": claim,
            "rationale": rationale,
            "failure_mode": failure_mode,
            "chunk_section_id": chunk.section_id,
            "chunk_section_title": chunk.section_title,
        }

    # Sentence-boundary regex: a terminator (. ! ?) followed by
    # whitespace then a capital letter or a section-internal marker.
    # Tolerates citation tokens at the end of a sentence (the regex
    # matches even when a "[textbook_id:section_id:p<page>]" appears
    # just before the terminator).
    _SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[])")

    def _claim_window(self, text: str, cite: Dict[str, Any]) -> str:
        """Pull the sentence containing the citation as the claim window.

        Sentence-bounded rather than fixed-character-width: the
        verifier judges a complete sentence as the unit of a claim,
        which is the natural unit for the citation token. Falls back
        to a wider expansion if the immediate sentence is shorter
        than ~40 chars (e.g. a fragment) so the judge has enough
        context to score.
        """
        # Split the surrounding text into sentences and locate the one
        # containing the citation's character offset.
        cit_start = cite["start"]
        cit_end = cite["end"]
        # Sentence boundaries: positions just after a terminator+space.
        boundaries = [0]
        for m in self._SENTENCE_BOUNDARY_RE.finditer(text):
            boundaries.append(m.end())
        boundaries.append(len(text))

        # Find the sentence span [s, e) whose [s, e) covers the citation
        # token. Sentences are [boundaries[i], boundaries[i+1]).
        target_idx = 0
        for i in range(len(boundaries) - 1):
            s, e = boundaries[i], boundaries[i + 1]
            if s <= cit_start < e:
                target_idx = i
                break

        s, e = boundaries[target_idx], boundaries[target_idx + 1]
        # Ensure the cited token is fully inside [s, e); if it spans a
        # boundary (rare but possible), expand the window to cover it.
        if cit_end > e:
            e = min(len(text), cit_end + 1)

        claim = text[s:e].strip()

        # If the claim is tiny (e.g. extracted "K-means [tok]."), pad
        # with one adjacent sentence on each side so the judge has
        # enough context to evaluate the assertion.
        _MIN_CLAIM_CHARS = 40
        if len(claim) < _MIN_CLAIM_CHARS:
            left_idx = max(0, target_idx - 1)
            right_idx = min(len(boundaries) - 2, target_idx + 1)
            s = boundaries[left_idx]
            e = boundaries[right_idx + 1]
            claim = text[s:e].strip()

        # Hard cap to CLAIM_WINDOW_CHARS as a safety belt (the
        # expanded fallback could in theory be long).
        if len(claim) > self.CLAIM_WINDOW_CHARS:
            # Center the cap around the citation.
            offset = cit_start - s
            half = self.CLAIM_WINDOW_CHARS // 2
            new_s = max(0, offset - half)
            new_e = min(len(claim), offset + half)
            claim = claim[new_s:new_e].strip()
        return claim

    def _llm_score_aggregate(self, claim: str, chunk_text: str) -> tuple:
        """Score a (claim, chunk) pair with self-consistency voting.

        Calls :meth:`_llm_score` ``self.n_samples`` times and aggregates:

        * **Score**: median of the N numeric scores (robust to outliers).
        * **Failure mode**: most common ("majority vote"); on ties the
          mode tied with the highest-scoring sample wins (favors the
          most-confident bucket).
        * **Rationale**: the rationale from the sample whose score is
          closest to the median (representative of the consensus).

        When ``n_samples == 1`` (the default), this is just a thin
        passthrough — no extra LLM calls. Existing tests + downstream
        consumers see no behavior change unless they explicitly opt in.

        Why this matters: gpt-4o-mini's judgment on a single citation
        has measured ±0.16 noise on the 1-5 scale. With n=3 voting the
        noise drops roughly to ±0.05, which is the difference between
        "did the architectural fix actually move precision" and "is
        this noise". The cost is 3× the verifier eval API spend
        (verifier total ~$0.30 → ~$0.90); generation is unaffected.
        """
        if self.n_samples == 1:
            return self._llm_score(claim, chunk_text)

        from collections import Counter

        samples: List[tuple] = []
        for _ in range(self.n_samples):
            sample = self._llm_score(claim, chunk_text)
            # `_llm_score` returns ``(3.0, "...failed...", "judge_uncertain")``
            # as a fallback when the LLM call itself fails — skip those
            # so voting isn't dominated by the fallback bucket.
            score, rationale, failure_mode = sample
            if rationale.startswith("LLM scoring failed"):
                continue
            samples.append(sample)

        if not samples:
            # Every sample fell into the fallback path. Surface a single
            # fallback result so the caller sees consistent shape.
            return 3.0, "LLM scoring failed after retries; defaulted to 3.0.", "judge_uncertain"

        scores = sorted(s[0] for s in samples)
        median_score = scores[len(scores) // 2]

        # Majority vote for failure_mode, with score-weighted tie-break:
        # if two modes tied for most votes, prefer the one associated
        # with the highest single-call SCORE (favors the bucket the most
        # confident sample chose).
        mode_counter = Counter(s[2] for s in samples)
        top_count = mode_counter.most_common(1)[0][1]
        tied_modes = [m for m, c in mode_counter.items() if c == top_count]
        if len(tied_modes) == 1:
            consensus_mode = tied_modes[0]
        else:
            # Pick the mode whose highest associated sample-score is biggest
            best_score_per_mode = {m: max(s[0] for s in samples if s[2] == m)
                                   for m in tied_modes}
            consensus_mode = max(best_score_per_mode, key=best_score_per_mode.get)

        # Rationale from the sample whose score is closest to median.
        closest_sample = min(samples, key=lambda s: abs(s[0] - median_score))
        consensus_rationale = closest_sample[1]
        return median_score, consensus_rationale, consensus_mode

    def _llm_score(self, claim: str, chunk_text: str) -> tuple:
        """Ask the LLM for a 1-5 faithfulness score + rationale + failure mode.

        Returns ``(score, rationale, failure_mode)``. ``failure_mode`` is
        one of the strings in :data:`FAILURE_MODE_VALUES`; ``"good"`` for
        scores ≥ 4, otherwise the judge's chosen category.

        This is the single-call primitive used by
        :meth:`_llm_score_aggregate`; callers that want self-consistency
        voting should go through the aggregate method instead.
        """
        # Trim the chunk to the most relevant passage for THIS claim so
        # the judge focuses on the supporting text rather than the
        # whole 500-token chunk. Falls back to a head-truncate when
        # the trim helper can't identify a clear best match.
        chunk_excerpt = _trim_chunk_to_relevant_passage(chunk_text, claim)
        prompt = f"""You are evaluating whether a textbook excerpt supports a claim drawn from generated course material.

CLAIM (with [...] citation token, drawn from a generated slide / script / assessment):
{claim}

CITED TEXTBOOK EXCERPT:
{chunk_excerpt}

Rate how faithfully the excerpt supports the claim on a 1.0-5.0 scale:
- 5.0: Claim is directly supported by the excerpt — same facts, same emphasis.
- 4.0: Claim is mostly supported; minor paraphrasing only.
- 3.0: Claim is loosely supported; the writer added some interpretation beyond what the excerpt says.
- 2.0: Claim has only tenuous connection to the excerpt.
- 1.0: Claim is not supported by the excerpt at all.

ALSO categorise the primary failure mode (use exactly one of these strings):
- "good"               — claim is well supported (use this when SCORE ≥ 4).
- "retrieval_bad"      — the excerpt isn't on the same topic as the claim; a different excerpt would be needed.
- "hallucination"      — excerpt is on-topic but the claim adds specifics, numbers, or facts the excerpt does NOT state.
- "loose_paraphrase"   — excerpt supports the gist but the claim drifts in wording or emphasis.
- "wrong_chunk_cited"  — excerpt is from the wrong section; the claim looks like it came from a NEARBY section instead.
- "judge_uncertain"    — you cannot confidently pick one of the above.

Respond with STRICT JSON only:
{{"SCORE": <float between 1.0 and 5.0>, "RATIONALE": "<one short sentence>", "FAILURE_MODE": "<one of the strings above>"}}
"""
        messages = [
            {
                "role": "system",
                "content": "You evaluate citation faithfulness. Output only the JSON object.",
            },
            {"role": "user", "content": prompt},
        ]
        max_retries = 3
        for _ in range(max_retries):
            try:
                response, _, _ = self.llm.generate_response(messages, stream=False)
                # Be permissive about leading/trailing text around the JSON.
                m = re.search(r"\{.*?\"SCORE\".*?\}", response, re.DOTALL)
                if not m:
                    continue
                result = json.loads(m.group(0))
                score = float(result.get("SCORE", 3.0))
                if not (1.0 <= score <= 5.0):
                    continue
                rationale = str(result.get("RATIONALE", "")).strip()
                mode_raw = str(result.get("FAILURE_MODE", "")).strip().lower()
                # Normalise to the allowed vocabulary; default a good
                # score to "good" and an unknown mode to "judge_uncertain".
                if mode_raw not in FAILURE_MODE_VALUES:
                    mode_raw = "good" if score >= 4.0 else "judge_uncertain"
                return score, rationale, mode_raw
            except Exception:
                continue
        return 3.0, "LLM scoring failed after retries; defaulted to 3.0.", "judge_uncertain"


class CourseEvaluationSystem:
    """
    Main system for evaluating course materials
    """
    def __init__(self, model_name: str, exp_name: str,
                 textbook_path: Optional[str] = None,
                 verifier_samples: int = 1):
        self.llm = LLM(model_name=model_name)
        self.program_chair = ValidationAgent("Program Chair", self.llm)
        self.test_student = ValidationAgent("Test Student", self.llm)
        self.evaluator = EvaluationAgent(self.llm)
        self.exp_name = exp_name

        self.eval_dir = Path(f"eval/{model_name}-Evaluation_{self.exp_name}/evaluation_results")
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        self.valid_dir = Path(f"eval/{model_name}-Evaluation_{self.exp_name}/validation_reports")
        self.valid_dir.mkdir(parents=True, exist_ok=True)

        # Textbook grounding (opt-in). When `textbook_path` is None the
        # grounding agent stays None and `score_grounding` is a no-op.
        self.grounding_agent: Optional[GroundingAgent] = None
        self.grounding_dir = Path(
            f"eval/{model_name}-Evaluation_{self.exp_name}/grounding_results"
        )
        if textbook_path:
            # Lazy import so `python evaluate.py` with no textbook flag
            # doesn't pay the import cost.
            from src.grounding import TextbookKnowledgeBase
            print(f"[grounding] Loading textbook for verification: {textbook_path}")
            kb = TextbookKnowledgeBase.from_path(textbook_path)
            self.grounding_agent = GroundingAgent(self.llm, kb, n_samples=verifier_samples)
            if verifier_samples > 1:
                print(f"[grounding] Verifier self-consistency: {verifier_samples} "
                      f"samples per citation, median + majority vote.")
            self.grounding_dir.mkdir(parents=True, exist_ok=True)
            print(
                f"[grounding] Indexed {len(kb)} chunks from "
                f"'{kb.textbook.title}' for citation verification."
            )

    def read_file_content(self, filepath: str) -> str:
        """Read content from file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return ""
    
    def map_file_to_type(self, filename: str) -> str:
        """Map filename to content type"""
        mapping = {
            'result_instructional_goals.md': 'learning_objectives',
            'result_syllabus_design.md': 'syllabus',
            'slides.tex': 'slide_content',
            'assessment.md': 'assessment',
            'script.md': 'slide_scripts'
        }
        return mapping.get(filename, 'Unknown')
    
    def save_validation_report(self, agent_name: str, file_type: str, filename: str, evaluation: str):
        """Save validation report to markdown file"""
        output_dir = self.valid_dir
        
        report_filename = f"{agent_name}_{file_type}_{Path(filename).stem}_validation.md"
        report_path = output_dir / report_filename.replace(" ", "_")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"# {agent_name} Validation Report\n\n")
            f.write(f"**File Type:** {file_type}\n\n")
            f.write(f"**File Name:** {filename}\n\n")
            f.write(f"**Evaluation Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            f.write(evaluation)
        
        print(f"Saved validation report: {report_path}")
    
    def score_grounding(self, file_data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Run citation verification across every generated file.

        No-op when `grounding_agent is None` — i.e. when `evaluate.py`
        was invoked without `--use-textbook`. The returned dict has the
        same shape regardless of file count, so the caller can always
        write it out.
        """
        if self.grounding_agent is None:
            return {}

        per_file: List[Dict[str, Any]] = []
        # Citations only appear in chapter-generated files (slide_content,
        # slide_scripts, assessment) — the foundation deliberations don't
        # carry citations. Scoring the foundation files would mostly find
        # zero citations, but it's cheap to include them and surfaces any
        # surprise tokens that leak in.
        for file_type, files in file_data.items():
            for info in files:
                if not info.get("content"):
                    continue
                summary = self.grounding_agent.score_text(
                    info["filename"], info["content"]
                )
                summary["file_type"] = file_type
                summary["filepath"] = info.get("filepath")
                per_file.append(summary)
                if summary["n_citations"]:
                    print(
                        f"[grounding] {info['filename']}: "
                        f"{summary['n_citations']} citations, "
                        f"precision={summary['citation_precision']:.2f} "
                        if summary['citation_precision'] is not None else
                        f"[grounding] {info['filename']}: "
                        f"{summary['n_citations']} citations (all malformed)"
                    )

        # Aggregate across every resolved citation in every file.
        all_resolved = []
        for s in per_file:
            for c in s["per_citation"]:
                if not c["malformed"] and c["score"] is not None:
                    all_resolved.append(c)
        n_total = sum(s["n_citations"] for s in per_file)
        n_malformed = sum(s["n_malformed"] for s in per_file)
        n_supported = sum(s["n_supported"] for s in per_file)
        n_unsupported = sum(s["n_unsupported"] for s in per_file)
        avg = (
            sum(c["score"] for c in all_resolved) / len(all_resolved)
            if all_resolved else None
        )

        # Distinct sections cited — useful for coverage metric in the
        # eventual comparison report.
        cited_sections = sorted({
            c["section_id"] for s in per_file for c in s["per_citation"]
            if not c["malformed"]
        })

        # Aggregate failure-mode buckets across every resolved citation.
        # Points at which lever to pull when precision is below target.
        overall_failure_modes: Dict[str, int] = {m: 0 for m in FAILURE_MODE_VALUES}
        for s in per_file:
            for mode, count in (s.get("failure_mode_counts") or {}).items():
                if mode in overall_failure_modes:
                    overall_failure_modes[mode] += count

        return {
            "exp_name": self.exp_name,
            "textbook_id": (
                self.grounding_agent.kb.textbook_id
                if self.grounding_agent else None
            ),
            "overall": {
                "n_files_with_citations": sum(
                    1 for s in per_file if s["n_citations"] > 0
                ),
                "n_citations_total": n_total,
                "n_malformed_total": n_malformed,
                "n_supported_total": n_supported,
                "n_unsupported_total": n_unsupported,
                "faithfulness_mean": avg,
                "citation_precision": (
                    n_supported / len(all_resolved) if all_resolved else None
                ),
                "distinct_sections_cited": cited_sections,
                "n_distinct_sections_cited": len(cited_sections),
                "failure_mode_counts": overall_failure_modes,
            },
            "files": per_file,
        }

    def save_grounding_results(self, results: Dict[str, Any]):
        """Write the grounding scores to disk alongside the other reports."""
        if not results:
            return
        out_dir = self.grounding_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        # Full per-citation JSON (useful for the comparison report).
        json_path = out_dir / "grounding_scores.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Human-readable markdown summary.
        md_path = out_dir / "grounding_summary.md"
        with open(md_path, "w", encoding="utf-8") as f:
            ov = results["overall"]
            f.write("# Grounding Verification Summary\n\n")
            f.write(f"**Experiment:** {results['exp_name']}\n\n")
            f.write(f"**Textbook:** {results.get('textbook_id', '?')}\n\n")
            f.write(f"**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n## Overall\n\n")
            f.write(f"- Files with citations: **{ov['n_files_with_citations']}**\n")
            f.write(f"- Total citations: **{ov['n_citations_total']}**\n")
            f.write(f"- Malformed (didn't resolve): **{ov['n_malformed_total']}**\n")
            f.write(f"- Supported (score ≥ 4): **{ov['n_supported_total']}**\n")
            f.write(f"- Unsupported (score < 3): **{ov['n_unsupported_total']}**\n")
            if ov["faithfulness_mean"] is not None:
                f.write(f"- Faithfulness (mean 1–5): **{ov['faithfulness_mean']:.2f}**\n")
                f.write(f"- Citation precision: **{ov['citation_precision']:.2%}**\n")
            f.write(f"- Distinct sections cited: **{ov['n_distinct_sections_cited']}**"
                    f" — {', '.join(ov['distinct_sections_cited'][:20])}"
                    f"{'...' if len(ov['distinct_sections_cited']) > 20 else ''}\n\n")

            # Failure-mode breakdown — surfaces which lever to pull next.
            fmc = ov.get("failure_mode_counts") or {}
            if any(fmc.values()):
                f.write("## Failure-mode breakdown (resolved citations)\n\n")
                f.write("How each resolved citation was categorised by the judge. "
                        "Pinpoints whether the precision loss comes from retrieval "
                        "(retrieval_bad), generation (hallucination / loose_paraphrase), "
                        "or attribution (wrong_chunk_cited).\n\n")
                total_resolved = sum(fmc.values()) or 1
                # Render in a fixed order so reports across runs are comparable.
                order = [
                    "good", "loose_paraphrase", "hallucination",
                    "retrieval_bad", "wrong_chunk_cited", "judge_uncertain",
                ]
                for mode in order:
                    count = fmc.get(mode, 0)
                    pct = (count / total_resolved) * 100.0
                    f.write(f"- **{mode}**: {count} ({pct:.1f}%)\n")
                f.write("\n")
            f.write("## Per file\n\n")
            for s in results["files"]:
                if not s["n_citations"]:
                    continue
                f.write(f"### {s['filename']}\n\n")
                f.write(f"- Citations: {s['n_citations']}")
                if s["faithfulness"] is not None:
                    f.write(f" | faithfulness {s['faithfulness']:.2f}")
                    f.write(f" | precision {s['citation_precision']:.0%}")
                if s["n_malformed"]:
                    f.write(f" | **{s['n_malformed']} malformed**")
                f.write("\n\n")

        print(f"\n[grounding] Saved grounding report: {md_path}")
        print(f"[grounding] Saved grounding scores:  {json_path}")

    def save_evaluation_results(self, results: Dict):
        """Save evaluation results to JSON and markdown"""
        output_dir = self.eval_dir

        # Save JSON results
        json_path = output_dir / "evaluation_scores.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Save JSON results
        json_path = output_dir / "evaluation_scores_overall.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results['overall_summary'], f, indent=2, ensure_ascii=False)
        
        # Save markdown summary
        md_path = output_dir / "evaluation_summary.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write("# Course Material Evaluation Summary\n\n")
            f.write(f"**Evaluation Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for file_type, data in results.items():
                # `results` includes an `overall_summary` aggregate entry
                # whose shape is `{'summary': {...}}` — no `'files'` key.
                # Skip those non-per-file entries so the writer doesn't
                # KeyError on the per-file iteration below.
                if 'files' not in data:
                    continue
                f.write(f"## {file_type}\n\n")
                f.write(f"- **Total Files:** {data['summary']['total_files']}\n")
                f.write(f"- **Average Score:** {data['summary']['average_score']:.2f}\n")
                f.write(f"- **Score Range:** {data['summary']['min_score']} - {data['summary']['max_score']}\n\n")

                f.write("### Individual File Scores\n\n")
                for file_result in data['files']:
                    f.write(f"**{file_result['filename']}** (Avg: {file_result['average']:.2f})\n")
                    for metric, score in file_result['scores'].items():
                        f.write(f"- {metric}: {score}\n")
                    f.write("\n")
        
        print(f"Saved evaluation results: {json_path}")

def main(model_name, exp_name, textbook_path: Optional[str] = None,
         verifier_samples: int = 1):
    """
    Main function to process course materials.

    When `textbook_path` is set, additionally runs the citation-verification
    pass (the `GroundingAgent`) on top of the existing rubric-scoring and
    validation flow, and writes a `grounding_results/` directory alongside
    the standard `evaluation_results/` and `validation_reports/` outputs.

    ``verifier_samples`` controls the verifier's self-consistency voting:
    1 = single call per citation (backward-compatible default), N>1 = N
    calls per citation with median + majority-vote aggregation. Only
    meaningful when ``textbook_path`` is set.
    """
    print("Starting Course Material Evaluation System...")

    system = CourseEvaluationSystem(
        model_name, exp_name,
        textbook_path=textbook_path,
        verifier_samples=verifier_samples,
    )
    root_dir = Path(f"exp/{exp_name}")

    # Collect all files to process
    file_data = {
        'learning_objectives': [],
        'syllabus': [],
        'assessment': [],
        'slide_content': [],
        'slide_scripts': []
    }
    
    # Process root level files
    root_files = ['result_instructional_goals.md', 'result_syllabus_design.md']
    for filename in root_files:
        filepath = root_dir / filename
        if filepath.exists():
            content = system.read_file_content(str(filepath))
            file_type = system.map_file_to_type(filename)
            
            if content and file_type != 'Unknown':
                file_data[file_type].append({
                    'filename': filename,
                    'content': content,
                    'filepath': str(filepath)
                })
    
    # Process chapter folders
    for chapter_dir in root_dir.glob("chapter_*"):
        if chapter_dir.is_dir():
            chapter_files = ['slides.tex', 'assessment.md', 'script.md']
            for filename in chapter_files:
                filepath = chapter_dir / filename
                if filepath.exists():
                    content = system.read_file_content(str(filepath))
                    file_type = system.map_file_to_type(filename)
                    
                    if content and file_type != 'Unknown':
                        file_data[file_type].append({
                            'filename': f"{chapter_dir.name}_{filename}",
                            'content': content,
                            'filepath': str(filepath)
                        })

    print("Files collected. Starting evaluation...")

    # Run evaluation agent
    evaluation_results = system.evaluator.evaluate_files(file_data)
    system.save_evaluation_results(evaluation_results)
    
    print("Evaluation complete!")
    
    # Run validation agents
    for file_type, files in file_data.items():
        for file_info in files:
            if file_info['content']:
                # Program Chair validation
                print(f"Program Chair validating {file_info['filename']}...")
                pc_evaluation = system.program_chair.evaluate_content(
                    file_type, file_info['filename'], file_info['content']
                )
                system.save_validation_report(
                    "Program_Chair", file_type, file_info['filename'], pc_evaluation
                )
                
                # Test Student validation
                print(f"Test Student validating {file_info['filename']}...")
                ts_evaluation = system.test_student.evaluate_content(
                    file_type, file_info['filename'], file_info['content']
                )
                system.save_validation_report(
                    "Test_Student", file_type, file_info['filename'], ts_evaluation
                )
    
    print("Validation complete.")

    # Grounding verification — runs only when --use-textbook was set.
    # Walks the same file_data and scores every citation token in-place.
    if system.grounding_agent is not None:
        print("\n" + "="*50)
        print("CITATION VERIFICATION (GROUNDING)")
        print("="*50)
        grounding_results = system.score_grounding(file_data)
        system.save_grounding_results(grounding_results)

        ov = grounding_results.get("overall", {})
        if ov.get("n_citations_total"):
            print(f"\n  Total citations: {ov['n_citations_total']}")
            print(f"  Supported (≥4):  {ov['n_supported_total']}")
            print(f"  Unsupported (<3): {ov['n_unsupported_total']}")
            print(f"  Malformed:        {ov['n_malformed_total']}")
            if ov["faithfulness_mean"] is not None:
                print(f"  Faithfulness:     {ov['faithfulness_mean']:.2f} / 5.0")
                print(f"  Precision:        {ov['citation_precision']:.1%}")
            fmc = ov.get("failure_mode_counts") or {}
            if any(fmc.values()):
                total_resolved = sum(fmc.values()) or 1
                print(f"\n  Failure-mode breakdown (resolved citations):")
                for mode in (
                    "good", "loose_paraphrase", "hallucination",
                    "retrieval_bad", "wrong_chunk_cited", "judge_uncertain",
                ):
                    count = fmc.get(mode, 0)
                    if count:
                        pct = (count / total_resolved) * 100.0
                        print(f"    {mode:20s} {count:4d}  ({pct:.1f}%)")
        else:
            print("\n  No citation tokens found in the generated content.")
            print("  (Was --use-textbook set on the original `python run.py` invocation?)")

    # Print summary
    print("\n" + "="*50)
    print("EVALUATION SUMMARY")
    print("="*50)
    for file_type, data in evaluation_results.items():
        print(f"\n{file_type}:")
        print(f"  Files: {data['summary']['total_files']}")
        print(f"  Average Score: {data['summary']['average_score']:.2f}")
        print(f"  Score Range: {data['summary']['min_score']} - {data['summary']['max_score']}")

if __name__ == "__main__":
    with open("config.json", "r") as f:
        config = json.load(f)
    os.environ["OPENAI_API_KEY"] = config.get("OPENAI_API_KEY", "")

    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Run evaluation ......")
    parser.add_argument(
        "--model", 
        type=str,
        default="gpt-4o-mini",
        help="Model name to use for evaluation"
    )

    parser.add_argument(
        "--exp",
        type=str,
        default="test",
        help="Experiment name for logging"
    )

    parser.add_argument(
        "--use-textbook",
        dest="textbook_path",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Run citation verification against this textbook (PDF / markdown "
            "file or directory). When omitted, only the existing rubric scoring "
            "and validation reports are produced."
        ),
    )

    parser.add_argument(
        "--verifier-samples",
        dest="verifier_samples",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Number of times to ask the judge for each citation, then "
            "aggregate (median score + majority-vote failure mode). N=1 "
            "(default) is the single-call behavior — backward-compatible "
            "with all prior runs. N=3 trades roughly 3× verifier API cost "
            "for a tighter noise floor (±0.16 → ~±0.05 per-citation). "
            "Only meaningful when --use-textbook is set."
        ),
    )

    args = parser.parse_args()
    main(
        model_name=args.model,
        exp_name=args.exp,
        textbook_path=args.textbook_path,
        verifier_samples=args.verifier_samples,
    )