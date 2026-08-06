"""
ADDIEOptimizer and OptimizeRunner - Optimize mode for the ADDIE framework.

This module is the optimize-mode counterpart to ADDIE + ADDIERunner in ADDIE.py.
It orchestrates the optimization of existing slide materials using the Deliberation
pattern, mirroring the structure of the generate-mode workflow.
"""

import os
import json
import re
import time
from typing import List, Dict, Any, Optional
from pathlib import Path

from src.agents import LLM, Agent
from src.optimize import OptimizeSlidesDeliberation
from src.pdf_processor import PDFSlideProcessor
from src.slide_knowledge_base import SlideKnowledgeBase
from src.compile import LaTeXCompiler

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


class ADDIEOptimizer:
    """
    Optimize mode configuration and agent creation.

    Mirrors the ADDIE class: creates agents and delegates execution to OptimizeRunner.
    """

    def __init__(self, model_name: str = "gpt-4o-mini", copilot: bool = False, seed: int = None, temperature: float = None):
        self.model_name = model_name
        self.copilot = copilot
        self.llm = LLM(model_name=model_name, seed=seed, temperature=temperature)

    def create_optimize_agents(self) -> Dict[str, Agent]:
        """
        Create all agents needed for the optimization deliberations.

        Returns:
            Dictionary of agents keyed by role name.
        """
        return {
            # Analysis phase agents
            "content_analyst": Agent(
                name="Content Analyst",
                role="Expert in analyzing educational content structure and quality",
                llm=self.llm,
                system_prompt=(
                    "You are a Content Analyst specialized in reviewing educational slide decks. "
                    "Your task is to analyze the structure, content quality, coverage, and organization "
                    "of existing slide materials. Identify strengths, weaknesses, gaps, and areas for "
                    "improvement. Provide a thorough, structured analysis."
                ),
            ),
            "improvement_advisor": Agent(
                name="Improvement Advisor",
                role="Educational design consultant providing actionable improvement recommendations",
                llm=self.llm,
                system_prompt=(
                    "You are an Improvement Advisor who provides specific, actionable recommendations "
                    "for enhancing educational slide decks. Based on the Content Analyst's findings and "
                    "the user's requirements, propose concrete improvements including content additions, "
                    "structural reorganization, and pedagogical enhancements."
                ),
            ),
            "analysis_summarizer": Agent(
                name="Analysis Summarizer",
                role="Summarizer for content analysis discussions",
                llm=self.llm,
                system_prompt=(
                    "You are a Summarizer for content analysis discussions. Based on the discussion "
                    "between the Content Analyst and Improvement Advisor, produce a structured report "
                    "that includes: (1) content analysis with strengths and weaknesses, (2) specific "
                    "improvement recommendations prioritized by importance, and (3) an action plan."
                ),
                output_constraint="Only generate the structured analysis report, no other text.",
            ),
            # Enhancement phase agents
            "content_enhancer": Agent(
                name="Content Enhancer",
                role="Expert in enhancing educational slides by applying improvement suggestions",
                llm=self.llm,
                system_prompt=(
                    "You are a Content Enhancer specialized in improving educational slides. "
                    "Your task is to take original slide content and enhancement recommendations, "
                    "then propose improved versions that incorporate the suggestions while maintaining "
                    "the original structure and key concepts. Focus on clarity, examples, and "
                    "educational value."
                ),
            ),
            "latex_generator": Agent(
                name="LaTeX Generator",
                role="Expert in generating LaTeX beamer slides from enhanced content",
                llm=self.llm,
                system_prompt=(
                    "You are a LaTeX Generator responsible for creating well-formatted beamer slides "
                    "from enhanced educational content. Discuss with the Content Enhancer about the "
                    "best way to present the improved content, then produce clean, compilable LaTeX "
                    "code using the beamer class format."
                ),
            ),
            "enhance_summarizer": Agent(
                name="Enhancement Summarizer",
                role="Summarizer for slide enhancement discussions",
                llm=self.llm,
                system_prompt=(
                    "You are a Summarizer for slide enhancement discussions. Based on the discussion "
                    "between the Content Enhancer and LaTeX Generator, produce the final enhanced "
                    "LaTeX frames. Your output MUST contain valid LaTeX beamer frames using "
                    "\\begin{frame}[fragile] ... \\end{frame} format."
                ),
                output_constraint=(
                    "Only generate the final LaTeX frames. Each frame must use "
                    "\\begin{frame}[fragile] ... \\end{frame} format."
                ),
            ),
        }

    def run(
        self,
        storage_id: str,
        user_requirements: str,
        output_dir: str = "./exp/optimize/",
        exp_name: Optional[str] = None,
        chapter_name: Optional[str] = None,
        mode: str = "regenerate",
    ) -> Dict[str, Any]:
        """
        Run the optimize workflow.

        Args:
            storage_id: ID of the stored PDF files
            user_requirements: User's requirements for improvement
            output_dir: Base output directory
            exp_name: Experiment name
            chapter_name: Specific chapter to optimize (None = all chapters)
            mode: "regenerate" (per-slide full rewrite) or "refine" (localized
                frame-level rewrite via SlideRefiner)

        Returns:
            Results dict with per-chapter outcomes and overall summary
        """
        runner = OptimizeRunner(self, output_dir)
        return runner.run(storage_id, user_requirements, exp_name, chapter_name, mode)


