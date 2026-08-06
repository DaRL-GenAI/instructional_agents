"""
OptimizeSlidesDeliberation - Per-chapter slide optimization using the Deliberation pattern.

This module is the optimize-mode counterpart to SlidesDeliberation in slides.py.
It uses the same Agent + Deliberation abstractions from agents.py to orchestrate
multi-agent discussions for analyzing and improving existing slide content.
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from src.agents import Agent, Deliberation, LLM
from src.slides import SlideUtils
from src.slide_knowledge_base import SlideKnowledgeBase
from src.slide_refiner import SlideRefiner


class OptimizeSlidesDeliberation:
    """
    Orchestrates per-chapter slide optimization using the Deliberation pattern.

    Two-phase deliberation:
      1. AnalysisDeliberation: Content Analyst + Improvement Advisor discuss existing slides
         -> Analysis Summarizer produces structured analysis and recommendations
      2. EnhancementDeliberation (per-slide): Content Enhancer + LaTeX Generator discuss
         how to improve each slide -> Enhancement Summarizer produces final LaTeX frames
    """

    def __init__(
        self,
        id: str,
        name: str,
        agents: Dict[str, Agent],
        llm: LLM,
        output_dir: str,
        knowledge_base: SlideKnowledgeBase,
    ):
        """
        Initialize OptimizeSlidesDeliberation.

        Args:
            id: Unique identifier (e.g. "optimize_chapter_1")
            name: Human-readable name (e.g. "Optimize - Chapter 1: Intro to ML")
            agents: Dictionary of agents keyed by role:
                - content_analyst, improvement_advisor, analysis_summarizer
                - content_enhancer, latex_generator, enhance_summarizer
            llm: LLM instance
            output_dir: Directory to save output files
            knowledge_base: Pre-loaded SlideKnowledgeBase for this chapter
        """
        self.id = id
        self.name = name
        self.agents = agents
        self.llm = llm
        self.output_dir = output_dir
        self.knowledge_base = knowledge_base

        os.makedirs(output_dir, exist_ok=True)

    def run(
        self,
        chapter_slides: List[Dict[str, Any]],
        user_requirements: str,
        user_feedback: Optional[Dict[str, Any]] = None,
        mode: str = "regenerate",
    ) -> Dict[str, Any]:
        """
        Run the optimization deliberation for a chapter.

        Args:
            chapter_slides: List of slide dicts from the knowledge base
                (each has: title, content, slide_number, etc.)
            user_requirements: User's requirements for improvement
            user_feedback: Optional user feedback dict (e.g. {"slides": "...", "overall": "..."})
            mode: Improvement strategy:
                - "regenerate" (default): per-slide multi-agent deliberation that
                  rewrites every slide from scratch.
                - "refine": localized, frame-level rewrite via SlideRefiner. Builds a
                  baseline deck from the existing slides, then surgically edits only the
                  frames most relevant to the feedback, leaving the rest untouched.

        Returns:
            Dict with success status, file paths, and statistics
        """
        if user_feedback is None:
            user_feedback = {"slides": "", "overall": ""}

        if mode not in ("regenerate", "refine"):
            raise ValueError(f"Unknown optimize mode: {mode!r} (expected 'regenerate' or 'refine')")

        print(f"\n{'='*60}")
        print(f"Starting Optimize Deliberation: {self.name}")
        print(f"Mode: {mode}")
        print(f"{'='*60}\n")
        print(f"Slides to optimize: {len(chapter_slides)}")
        print(f"User requirements: {user_requirements[:200]}...")

        total_time = 0
        total_tokens = 0

        # ── Phase 1: Analysis Deliberation ──────────────────────────
        print(f"\n{'#'*50}")
        print(f"Phase 1: Content Analysis & Recommendations")
        print(f"{'#'*50}\n")

        analysis_result, analysis_time, analysis_tokens = self._run_analysis_deliberation(
            chapter_slides, user_requirements
        )
        total_time += analysis_time
        total_tokens += analysis_tokens

        # Save analysis result
        analysis_path = os.path.join(self.output_dir, "analysis.md")
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(f"# Content Analysis\n\n{analysis_result}")
        print(f"Analysis saved to: {analysis_path}")

        # Get LaTeX template (shared by both modes)
        latex_template = SlideUtils.get_latex_template(catalog=False)
        latex_prefix, latex_suffix = SlideUtils.parse_latex_template(latex_template)

        # ── Phase 2: Improve slides (mode-dependent) ────────────────
        if mode == "refine":
            print(f"\n{'#'*50}")
            print(f"Phase 2: Localized Frame-level Refinement")
            print(f"{'#'*50}\n")

            full_latex, enhanced_frames, enhanced_content_list, refine_info = self._refine_slides(
                chapter_slides, analysis_result, user_requirements, user_feedback,
                latex_prefix, latex_suffix,
            )
        else:
            print(f"\n{'#'*50}")
            print(f"Phase 2: Slide Enhancement & LaTeX Generation")
            print(f"{'#'*50}\n")

            refine_info = None
            enhanced_frames = []
            enhanced_content_list = []

            for idx, slide in enumerate(chapter_slides):
                slide_title = slide.get("title", f"Slide {idx + 1}")
                print(f"\n{'-'*50}")
                print(f"Enhancing Slide {idx + 1}/{len(chapter_slides)}: {slide_title}")
                print(f"{'-'*50}\n")

                # Search knowledge base for related content
                relevant_content = self.knowledge_base.search(slide_title, top_k=3)

                enhanced, frames, enh_time, enh_tokens = self._run_enhancement_deliberation(
                    slide, idx, analysis_result, user_requirements, user_feedback, relevant_content
                )
                total_time += enh_time
                total_tokens += enh_tokens

                enhanced_content_list.append(enhanced)
                enhanced_frames.extend(frames)

            # Compile full LaTeX document from the regenerated frames
            full_latex = SlideUtils.compile_latex_document(latex_prefix, enhanced_frames, latex_suffix)

        # ── Phase 3: Save ───────────────────────────────────────────
        print(f"\n{'#'*50}")
        print(f"Phase 3: Compiling Results")
        print(f"{'#'*50}\n")

        # Save LaTeX file
        latex_file = os.path.join(self.output_dir, "enhanced_slides.tex")
        with open(latex_file, "w", encoding="utf-8") as f:
            f.write(full_latex)

        # Save enhanced content summary
        content_file = os.path.join(self.output_dir, "enhanced_content.json")
        with open(content_file, "w", encoding="utf-8") as f:
            json.dump({
                "enhanced_at": datetime.now().isoformat(),
                "mode": mode,
                "original_slides_count": len(chapter_slides),
                "enhanced_slides": enhanced_content_list,
                "refine_info": refine_info,
                "user_requirements": user_requirements,
            }, f, indent=2, ensure_ascii=False)

        # Save statistics
        stats_file = os.path.join(self.output_dir, f"statistics_{self.id}.json")
        with open(stats_file, "w", encoding="utf-8") as f:
            json.dump({
                "mode": mode,
                "elapsed_time": total_time,
                "token_usage": total_tokens,
                "total_slides": len(chapter_slides),
                "total_frames": len(enhanced_frames),
            }, f, indent=2)

        print(f"\nOptimize Deliberation Complete: {self.name}")
        print(f"  LaTeX: {latex_file}")
        print(f"  Content: {content_file}")
        print(f"  Frames generated: {len(enhanced_frames)}")
        print(f"  Time: {total_time:.2f}s | Tokens: {total_tokens}")

        return {
            "success": True,
            "mode": mode,
            "latex_file": latex_file,
            "content_file": content_file,
            "analysis_file": analysis_path,
            "total_slides": len(chapter_slides),
            "total_frames": len(enhanced_frames),
            "refine_info": refine_info,
            "elapsed_time": total_time,
            "token_usage": total_tokens,
        }

    # Maximum localized-refine repair attempts per chapter deck.
    REFINE_MAX_RETRIES = 2

    def _refine_slides(
        self,
        chapter_slides: List[Dict[str, Any]],
        analysis_result: str,
        user_requirements: str,
        user_feedback: Dict[str, Any],
        latex_prefix: str,
        latex_suffix: str,
    ) -> tuple:
        """
        Localized refinement path (mode="refine").

        Builds a baseline LaTeX deck from the existing slides, then uses SlideRefiner
        to locate only the frames relevant to the feedback and rewrite just their
        bodies, leaving every other frame byte-identical.

        Returns:
            (full_latex, frames, content_list, refine_info)
        """
        # 1. Build a clean, escaped baseline deck from the existing slides.
        baseline_frames = [
            self._build_baseline_frame(slide, idx)
            for idx, slide in enumerate(chapter_slides)
        ]
        baseline_latex = SlideUtils.compile_latex_document(
            latex_prefix, baseline_frames, latex_suffix
        )

        # 2. Assemble the feedback string the refiner will act on.
        feedback_text = self._build_refine_feedback(
            analysis_result, user_requirements, user_feedback
        )

        # 3. Surgical, frame-level refinement with deterministic validation + retries.
        refiner = SlideRefiner(self.llm)
        result = refiner.refine_slides(
            content=baseline_latex,
            feedback_text=feedback_text,
            max_retries=self.REFINE_MAX_RETRIES,
        )

        full_latex = result["refined_content"]
        frames = SlideUtils.extract_latex_frames(full_latex)

        edited_indexes = {f["index"] for f in result.get("edited_frames", [])}
        print(
            f"Refine complete: status={result['slide_validation_status']}, "
            f"targeted={result.get('target_indexes')}, "
            f"edited={sorted(edited_indexes)}, retries={result.get('retries_used')}"
        )
        if result["slide_validation_status"] != "PASS":
            print("Refine validation did not fully pass:")
            for err in result.get("slide_validation_errors", []):
                print(f"  - {err}")

        content_list = [
            {
                "index": idx,
                "title": slide.get("title", f"Slide {idx + 1}"),
                "edited": idx in edited_indexes,
            }
            for idx, slide in enumerate(chapter_slides)
        ]

        refine_info = {
            "validation_status": result["slide_validation_status"],
            "validation_errors": result.get("slide_validation_errors", []),
            "target_indexes": result.get("target_indexes", []),
            "edited_frames": result.get("edited_frames", []),
            "retries_used": result.get("retries_used"),
            "locator_response": result.get("locator_response"),
        }

        return full_latex, frames, content_list, refine_info

    def _build_baseline_frame(self, slide: Dict[str, Any], idx: int) -> str:
        """Build a single valid Beamer frame from an existing slide dict."""
        title = slide.get("title", f"Slide {idx + 1}")
        content = slide.get("content", slide.get("text", "")) or ""

        title_tex = self._escape_latex(title)

        # Turn the slide content into a small, escaped itemize body.
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        lines = lines[:8]  # keep frames presentation-sized
        if lines:
            items = "\n".join(
                f"        \\item {self._escape_latex(ln[:300])}" for ln in lines
            )
            body = f"    \\begin{{itemize}}\n{items}\n    \\end{{itemize}}"
        else:
            body = f"    {self._escape_latex(content[:300]) or '~'}"

        return (
            f"\\begin{{frame}}[fragile]\n"
            f"    \\frametitle{{{title_tex}}}\n"
            f"{body}\n"
            f"\\end{{frame}}"
        )

    @staticmethod
    def _escape_latex(text: str) -> str:
        """Escape LaTeX special characters so baseline frames compile cleanly."""
        if not text:
            return ""
        # Stash backslashes behind a sentinel so the braces in their replacement
        # (\textbackslash{}) don't get re-escaped by the {}-escaping below.
        sentinel = "\x00BSLASH\x00"
        text = text.replace("\\", sentinel)
        for ch, esc in (
            ("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
            ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
        ):
            text = text.replace(ch, esc)
        # These insert braces too, but only after {}-escaping has run.
        text = text.replace("~", r"\textasciitilde{}")
        text = text.replace("^", r"\textasciicircum{}")
        text = text.replace(sentinel, r"\textbackslash{}")
        return text

    def _build_refine_feedback(
        self,
        analysis_result: str,
        user_requirements: str,
        user_feedback: Dict[str, Any],
    ) -> str:
        """Combine requirements, analysis, and human feedback into one feedback string."""
        parts = []
        if user_requirements:
            parts.append(f"USER REQUIREMENTS:\n{user_requirements}")
        slides_fb = (user_feedback or {}).get("slides", "")
        overall_fb = (user_feedback or {}).get("overall", "")
        if slides_fb:
            parts.append(f"USER FEEDBACK ON SLIDES:\n{slides_fb}")
        if overall_fb:
            parts.append(f"OVERALL USER FEEDBACK:\n{overall_fb}")
        if analysis_result:
            parts.append(f"ANALYSIS & RECOMMENDATIONS:\n{analysis_result[:3000]}")
        return "\n\n".join(parts)

    def _run_analysis_deliberation(
        self,
        chapter_slides: List[Dict[str, Any]],
        user_requirements: str,
    ) -> tuple:
        """
        Run the analysis phase as a proper Deliberation.

        Content Analyst + Improvement Advisor discuss the existing slides,
        then the Analysis Summarizer produces a structured report.

        Returns:
            (analysis_text, elapsed_time, token_usage)
        """
        # Format existing slide content as context
        slides_summary = self._format_slides_for_context(chapter_slides)

        # Get knowledge base summary for additional context
        kb_summary = self.knowledge_base.get_all_content_summary()
        kb_info = f"Knowledge base contains {kb_summary.get('total_chunks', 0)} slide chunks."

        # Create the Analysis Deliberation using the standard Deliberation class
        analysis_deliberation = Deliberation(
            id=f"{self.id}_analysis",
            name=f"Content Analysis - {self.name}",
            agents=[
                self.agents["content_analyst"],
                self.agents["improvement_advisor"],
            ],
            summary_agent=self.agents["analysis_summarizer"],
            max_rounds=1,
            instruction_prompt=(
                "Analyze the existing slide content below. The Content Analyst should evaluate "
                "structure, coverage, quality, strengths, and weaknesses. The Improvement Advisor "
                "should then propose specific, actionable recommendations for enhancement.\n\n"
                f"Knowledge Base Info: {kb_info}"
            ),
            output_format="md",
        )

        # Run the deliberation
        result, elapsed_time, token_usage = analysis_deliberation.run(
            current_context=slides_summary,
            user_suggestion=user_requirements,
        )

        return result, elapsed_time, token_usage

    def _run_enhancement_deliberation(
        self,
        slide: Dict[str, Any],
        slide_idx: int,
        analysis_result: str,
        user_requirements: str,
        user_feedback: Dict[str, Any],
        relevant_content: List[Dict[str, Any]],
    ) -> tuple:
        """
        Run the enhancement phase for a single slide as a proper Deliberation.

        Content Enhancer + LaTeX Generator discuss the slide improvement,
        then the Enhancement Summarizer produces the final LaTeX frames.

        Returns:
            (enhanced_content_dict, latex_frames_list, elapsed_time, token_usage)
        """
        title = slide.get("title", f"Slide {slide_idx + 1}")
        content = slide.get("content", slide.get("text", ""))

        # Format relevant content from knowledge base search
        related_text = ""
        if relevant_content:
            related_items = []
            for i, item in enumerate(relevant_content[:3]):
                item_content = item.get("content", "")[:300]
                related_items.append(f"  Related {i+1}: {item_content}")
            related_text = "\n".join(related_items)

        # Format user feedback
        feedback_text = ""
        if user_feedback:
            slides_fb = user_feedback.get("slides", "")
            overall_fb = user_feedback.get("overall", "")
            if slides_fb:
                feedback_text += f"\nUser feedback on slides: {slides_fb}"
            if overall_fb:
                feedback_text += f"\nOverall user feedback: {overall_fb}"

        # Build the context for this slide's enhancement
        slide_context = (
            f"Original Slide Title: {title}\n"
            f"Original Content:\n{content[:2000]}\n\n"
            f"Analysis & Recommendations:\n{analysis_result[:2000]}\n"
        )
        if related_text:
            slide_context += f"\nRelated Content from Knowledge Base:\n{related_text}\n"
        if feedback_text:
            slide_context += f"\n{feedback_text}\n"

        # Create the Enhancement Deliberation
        enhancement_deliberation = Deliberation(
            id=f"{self.id}_enhance_{slide_idx}",
            name=f"Enhance Slide: {title}",
            agents=[
                self.agents["content_enhancer"],
                self.agents["latex_generator"],
            ],
            summary_agent=self.agents["enhance_summarizer"],
            max_rounds=1,
            instruction_prompt=(
                "Improve this slide based on the analysis and user requirements. "
                "The Content Enhancer should propose enhanced content that maintains the original "
                "structure while incorporating improvements. The LaTeX Generator should then discuss "
                "how to best present this content in beamer format.\n\n"
                "The final summary MUST contain the enhanced LaTeX frames using \\begin{frame}[fragile] ... \\end{frame} format. "
                "Generate at most 3 frames per slide. Follow these LaTeX guidelines:\n"
                "1. Don't use non-English characters directly (use LaTeX commands like $\\gamma$)\n"
                "2. Escape special characters (use \\& instead of &)\n"
                "3. Use itemize/enumerate for lists, block for highlights, lstlisting for code\n"
                "4. Keep each frame focused and not overcrowded"
            ),
            output_format="tex",
        )

        # Run the deliberation
        result, elapsed_time, token_usage = enhancement_deliberation.run(
            current_context=slide_context,
            user_suggestion=user_requirements,
        )

        # Extract LaTeX frames from the deliberation result
        frames = SlideUtils.extract_latex_frames(result)
        if not frames:
            # Fallback: create a simple frame from the result
            frames = [
                f"\\begin{{frame}}[fragile]\n"
                f"    \\frametitle{{{title}}}\n"
                f"    {content[:500]}\n"
                f"\\end{{frame}}"
            ]

        # Build enhanced content record
        enhanced_content = {
            "original_title": title,
            "enhanced_title": title,
            "original_content": content,
            "enhanced_content": result,
            "frames_count": len(frames),
        }

        return enhanced_content, frames, elapsed_time, token_usage

    def _format_slides_for_context(self, slides: List[Dict[str, Any]]) -> str:
        """Format slide list into a text summary for deliberation context."""
        lines = [f"Existing Slides ({len(slides)} total):\n"]
        for i, slide in enumerate(slides):
            title = slide.get("title", f"Slide {i+1}")
            content = slide.get("content", slide.get("text", ""))
            # Truncate long content
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"--- Slide {i+1}: {title} ---")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)
