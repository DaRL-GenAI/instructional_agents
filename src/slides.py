import os
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from src.agents import (
    LLM,
    Agent,
)
from src.beamer_preflight import normalize_beamer_source
from src.frontend_slides import parse_beamer_source
from src.frontend_slides import render_speaker_notes_markdown


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
        current_frame: Optional[str] = None,
        user_feedback: Optional[Dict] = None,
        style_guidance: str = "",
    ) -> str:
        """Generate prompt for LaTeX frame creation"""
        feedback_text = ""
        if user_feedback:
            feedback_text = f"""
User Feedback:
[For slides]{json.dumps(user_feedback.get('slides', {}), indent=2)}
[For overall]{json.dumps(user_feedback.get('overall', {}), indent=2)}
"""
        
        current_frame_text = ""
        if current_frame:
            current_frame_text = f"""
Current LaTeX frame (for reference):
```latex
{current_frame}
```
"""
        
        description_text = f"\nSlide Description: {description}" if description else ""
        style_text = (
            f"\nSelected Course Slide Style Guidance:\n{style_guidance}\n"
            "Realize any color described in the style guidance as an inline hex "
            "value (e.g. \\textcolor[HTML]{0047AB}{...}), never as a new named "
            "color.\n"
            if style_guidance
            else ""
        )
        
        return f"""
Based on the following slide content, generate LaTeX code for a presentation slide.

Slide Title: {title}{description_text}

Detailed Content:
{content[:2000]}

{current_frame_text}{feedback_text}{style_text}

Please generate the LaTeX code for this slide using the beamer class format.
You should first summarize the content and extract key points to A BRIEF SUMMARY.

IMPORTANT: Return exactly one Beamer frame for this outline slide. Summarize and
prioritize the source content so it fits within that single frame.

The frame should be structured as follows:
\\begin{{frame}}[fragile]
    \\frametitle{{Slide Title}}
    % Content goes here
\\end{{frame}}

Guidelines:
1. Don't use non-English characters directly, e.g. use $\\gamma$ instead of γ, $\\epsilon$ instead of ε
2. If any symbol has a special meaning, add a backslash. e.g. use \\& instead of &
3. Use bullet points or numbered lists for clarity
4. Keep the frame focused and not overcrowded
5. Never nest itemize/enumerate environments more than 3 levels deep; prefer 2 levels for readability
6. Colors: the preamble is fixed, so you cannot add \\definecolor. Only use standard color names (red, blue, teal, gray, ...), color names already defined in the template or current frame, or inline hex via \\textcolor[HTML]{{RRGGBB}}{{...}}. Never invent named colors such as electricblue
7. Never nest display-math environments. For multiple aligned lines, use \\begin{{align*}} by itself, or put \\begin{{aligned}} inside \\begin{{equation}}. Never put align, align*, gather, or multline inside equation.

Use LaTeX features like:
- \\begin{{itemize}} for bullet points
- \\begin{{enumerate}} for numbered lists
- \\begin{{block}}{{Title}} for highlighted blocks
- \\begin{{lstlisting}} for code snippets
- \\begin{{equation}} for mathematical formulas

Your response should contain exactly one frame, from \\begin{{frame}}[fragile]
to \\end{{frame}}.
"""
    
    @staticmethod
    def generate_latex_frame_from_content(
        agent: Agent,
        title: str,
        content: str,
        description: Optional[str] = None,
        current_frame: Optional[str] = None,
        user_feedback: Optional[Dict] = None,
    ) -> Optional[str]:
        """Generate exactly one LaTeX frame from content using an Agent."""
        prompt = SlideUtils.generate_latex_frame_prompt(
            title=title,
            content=content,
            description=description,
            current_frame=current_frame,
            user_feedback=user_feedback,
        )
        
        agent.reset_history()
        response, _, _ = agent.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False
        )
        
        frames = SlideUtils.extract_latex_frames(response)
        return frames[0] if len(frames) == 1 else None


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
                 slide_style_guidance: str = "",
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
        self.slide_style_guidance = slide_style_guidance

        # Initialize containers for results
        self.slides_outline = []
        self.latex_dict = {}
        self.slides_script = {}
        self.assessment_template = {}  # New: assessment template
        self.assessment_content = {}   # New: assessment content

    # ------------------------------------------------------------------ #
    # Checkpoint helpers (resume support)                                #
    # ------------------------------------------------------------------ #
    CHECKPOINT_FILENAME = "_checkpoint.json"
    CHECKPOINT_VERSION = 2

    def _checkpoint_path(self) -> str:
        return os.path.join(self.output_dir, self.CHECKPOINT_FILENAME)

    def _save_checkpoint(self, done_steps, last_slide_idx=None):
        """Persist mid-run state so a crash can be resumed.

        Writes atomically via rename to avoid a truncated checkpoint if the
        process dies mid-write.
        """
        payload = {
            "version": self.CHECKPOINT_VERSION,
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
        if ckpt.get("version") != self.CHECKPOINT_VERSION:
            print(
                f"[resume] Ignoring incompatible checkpoint version "
                f"{ckpt.get('version')!r}; expected {self.CHECKPOINT_VERSION}."
            )
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

            # Step 5.2: Generate one LaTeX frame for the outline slide
            self._generate_slide_latex(slide_idx, slide, slide_draft)

            # Step 5.3: Generate slide script
            self._generate_slide_script(slide_idx, slide, slide_draft)

            # Step 5.4: Generate slide assessment
            self._generate_slide_assessment(slide_idx, slide, slide_draft)

            # Checkpoint after every completed slide
            self._save_checkpoint(done_steps, last_slide_idx=slide_idx)
        
        # Step 6: Compile final LaTeX source
        latex_source = self._compile_latex_source()
        preflight = normalize_beamer_source(latex_source)
        latex_source = preflight.source
        if preflight.changed:
            if preflight.removed_list_wrapper_pairs:
                print(
                    "[preflight] Flattened "
                    f"{preflight.removed_list_wrapper_pairs} unsupported deep-list "
                    "wrapper(s) before saving slides.tex"
                )
            if preflight.inserted_list_closures:
                print(
                    "[preflight] Closed "
                    f"{preflight.inserted_list_closures} unclosed generated list "
                    "environment(s) before saving slides.tex"
                )
            if preflight.injected_color_definitions:
                print(
                    "[preflight] Auto-defined missing color(s) before saving "
                    f"slides.tex: {', '.join(preflight.injected_color_definitions)}"
                )
            if preflight.repaired_nested_math_environments:
                print(
                    "[preflight] Repaired "
                    f"{preflight.repaired_nested_math_environments} nested "
                    "display-math environment(s) before saving slides.tex"
                )
        
        # Step 7: Compile final slides script
        slides_script_md = self._compile_slides_script(latex_source)
        
        # Step 8: Compile final assessment
        assessment_md = self._compile_assessment()
        
        # Save the results
        latex_path = os.path.join(self.output_dir, f"slides.tex")
        script_path = os.path.join(self.output_dir, f"script.md")
        assessment_path = os.path.join(self.output_dir, f"assessment.md")

        os.makedirs(self.output_dir, exist_ok=True)
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
        """Generate slides outline using Instructional Designer agent"""
        instructional_designer = self.agents.get("instructional_designer")
        if not instructional_designer:
            raise ValueError("Instructional Designer agent not found")
        
        # Create a simple outline template example
        outline_template = """[
            {
                "slide_id": 1,
                "title": "Introduction to Topic",
                "description": "Brief overview of the main topic"
            },
            {
                "slide_id": 2,
                "title": "Key Concepts",
                "description": "Explanation of key concepts"
            }
            ]"""
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following chapter information, create a detailed slides outline in JSON format.
        
        Chapter Title: {chapter['title']}
        Chapter Description: {chapter['description']}
        
        User Feedback:
        {json.dumps(self.user_feedback, indent=2)}

        Please generate a comprehensive slides outline with about {self.catalog_dict['slides_length'] / 3} slides covering all important aspects of this chapter.
        The outline should be in JSON format with the following structure:
        
        {outline_template}
        
        Please try to use the simple and common latex grammer to guarantee the LaTeX code can be compiled successfully.
        Your response must be valid JSON that can be parsed programmatically.
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
        
        # Create the prompt for the agent
        prompt = f"""
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

        Selected Course Slide Style Guidance:
        {self.slide_style_guidance or "Use the default clear academic presentation treatment."}
        
        Please generate the initial LaTeX code with frame placeholders for each slide in the outline.
        Create exactly one frame placeholder for each slide in the outline.
        
        Example frame structure:
        \\begin{{frame}}[fragile]
            \\frametitle{{Slide Title}}
            % Content will be added here
        \\end{{frame}}

        1. Don't use non-English characters directly, e.g. use $\\gamma$ instead of γ, $\\epsilon$ instead of ε
        2. If any of symbols has a special meaning, add a slash. e.g. use \\& instead of &
        3. Colors: only use standard color names (red, blue, teal, gray, ...), colors defined in the provided template, or inline hex via \\textcolor[HTML]{{RRGGBB}}{{...}}. Never invent named colors such as electricblue, and do not add \\usepackage lines or color definitions beyond the provided template

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
        """Parse one generated placeholder frame for each outline slide."""
        frametitle_pattern = re.compile(r'\\frametitle{(.*?)}', re.DOTALL)
        frames = SlideUtils.extract_latex_frames(latex_source)
        title_frames = [frame for frame in frames if "\\titlepage" in frame]
        content_frames = [frame for frame in frames if "\\titlepage" not in frame]
        prefix, suffix = SlideUtils.parse_latex_template(latex_source)
        self.latex_prefix = prefix
        if title_frames:
            self.latex_prefix += "\n\n" + title_frames[0]
        self.latex_suffix = suffix
        self.latex_dict = {}
        for slide_idx, frame in enumerate(content_frames[: len(self.slides_outline)]):
            title_match = frametitle_pattern.search(frame)
            title = (
                title_match.group(1).strip()
                if title_match
                else self.slides_outline[slide_idx]["title"]
            )
            self.latex_dict[slide_idx] = {
                "frames": [{
                    "full_frame": frame,
                    "content": frame.strip(),
                    "title": title,
                    "frame_index": 0,
                }],
                "slide_title": title,
            }
    
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
        
        # Create the prompt for the agent
        prompt = f"""
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
        
        # Create the prompt for the agent
        prompt = f"""
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
        
        # Create the prompt for the agent
        prompt = f"""
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
        4. Any formulas, code snippets, or diagrams that would be helpful, but dont try to include any pictures in the LaTeX code.
        
        Focus on making the content educational, engaging, and aligned with the chapter's learning objectives.
        Note: Your output length needs to be kept within a reasonable range so that it can fit on a single PPT slide.
        """
        
        # Reset agent history to ensure clean context
        teaching_faculty.reset_history()
        
        # Get the response from the agent
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
        """Generate exactly one LaTeX frame for an outline slide."""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get the current LaTeX frame if it exists.
        current_frames = self.latex_dict.get(slide_idx, {}).get("frames", [])
        current_frame_text = current_frames[0]["full_frame"] if current_frames else None
        
        # Use utility function to generate prompt
        prompt = SlideUtils.generate_latex_frame_prompt(
            title=slide['title'],
            content=slide_draft,
            description=slide.get('description'),
            current_frame=current_frame_text,
            user_feedback=self.user_feedback,
            style_guidance=self.slide_style_guidance,
        )
        
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
        
        if len(frame_matches) == 1:
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
            
            frame_code = frame_matches[0]
            self.latex_dict[slide_idx]["frames"].append({
                "full_frame": frame_code,
                "content": frame_code.replace("\\begin{frame}", "").replace("\\end{frame}", "").strip(),
                "title": slide['title'],
                "frame_index": 0
            })
            print(f"Generated frame for slide: {slide['title']}")
        else:
            # Enforce the one-frame contract even when the model returns zero
            # or multiple frames.
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
            print(
                f"Generated fallback frame for slide: {slide['title']} "
                f"(expected one frame, found {len(frame_matches)})"
            )
    
    def _generate_slide_script(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate script for a slide using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get adjacent slide scripts for context
        prev_script = self.slides_script.get(slide_idx-1, {}).get("script", "") if slide_idx > 0 else ""
        current_script = self.slides_script.get(slide_idx, {}).get("script", "")
        next_script = self.slides_script.get(slide_idx+1, {}).get("script", "") if slide_idx < len(self.slides_outline)-1 else ""
        
        frame_info = ""
        if slide_idx in self.latex_dict and self.latex_dict[slide_idx]["frames"]:
            frame = self.latex_dict[slide_idx]["frames"][0]
            frame_info = f"```latex\n{frame['full_frame']}\n```"
        
        # Create the prompt for the agent
        prompt = f"""
        Based on the following slide content, generate a detailed speaking script for presenting this slide.
        
        Slide Title: {slide['title']}
        Slide Description: {slide['description']}
        
        Detailed Content:
        {slide_draft}
        
        LaTeX frame for this slide:
        {frame_info}
        
        Context (adjacent slides' scripts for smooth transitions):
        Previous slide script: {prev_script[:200] + "..." if len(prev_script) > 200 else prev_script}
        Current placeholder: {current_script}
        Next slide script: {next_script[:200] + "..." if len(next_script) > 200 else next_script}

        User Feedback:
        [For script]{json.dumps(self.user_feedback['script'], indent=2)}
        [For overall]{json.dumps(self.user_feedback['overall'], indent=2)}
        
        Please generate a comprehensive speaking script for this slide that:
        1. Introduces the slide topic
        2. Explains all key points clearly and thoroughly
        3. Provides relevant examples or analogies
        4. Connects to previous or upcoming content
        5. Includes rhetorical questions or engagement points for students
        
        The script should be detailed enough for someone else to present effectively from it.
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
        }
    
    def _generate_slide_assessment(self, slide_idx: int, slide: Dict[str, str], slide_draft: str):
        """Generate assessment for a slide using Teaching Assistant agent"""
        teaching_assistant = self.agents.get("teaching_assistant")
        if not teaching_assistant:
            raise ValueError("Teaching Assistant agent not found")
        
        # Get the current assessment template for this slide
        template = self.assessment_template.get(slide_idx, {})
        
        # Create the prompt for the agent
        prompt = f"""
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
    
    def _compile_slides_script(self, latex_source: str | None = None) -> str:
        """Compile notes against the exact order and titles in finalized LaTeX."""
        source = latex_source if latex_source is not None else self._compile_latex_source()
        deck = parse_beamer_source(source)
        content_notes = [
            str(self.slides_script[i].get("script", "")).strip()
            for i in range(len(self.slides_outline))
            if i in self.slides_script
        ]
        return render_speaker_notes_markdown(
            deck,
            content_notes,
            document_title=f"Slides Script: {self.name}",
        )
    
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