class OptimizeRunner:
    """
    Orchestrates the optimize workflow.

    Mirrors ADDIERunner: handles chapter detection, knowledge base creation,
    deliberation instantiation, and result compilation.
    """

    def __init__(self, optimizer: ADDIEOptimizer, output_dir: str):
        self.optimizer = optimizer
        self.output_dir = output_dir
        self.processor = PDFSlideProcessor()

    def run(
        self,
        storage_id: str,
        user_requirements: str,
        exp_name: Optional[str] = None,
        chapter_name: Optional[str] = None,
        mode: str = "regenerate",
    ) -> Dict[str, Any]:
        """
        Run the full optimization workflow.

        Args:
            storage_id: ID of the stored PDF files
            user_requirements: User's requirements for improvement
            exp_name: Experiment name for organizing outputs
            chapter_name: Specific chapter to optimize (None = all)
            mode: "regenerate" or "refine" (localized frame-level rewrite)

        Returns:
            Results dict
        """
        start_time = time.time()

        print("\n" + "=" * 80)
        print("INSTRUCTIONAL DESIGN WORKFLOW - OPTIMIZE MODE")
        print("=" * 80 + "\n")
        print(f"Storage ID: {storage_id}")
        print(f"Requirements: {user_requirements[:200]}")
        if chapter_name:
            print(f"Target chapter: {chapter_name}")
        print()

        os.makedirs(self.output_dir, exist_ok=True)

        # Step 1: Detect chapters
        if chapter_name:
            chapters = [chapter_name]
        else:
            chapters = self._detect_chapters(storage_id)

        if not chapters:
            return {
                "success": False,
                "error": "No chapters detected. Please specify a chapter name.",
                "chapters": [],
            }

        print(f"Chapters to optimize: {chapters}\n")

        # Step 2: Process each chapter
        results = {
            "success": True,
            "total_chapters": len(chapters),
            "chapters": [],
        }

        for chapter_idx, ch_name in enumerate(chapters):
            print(f"\n{'#' * 60}")
            print(f"Chapter {chapter_idx + 1}/{len(chapters)}: {ch_name}")
            print(f"{'#' * 60}\n")

            try:
                chapter_result = self._optimize_chapter(
                    storage_id, ch_name, user_requirements, exp_name, mode
                )
                results["chapters"].append(chapter_result)
            except Exception as e:
                print(f"Error optimizing chapter {ch_name}: {e}")
                import traceback
                traceback.print_exc()
                results["chapters"].append({
                    "success": False,
                    "chapter": ch_name,
                    "error": str(e),
                })

        # Step 3: Compile all LaTeX files
        print(f"\n{'#' * 60}")
        print("Compiling LaTeX files")
        print(f"{'#' * 60}\n")

        compiler = LaTeXCompiler(self.output_dir)
        compiler.compile_all()

        # Summary
        execution_time = time.time() - start_time
        hours, rem = divmod(execution_time, 3600)
        minutes, seconds = divmod(rem, 60)

        successful = [r for r in results["chapters"] if r.get("success")]
        failed = [r for r in results["chapters"] if not r.get("success")]

        print("\n" + "=" * 80)
        print(f"OPTIMIZE WORKFLOW COMPLETED IN: {int(hours):02d}:{int(minutes):02d}:{seconds:.2f}")
        print(f"  Chapters: {len(successful)} succeeded, {len(failed)} failed")
        print("=" * 80 + "\n")

        results["execution_time"] = execution_time

        return results

    def _optimize_chapter(
        self,
        storage_id: str,
        chapter_name: str,
        user_requirements: str,
        exp_name: Optional[str] = None,
        mode: str = "regenerate",
    ) -> Dict[str, Any]:
        """
        Optimize a single chapter.

        Steps:
          1. Extract PDF content for this chapter
          2. Build a knowledge base from extracted content
          3. Create and run OptimizeSlidesDeliberation

        Returns:
            Chapter optimization result dict
        """
        # 1. Extract relevant content
        print(f"Extracting content for chapter: {chapter_name}")
        extracted_data = self.processor.extract_by_requirement(
            storage_id=storage_id,
            user_requirements=user_requirements,
            target_chapters=[chapter_name],
        )

        if extracted_data["total_extracted_files"] == 0:
            return {
                "success": False,
                "chapter": chapter_name,
                "error": f"No content found for {chapter_name}",
            }

        # 2. Create knowledge base
        kb_name = f"{storage_id}_chapter_{chapter_name.replace(' ', '_').replace('Chapter', 'Ch')}"
        if exp_name:
            kb_dir = f"./exp/{exp_name}/knowledge_base"
        else:
            kb_dir = os.path.join(self.output_dir, "knowledge_base")

        print(f"Creating knowledge base: {kb_name}")
        kb = SlideKnowledgeBase(kb_name, kb_dir=kb_dir)
        kb.create_from_extracted_data(extracted_data, chapter_filter=chapter_name)

        # 3. Get chapter slides from knowledge base
        chapter_slides = self._get_chapter_slides(kb)
        if not chapter_slides:
            return {
                "success": False,
                "chapter": chapter_name,
                "error": "No slides extracted from knowledge base",
            }

        # 4. Create and run OptimizeSlidesDeliberation
        chapter_dir_name = chapter_name.replace(" ", "_").lower()
        chapter_dir = os.path.join(self.output_dir, chapter_dir_name)

        agents = self.optimizer.create_optimize_agents()

        deliberation = OptimizeSlidesDeliberation(
            id=f"optimize_{chapter_dir_name}",
            name=f"Optimize - {chapter_name}",
            agents=agents,
            llm=self.optimizer.llm,
            output_dir=chapter_dir,
            knowledge_base=kb,
        )

        result = deliberation.run(chapter_slides, user_requirements, mode=mode)
        result["chapter"] = chapter_name
        result["knowledge_base_name"] = kb_name

        return result

    def _get_chapter_slides(self, kb: SlideKnowledgeBase) -> List[Dict[str, Any]]:
        """
        Get all slides from a knowledge base, sorted by slide number.
        """
        chunks_file = kb.kb_dir / "chunks.json"
        if chunks_file.exists():
            with open(chunks_file, "r", encoding="utf-8") as f:
                slides = json.load(f)
        elif hasattr(kb, "chunks") and kb.chunks:
            slides = kb.chunks
        else:
            return []

        # Sort by slide number
        slides = sorted(
            slides,
            key=lambda x: x.get(
                "slide_number", x.get("metadata", {}).get("slide_number", 0)
            ),
        )
        return slides

    def _detect_chapters(self, storage_id: str) -> List[str]:
        """
        Auto-detect chapters from stored PDF files.

        Tries: filename patterns → PDF content scan → fallback to sequential numbering.
        """
        storage_dir = self.processor.output_dir / "temp_storage" / storage_id

        if not storage_dir.exists():
            return []

        metadata_file = storage_dir / "metadata.json"
        if not metadata_file.exists():
            return []

        with open(metadata_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        chapters = set()

        # Try extracting from filenames
        for file_info in metadata["files"]:
            filename = file_info["filename"]
            chapter = self.processor._extract_chapter_from_filename(filename)
            if chapter:
                chapters.add(chapter)

        # If filenames didn't work, scan PDF content
        if not chapters and PDFPLUMBER_AVAILABLE:
            pdf_files = [Path(f["stored_path"]) for f in metadata["files"]]
            for pdf_file in pdf_files:
                if not pdf_file.exists():
                    continue
                try:
                    with pdfplumber.open(pdf_file) as pdf:
                        for page_num in range(min(5, len(pdf.pages))):
                            page = pdf.pages[page_num]
                            text = page.extract_text() or ""
                            for pattern in [r"chapter\s*(\d+)", r"第\s*(\d+)\s*章"]:
                                for match in re.findall(pattern, text, re.IGNORECASE):
                                    chapters.add(f"Chapter {match}")
                except Exception as e:
                    print(f"Warning: Could not scan {pdf_file.name}: {e}")

        # Fallback: use file order
        if not chapters:
            pdf_files = sorted([Path(f["stored_path"]) for f in metadata["files"]])
            for i, _ in enumerate(pdf_files, 1):
                chapters.add(f"Chapter {i}")

        # Sort by chapter number
        def extract_num(name: str) -> int:
            m = re.search(r"\d+", name)
            return int(m.group()) if m else 0

        return sorted(list(chapters), key=extract_num)
