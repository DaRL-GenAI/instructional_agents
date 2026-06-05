import os
import json
import re
from typing import List, Dict, Optional

from src.agents import (
    LLM,
    Agent,
    Deliberation,
)

from src.slides import SlidesDeliberation
from src.compile import LaTeXCompiler

class SyllabusProcessor(Agent):
    """
    Agent responsible for processing syllabus and dividing it into formal chapters
    """
    def __init__(self, name="Syllabus Processor", llm=None):
        super().__init__(
            name=name,
            role="Syllabus organizer and formatter",
            llm=llm,
            system_prompt="You are a Syllabus Processor responsible for analyzing a course syllabus and extracting its weekly topics and schedule. Your task is to create a structured list of chapters, each with a title and brief introduction. The format should be clear and consistent, making it easy to understand the course structure."
        )
    
    def process_syllabus(self, syllabus_content: str) -> List[Dict[str, str]]:
        """
        Process the syllabus content and return a list of chapters
        
        Args:
            syllabus_content: The raw syllabus content
            
        Returns:
            A list of dictionaries, each containing 'title' and 'description' for a chapter
        """
        # Create a prompt to send to the LLM
        prompt = f"""
        Please analyze the following syllabus content and extract its weekly topics and schedule.

        Format your response as a JSON array of objects, each with 'title' and 'description' fields.

        Rules for the 'title' field:
        - Use the EXACT title from each weekly schedule entry in the syllabus.
        - Preserve the syllabus's own numbering and label style (e.g. "Week 1: ...",
          "Module 1: ...", "Unit 1: ...", or whatever heading the syllabus actually uses).
        - DO NOT renumber entries based on textbook chapter references that appear in
          the readings (e.g. "Readings: Chapter 1.1 - 1.2"). Textbook chapter numbers
          must NOT become the course chapter numbers.
        - Output exactly one entry per weekly schedule item in the syllabus, in the
          same order they appear.

        Syllabus Content:
        {syllabus_content}

        Example format (when the syllabus uses week-based headings):
        [
            {{
                "title": "Week 1: Introduction to Machine Learning",
                "description": "Overview of basic machine learning concepts and applications."
            }},
            ...
        ]

        Important: Your entire response must be valid JSON. Do not include any explanatory text before or after the JSON array.
        """
        
        # Reset message history to ensure a clean context
        self.reset_history()
        
        # Get the response from the LLM
        response, elapsed_time, token_usage = self.generate_response(
            prompt=prompt,
            stream=True,
            save_to_history=False  # No need to save this interaction in history
        )
        
        # Parse the JSON response
        try:
            # First try to parse the entire response as JSON
            try:
                chapters = json.loads(response)
                return chapters
            except json.JSONDecodeError:
                # If that fails, try to extract JSON from the response
                json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    chapters = json.loads(json_str)
                    return chapters
                else:
                    # If no JSON array pattern is found, try to extract individual chapter objects
                    chapter_matches = re.findall(r'\{\s*"title"\s*:\s*"[^"]*"\s*,\s*"description"\s*:\s*"[^"]*"\s*\}', response)
                    if chapter_matches:
                        # Combine individual objects into an array
                        combined_json = "[" + ",".join(chapter_matches) + "]"
                        chapters = json.loads(combined_json)
                        return chapters
                    else:
                        raise ValueError("No valid JSON found in response")
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error: Could not parse JSON response from LLM: {e}")
            print("Response:", response)
            raise ValueError("Failed to process syllabus into chapters")
        
            
class ADDIERunner:
    """
    Runner class for the ADDIE workflow
    Handles command-line interaction and execution logic
    """
    def __init__(self, addie_instance, output_dir="output", resume: bool = False):
        """
        Initialize the runner with an ADDIE instance

        Args:
            addie_instance: An instance of the ADDIE class
            output_dir: Directory to read/write deliberation outputs.
            resume: If True, skip deliberations whose outputs are already
                present on disk and pick up chapter work mid-stream.
        """
        self.addie = addie_instance
        self.course_name = None
        self.output_dir = output_dir
        self.resume = resume
        self.results = []
        self.chapters = []

        # Store these for retry logic with slides
        self.latex_source = None
        self.slides_script = None
    
    def setup(self):
        """Setup the runner by getting user input and creating output directory"""
        # Get user input for course name or topic
        self.course_name = self.addie.course_name
        if not self.course_name:
            raise ValueError("Course name or topic is required to proceed.")
        
        self.results = [self.course_name]
    
    def _textbook_toc_context(self) -> Optional[str]:
        """Return the textbook TOC for foundation-deliberation injection.

        Returns the formatted TOC string when ``--use-textbook`` is in play,
        else ``None`` so the deliberation prompt is byte-identical to the
        vanilla path. Called once at the start of the foundation loop and
        reused for every deliberation + retry — the TOC doesn't change
        during a single run.
        """
        kb = getattr(self.addie, "knowledge_base", None)
        if kb is None:
            return None
        try:
            return kb.toc()
        except Exception as e:  # defensive: malformed textbook shouldn't kill the run
            print(f"[grounding] TOC formatting failed ({e}); falling back to vanilla foundation prompts")
            return None

    def run_foundation_deliberations(self):
        """Run the first 6 foundational deliberations"""
        print(f"\n{'#'*60}\nStarting ADDIE Workflow: Foundation Phase\n{'#'*60}\n")

        # Get the first 6 deliberations
        foundation_deliberations = self.addie.deliberations

        # Build the textbook context block once — used by every foundation
        # deliberation including any copilot retries. ``None`` when no
        # ``--use-textbook``, which keeps the vanilla prompts byte-identical.
        self._foundation_toc = self._textbook_toc_context()
        if self._foundation_toc:
            print(
                f"[grounding] Injecting textbook TOC ({len(self._foundation_toc.split())} words) "
                "into foundation deliberations to anchor course structure to the source"
            )

        # Run each deliberation in sequence
        i = 0
        statistics = []
        while i < len(foundation_deliberations):
            deliberation = foundation_deliberations[i]
            print(f"\n{'#'*50}\nDeliberation {i+1}/{len(foundation_deliberations)}: {deliberation.name}\n{'#'*50}\n")

            # Resume: if a result file for this deliberation already exists,
            # load it into self.results and skip the LLM call.
            if self.resume:
                result_path = os.path.join(
                    self.output_dir,
                    f"result_{deliberation.id}.{deliberation.output_format}",
                )
                if os.path.exists(result_path) and os.path.getsize(result_path) > 0:
                    with open(result_path, "r") as f:
                        loaded = f.read()
                    # _save_result prepends "Name\n===\n\n" — strip it so the
                    # loaded content matches what deliberation.run() returns.
                    header_prefix = (
                        f"{deliberation.name}\n{'='*len(deliberation.name)}\n\n"
                    )
                    if loaded.startswith(header_prefix):
                        loaded = loaded[len(header_prefix):]
                    if i >= len(self.results) - 1:
                        self.results.append(loaded)
                    else:
                        self.results[i + 1] = loaded
                    print(f"[resume] Skipped '{deliberation.name}' — loaded from {result_path}")
                    i += 1
                    continue

            # Get user suggestion if copilot mode is enabled
            user_suggestion = ""
            if self.addie.copilot:
                print("\nWould you like to add any suggestions before starting this deliberation? (press Enter to skip)")
                user_suggestion = input("Your suggestion: ").strip()

            if self.addie.copilot:
                print("\nLoading user suggestions from copilot catalog...")
                user_suggestion = f'''###User Feedback: {user_suggestion}
                Suggestions for learning objectives: {self.addie.copilot_catalog.get("learning_objectives", "")}
                Suggestions for syllabus: {self.addie.copilot_catalog.get("syllabus", "")}
                Suggestions for overall package: {self.addie.copilot_catalog.get("overall", "")}
                \n\n'''
                print(f"User suggestions loaded: {user_suggestion}")
            
            # Run deliberation with current state and user suggestion. When
            # textbook grounding is active, ``self._foundation_toc`` is the
            # TOC string the agents see *before* deciding course structure;
            # ``None`` for vanilla, which makes the prompt byte-identical.
            result, elapsed_time, token_usage = deliberation.run(
                current_context=str(self.results),
                user_suggestion=user_suggestion,
                textbook_context=self._foundation_toc,
            )
            statistics.append({"elapsed_time": elapsed_time, "token_usage": token_usage})

            with open(os.path.join(self.output_dir, "statistics.json"), "w") as f:
                json.dump(statistics, f, indent=2)

            # Save current result
            if i >= len(self.results) - 1:  # -1 because we already have the course name
                self.results.append(result)
            else:
                self.results[i+1] = result  # +1 to skip the course name
            
            # Save the result to file
            self._save_result(deliberation, result)
            
            # Check if user wants to proceed or retry in copilot mode
            if self.addie.copilot:
                retried = self._check_for_retry(deliberation, i+1)  # +1 to skip the course name
                if not retried:
                    # Only increment if we didn't retry (retry already updates the result)
                    i += 1
            else:
                i += 1

        # After foundation deliberations finish but before chapter
        # extraction: when textbook grounding is on, augment the syllabus
        # output file with administrative scaffolding (office hours,
        # grading policy, accessibility statement, etc.). The grounding
        # work done above stays untouched — this is a separate LLM call
        # that READS the existing syllabus and APPENDS admin sections.
        # Targets the rubric metrics that regressed under TOC injection
        # (transparency_of_policies, accessibility, etc.) without
        # competing for prompt budget against grounding directives. No-op
        # on the vanilla path.
        self._maybe_augment_syllabus_with_admin()

        # After running the syllabus design deliberation, process the syllabus
        self._process_syllabus()

    # Generic administrative scaffolding template — appended as a new
    # section to the syllabus output. Catalog-agnostic and textbook-
    # agnostic: every variable is a placeholder the instructor fills in.
    # Keeping this here (vs. inside the prompt body inline) makes it easy
    # to inspect / extend without touching control flow.
    _ADMIN_SCAFFOLDING_INSTRUCTIONS = (
        "You are revising a course syllabus to ensure it includes the standard "
        "administrative components that academic courses must have. The current "
        "syllabus content (course objectives, weekly schedule, etc.) is shown below.\n\n"
        "Your task: APPEND a new section titled '## Course Policies' to the END "
        "of the syllabus markdown. The new section must include subsections for:\n"
        "- Instructor Contact Information (use bracket placeholders: [Instructor Name], "
        "[Email], [Office Location], [Office Hours]).\n"
        "- Communication Channels (response-time expectations, preferred channel).\n"
        "- Grading Policy (the overall weighting scheme + late-work policy + rounding).\n"
        "- Attendance Policy (expectations + how absences are handled).\n"
        "- Accessibility and Accommodations (ADA-style statement directing students "
        "to the institution's disability services office; placeholder for the office name).\n"
        "- Academic Integrity (plagiarism + AI-assistance + collaboration boundaries).\n\n"
        "Constraints:\n"
        "- Keep ALL existing syllabus content unchanged. Only APPEND the new section.\n"
        "- Use generic, institution-agnostic language with placeholders rather than "
        "made-up policy specifics.\n"
        "- Keep the tone consistent with the existing syllabus.\n"
        "- Return the FULL revised syllabus markdown, not just the new section.\n\n"
        "Current syllabus:\n{syllabus_content}\n"
    )

    def _maybe_augment_syllabus_with_admin(self) -> None:
        """Append administrative scaffolding to the syllabus output FILE.

        Runs only when textbook grounding is active. The rationale: under
        TOC injection, the syllabus deliberation's prompt budget is mostly
        consumed by textbook chapter alignment and the grounding directive
        — there isn't room for the LLM to also produce standard admin
        scaffolding (office hours, grading policy, accessibility statement,
        academic integrity). The rubric's `syllabus:transparency_of_policies`
        and `syllabus:accessibility` metrics regress as a result.

        Rather than modify the syllabus deliberation prompt (which would
        compete with the grounding directive for prompt budget and
        empirically hurt grounding substance), we run a SEPARATE
        post-foundation LLM call that reads the produced syllabus file
        and APPENDS a "Course Policies" section. The grounding-relevant content is
        already generated; this call only adds administrative metadata.

        Idempotent across `--resume`: a sibling sentinel file
        ``result_syllabus_design.md.pre_admin_scaffolding.bak`` is written
        on first augmentation and used to detect that the augmentation has
        already happened, so resumed runs don't double-append.

        Vanilla path: no-op (early-returns when
        ``self.addie.knowledge_base is None``).
        """
        if self.addie.knowledge_base is None:
            return
        syllabus_path = os.path.join(self.output_dir, "result_syllabus_design.md")
        if not os.path.exists(syllabus_path):
            # No syllabus to augment (foundation phase probably didn't run
            # to completion). Skip silently.
            return
        sentinel = syllabus_path + ".pre_admin_scaffolding.bak"
        if os.path.exists(sentinel):
            # Already augmented in a previous run; don't double-append.
            print(
                "[grounding] Syllabus admin scaffolding already applied "
                f"(sentinel {os.path.basename(sentinel)} exists); skipping."
            )
            return

        with open(syllabus_path, "r") as f:
            current = f.read()
        if not current.strip():
            return

        print("\n[grounding] Appending administrative scaffolding to syllabus...")
        prompt = self._ADMIN_SCAFFOLDING_INSTRUCTIONS.format(syllabus_content=current)
        response = self.addie.llm.generate_response(prompt)
        # `LLM.generate_response` returns (text, elapsed, tokens); be
        # defensive in case the error path returned a bare string in a
        # historical build.
        if isinstance(response, tuple) and response:
            augmented = response[0]
        else:
            augmented = str(response or "")
        # If the LLM call failed or returned empty, leave the original
        # syllabus alone — never write a worse syllabus over a working one.
        if not augmented.strip() or augmented.startswith("Error"):
            print("[grounding] Augmentation produced no usable output; "
                  "leaving original syllabus unchanged.")
            return

        # Preserve the original under a sentinel name (lets us detect that
        # augmentation has been applied, and gives us a clean rollback path
        # if anything looks off in the augmented version).
        with open(sentinel, "w") as f:
            f.write(current)
        with open(syllabus_path, "w") as f:
            f.write(augmented)
        print(
            f"[grounding] Syllabus augmented. Original preserved at "
            f"{os.path.basename(sentinel)}."
        )

    def _process_syllabus(self):
        """Process the syllabus to extract chapters"""
        # Resume: if chapters were already processed in a previous run,
        # just reload them from disk instead of calling the LLM again.
        chapters_path = os.path.join(self.output_dir, "processed_chapters.json")
        if self.resume and os.path.exists(chapters_path):
            self._load_chapters()
            if self.chapters:
                print(f"[resume] Loaded {len(self.chapters)} chapters from {chapters_path}")
                # Contract still needs to be built — it lives in memory on
                # the ADDIE instance, not on disk — so a --resume grounded
                # run needs the contract rebuilt against the loaded chapters.
                self._maybe_build_contract()
                return

        # Get the syllabus design result
        # The syllabus should be the result of the syllabus_design deliberation (4th deliberation, index 3+1)
        syllabus_index = 4  # Index in results array (including course name)

        if len(self.results) > syllabus_index:
            syllabus_content = self.results[syllabus_index]

            # Create and use the SyllabusProcessor agent
            processor = SyllabusProcessor(llm=self.addie.llm)
            self.chapters = processor.process_syllabus(syllabus_content)

            # Save the processed chapters
            self._save_chapters()

            print(f"\nSyllabus processed into {len(self.chapters)} chapters:")
            for i, chapter in enumerate(self.chapters):
                print(f"{i+1}. {chapter['title']}")

            # If textbook grounding is active, build the course contract
            # binding each chapter to a handful of textbook sections. Retrieval
            # in the slide / script / assessment prompts will be constrained
            # to those sections.
            self._maybe_build_contract()
        else:
            print("Error: Syllabus not found in results. Cannot process chapters.")

    def _maybe_build_contract(self):
        """Build the course contract iff textbook grounding is active.

        No-op when ``--use-textbook`` wasn't passed (retriever / KB are
        ``None``). Called from both the fresh syllabus-processing path
        and the ``--resume`` chapter-loading path so a resumed grounded
        run gets the same contract-bound retrieval as a fresh one.
        """
        if self.addie.retriever is None or self.addie.knowledge_base is None:
            return
        from src.grounding import build_course_contract
        print(
            "\n[grounding] Building course contract from chapters "
            "(with HyDE + subtopic multi-query)..."
        )
        # Use a stronger LLM (gpt-4o) just for query expansion (HyDE
        # passages, subtopic decomposition). The contract is built
        # once per run; 15 chapters × ~2 calls each = ~30 LLM calls
        # is ~$0.05-0.10 extra — cheap given the coverage lift better
        # queries produce.
        query_llm = self.addie.llm
        try:
            from src.agents import LLM
            query_llm = LLM(model_name="gpt-4o")
        except Exception as e:
            print(
                f"[grounding] Could not build gpt-4o query helper "
                f"({type(e).__name__}: {e}); falling back to default LLM."
            )
            query_llm = self.addie.llm
        self.addie.contract = build_course_contract(
            course_id=self.addie.course_name or "course",
            chapters=self.chapters,
            kb=self.addie.knowledge_base,
            retriever=self.addie.retriever,
            # Enable the retrieval-quality boosts when an LLM is on hand.
            # They degrade gracefully on per-call errors (logged + skipped).
            llm=query_llm,
        )
        for i, m in enumerate(self.addie.contract.topic_to_textbook):
            print(
                f"  ch{i+1} {m.topic[:50]!r:55s} -> "
                f"sections {m.section_ids}"
            )
    
    def _save_chapters(self):
        """Save the processed chapters to a file"""
        chapters_path = os.path.join(self.output_dir, "processed_chapters.json")
        with open(chapters_path, "w") as f:
            json.dump(self.chapters, f, indent=2)
        print(f"\nProcessed chapters saved to: '{chapters_path}'")
    
    def _load_chapters(self):
        """Load processed chapters from file"""
        chapters_path = os.path.join(self.output_dir, "processed_chapters.json")
        
        try:
            with open(chapters_path, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.chapters = [
                    ch for ch in data if isinstance(ch, dict) and 'title' in ch and 'description' in ch
                ]
                print(f"Loaded {len(self.chapters)} valid chapters from: '{chapters_path}'")
            else:
                print(f"Invalid format: Expected a list, got {type(data).__name__}")
                self.chapters = []
        except Exception as e:
            print(f"Failed to load chapters: {e}")
            self.chapters = []
        
    def run_chapter_deliberations(self):
        """Run the remaining deliberations for each chapter"""
        if not self.chapters:
            print("No chapters found. Please ensure syllabus processing was successful.")
            return
        
        print(f"\n{'#'*60}\nStarting ADDIE Workflow: Chapter Development Phase\n{'#'*60}\n")
        
        # For each chapter, run the SlidesDeliberation
        for chapter_idx, chapter in enumerate(self.chapters):
            print(f"\n{'#'*50}\nChapter {chapter_idx+1}/{len(self.chapters)}: {chapter['title']}\n{'#'*50}\n")

            # Create chapter directory
            chapter_dir = os.path.join(self.output_dir, f"chapter_{chapter_idx+1}")
            os.makedirs(chapter_dir, exist_ok=True)

            # Resume: skip this chapter entirely if all three final outputs
            # already exist and are non-empty. Partial chapters (e.g. empty
            # dir, or missing one of the three) fall through — the inner
            # SlidesDeliberation will pick up from its own checkpoint.
            if self.resume:
                required = ["slides.tex", "script.md", "assessment.md"]
                if all(
                    os.path.exists(os.path.join(chapter_dir, f))
                    and os.path.getsize(os.path.join(chapter_dir, f)) > 0
                    for f in required
                ):
                    print(f"[resume] Skipped chapter_{chapter_idx+1} — all outputs present")
                    continue

            # Run SlidesDeliberation for this chapter with retry support
            self._run_slides_generation_with_retry(chapter, chapter_idx, chapter_dir)

        # All chapters finished successfully — sweep any leftover checkpoint
        # files (belt-and-suspenders; SlidesDeliberation already removes its
        # own on successful completion).
        self._cleanup_checkpoints()

        # After all chapters, compile the LaTeX source and slides script
        compiler = LaTeXCompiler(self.output_dir)
        compiler.compile_all()

    def _cleanup_checkpoints(self):
        """Remove any leftover _checkpoint.json files under output_dir.

        Called at the end of a fully-successful chapter phase so that a
        re-run without --resume starts clean, and so that the on-disk
        artifact tree doesn't carry around stale resume state.
        """
        removed = 0
        for root, _dirs, files in os.walk(self.output_dir):
            for name in files:
                if name == "_checkpoint.json":
                    try:
                        os.remove(os.path.join(root, name))
                        removed += 1
                    except OSError as exc:
                        print(f"Warning: could not remove {os.path.join(root, name)}: {exc}")
        if removed:
            print(f"[cleanup] Removed {removed} leftover checkpoint file(s)")
        
    def _run_slides_generation_with_retry(self, chapter, chapter_idx, chapter_dir):
        """Run slides generation with retry support"""
        print(f"\n{'#'*40}\nSlides Generation for Chapter {chapter_idx+1}: {len(self.chapters)}: {chapter['title']}\n{'#'*40}\n")

        # Get user suggestion if copilot mode is enabled
        user_suggestion = ""
        if self.addie.copilot:
            print("\nWould you like to add any suggestions before starting slides creation? (press Enter to skip)")
            user_suggestion = input("Your suggestion: ").strip()
        
        # Create context for slides deliberation
        slides_context = {
            "foundation_results": self.results,
            "course_name": self.course_name,
            "slides": "",
            "script": "",
            "assessment": "",
            "overall": "",
        }
        if self.addie.copilot:
            print("\nLoading user suggestions from copilot catalog...")
            slides_context["slides"] += self.addie.copilot_catalog.get("slides", "")
            slides_context['script'] += self.addie.copilot_catalog.get("script", "")
            slides_context['assessment'] += self.addie.copilot_catalog.get("assessment", "")
            slides_context['overall'] += self.addie.copilot_catalog.get("overall", "")
            print(f"User suggestions loaded: {slides_context['slides']}, {slides_context['script']}, {slides_context['assessment']}, {slides_context['overall']}")

        # Create a SlidesDeliberation instance for this chapter.
        # When textbook grounding is active, hand the deliberation a
        # reference to the retriever and the section IDs the contract has
        # bound to this chapter — used to scope evidence retrieval.
        slides_deliberation = self._create_slides_deliberation(
            chapter, f"chapter_{chapter_idx+1}", chapter_idx=chapter_idx,
        )
        
        # Store original context for retries
        original_context = slides_context.copy()
        previous_suggestions = []
        if user_suggestion:
            previous_suggestions.append(user_suggestion)
        
        # Run the SlidesDeliberation
        slides_deliberation.run(chapter, slides_context)

        # Retry logic for slides generation
        if self.addie.copilot:
            retry_loop = True
            while retry_loop:
                print("\nHow would you like to proceed with slides generation?")
                print("1. Continue to assessment development")
                print("2. Re-run slides generation with additional suggestions")
                
                choice = input("Your choice (1 or 2): ").strip()
                if choice != "2":
                    retry_loop = False
                    continue
                
                # Get new suggestion
                print("\nPlease provide your suggestions for improving the slides:")
                new_suggestion = input("Your suggestion: ").strip()
                if not new_suggestion:
                    print("No suggestion provided. Please enter a suggestion or choose option 1 to continue.")
                    continue
                
                # Add to previous suggestions
                previous_suggestions.append(new_suggestion)
                
                # Combine all suggestions for this run
                combined_suggestions = "\n\nUser Suggestions:\n" + "\n".join([f"- {s}" for s in previous_suggestions])
                
                # Update context with combined suggestions
                retry_context = original_context.copy()
                retry_context["user_suggestion"] = combined_suggestions
                
                print("\nRe-running slides generation with your suggestions...\n")
                
                # Re-run the SlidesDeliberation
                slides_deliberation.run(chapter, retry_context)

                # Ask if the user is satisfied
                print("\nAre you satisfied with the slides?")
                print("1. Yes, continue to assessment development")
                print("2. No, I want to provide additional suggestions")
                
                satisfaction = input("Your choice (1 or 2): ").strip()
                if satisfaction == "1":
                    retry_loop = False
    
    def _create_slides_deliberation(self, chapter, chapter_dir_name, chapter_idx: int = 0):
        """
        Create a SlidesDeliberation instance for a chapter
        
        Args:
            chapter: Chapter information
            chapter_dir_name: Name of the chapter directory
            
        Returns:
            SlidesDeliberation instance
        """
        # Create agents for the slides deliberation
        agents = {
            "teaching_faculty": Agent(
                name="Teaching Faculty",
                role="Professor creating lecture content",
                llm=self.addie.llm,
                system_prompt="You are a Teaching Faculty responsible for creating detailed educational content for slides. Your goal is to explain concepts clearly, provide examples, and make complex topics accessible to students."
            ),
            "instructional_designer": Agent(
                name="Instructional Designer",
                role="Expert designing slide structure",
                llm=self.addie.llm,
                system_prompt="You are an Instructional Designer responsible for organizing course content into a logical slide structure. Your goal is to create an outline that covers all key topics with appropriate depth and flow."
            ),
            "teaching_assistant": Agent(
                name="Teaching Assistant",
                role="TA creating LaTeX slides and scripts",
                llm=self.addie.llm,
                system_prompt="You are a Teaching Assistant responsible for creating LaTeX slides and detailed speaker notes. Your goal is to create well-formatted slides and comprehensive speaking notes that explain all key points clearly."
            )
        }
        
        # Per-chapter grounding scope: look up the section IDs the contract
        # bound to this chapter, if any. ``None`` means "no contract — let
        # the retriever search the whole textbook".
        from src.grounding import sections_for_chapter
        section_ids = sections_for_chapter(self.addie.contract, chapter_idx)

        # Create and return the slides deliberation
        return SlidesDeliberation(
            id=f"slides_{chapter_dir_name}",
            name=f"Slides Generation - {chapter['title']}",
            agents=agents,
            llm=self.addie.llm,
            output_dir=os.path.join(self.output_dir, chapter_dir_name),
            catalog=self.addie.catalog,
            catalog_dict=self.addie.catalog_dict,
            resume=self.resume,
            retriever=self.addie.retriever,
            section_ids=section_ids,
            textbook_id=(
                self.addie.knowledge_base.textbook_id
                if self.addie.knowledge_base else None
            ),
        )
    
    def _save_result(self, deliberation, result):
        """Save deliberation result to file"""
        file_path = os.path.join(self.output_dir, f"result_{deliberation.id}.{deliberation.output_format}")
        with open(file_path, "w") as f:
            f.write(f"{deliberation.name}\n{'='*len(deliberation.name)}\n\n{result}")
        print(f"\nResult saved to: '{file_path}' ({deliberation.name} result)")
    
    def _save_chapter_result(self, deliberation, result, chapter_idx, chapter_dir):
        """Save chapter-specific deliberation result to file"""
        # Save result to chapter directory
        file_path = os.path.join(chapter_dir, f"result_{deliberation.id}.{deliberation.output_format}")
        with open(file_path, "w") as f:
            f.write(f"{deliberation.name}\n{'='*len(deliberation.name)}\n\n{result}")
        print(f"\nResult saved to: '{file_path}' ({deliberation.name} result)")
    
    def _check_for_retry(self, deliberation, idx, chapter_context=False, chapter_idx=None):
        """
        Check if user wants to retry a deliberation, allowing unlimited retries
        
        Args:
            deliberation: The deliberation to potentially retry
            idx: Index in results array for foundation deliberations
            chapter_context: Whether this is a chapter-specific deliberation
            chapter_idx: Index of chapter if chapter_context is True
        
        Returns:
            True if the deliberation was retried and user is satisfied, False otherwise
        """
        # Store the original context to use for all retries
        if chapter_context:
            chapter = self.chapters[chapter_idx]
            original_context = {
                "foundation_results": self.results,
                "current_chapter": chapter
            }
            if hasattr(self, 'latex_source') and hasattr(self, 'slides_script'):
                original_context.update({
                    "slides_content": self.latex_source,
                    "slides_script": self.slides_script
                })
            context_str = str(original_context)
        else:
            # Foundation deliberation context
            context_str = str(self.results)
        
        # Keep track of previous user suggestions to include in each retry
        previous_suggestions = []
        
        while True:
            print("\nHow would you like to proceed?")
            print("1. Continue to the next deliberation")
            print("2. Re-run this deliberation with additional suggestions")
            
            choice = input("Your choice (1 or 2): ").strip()
            if choice != "2":
                return False
            
            # Get new suggestion
            print("\nPlease provide your suggestions for re-running this deliberation:")
            new_suggestion = input("Your suggestion: ").strip()
            if not new_suggestion:
                print("No suggestion provided. Please enter a suggestion or choose option 1 to continue.")
                continue
            
            # Add to previous suggestions
            previous_suggestions.append(new_suggestion)
            
            # Combine all suggestions for this run
            combined_suggestions = "\n\nUser Suggestions:\n" + "\n".join([f"- {s}" for s in previous_suggestions])
            
            print("\nRe-running deliberation with your suggestions...\n")
            
            # Pull the TOC injected at run_foundation_deliberations time so
            # retries see the same source-anchored prompt the first call did.
            # ``None`` when no textbook (vanilla path); ``None`` for chapter
            # retries too (SlidesDeliberation has its own grounding path that
            # works at the per-chapter level rather than the foundation TOC).
            foundation_toc = getattr(self, "_foundation_toc", None)
            if chapter_context:
                # Re-run chapter deliberation with combined suggestions but original context
                result = deliberation.run(current_context=context_str, user_suggestion=combined_suggestions)

                # Save to chapter directory
                chapter_dir = os.path.join(self.output_dir, f"chapter_{chapter_idx+1}")
                self._save_chapter_result(deliberation, result, chapter_idx, chapter_dir)
            else:
                # Re-run foundation deliberation with combined suggestions but original context
                result = deliberation.run(
                    current_context=context_str,
                    user_suggestion=combined_suggestions,
                    textbook_context=foundation_toc,
                )
                self.results[idx] = result
                self._save_result(deliberation, result)
            
            # Ask if the user is satisfied or wants to retry again
            print("\nAre you satisfied with the results?")
            print("1. Yes, continue to the next deliberation")
            print("2. No, I want to provide additional suggestions")
            
            satisfaction = input("Your choice (1 or 2): ").strip()
            if satisfaction == "1":
                return True  # We did retry at least once and user is satisfied
    
    def run(self):
        """Run the complete workflow"""
        try:
            print(f"\n{'#'*60}\nStarting ADDIE Workflow: Instructional Design\n{'#'*60}\n")
            print(f"Description: Complete workflow for developing a course design from goals to assessment\n")
            print(f"Mode: {'copilot' if self.addie.copilot else 'Automatic'}\n")
            
            # Setup the runner
            self.setup()
            
            # Run foundation deliberations
            self.run_foundation_deliberations()
            # self._load_chapters()

            # Run chapter-specific deliberations
            self.run_chapter_deliberations()
            
            print(f"\n{'#'*60}\nADDIE Workflow Complete\n{'#'*60}\n")
            print("\nAll results have been saved to:")
            print(f"- Foundation results: {self.output_dir}")
            print(f"- Chapter results: {self.output_dir}/chapter_*")
            
            return self.results
        
        except Exception as e:
            print(f"Error running ADDIE workflow: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
        

class ADDIE:
    """
    ADDIE (Analyze, Design, Develop, Implement, Evaluate) class for instructional design
    This class coordinates a series of deliberations to create a complete course design
    """
    def __init__(self, course_name, model_name: str = "gpt-4o-mini", copilot: bool = False, catalog: bool = False, data_catalog: dict = {}, data_copilot: dict = {}, seed: int = None, temperature: float = None, resume: bool = False, textbook_path: str = None, vlm_extraction: bool = False):
        """
        Initialize ADDIE workflow

        Args:
            model_name: Name of the LLM model to use
            copilot: Whether to enable copilot mode with user feedback
            seed: Random seed for reproducibility (passed to OpenAI API)
            temperature: Sampling temperature (passed to OpenAI API)
            resume: If True, skip deliberations whose outputs already exist in
                output_dir and resume chapter generation from the last
                incomplete chapter (or a mid-chapter checkpoint).
            textbook_path: Optional path to a textbook (PDF, markdown, or a
                directory of either) used to ground course generation. When
                ``None`` (the default) generation runs exactly as in the
                vanilla pipeline.
            vlm_extraction: When True AND a textbook_path is set, ingest
                via the hybrid path that augments complex pages (figures,
                equations, tables) with structured content extracted via
                GPT-4o-mini vision. Saves cropped page PNGs to disk so
                the downstream slide generator can include them as
                figures. No effect when textbook_path is None.
        """
        self.course_name = course_name
        self.model_name = model_name
        self.copilot = copilot
        self.catalog = catalog
        self.resume = resume
        self.llm = LLM(model_name=model_name, seed=seed, temperature=temperature)
        self.deliberations = []
        self.results = []

        # Textbook grounding (opt-in). When the path is absent, the knowledge
        # base, retriever, and contract stay ``None`` and downstream code
        # paths take the vanilla branch — vanilla behavior is byte-identical
        # to a run without the flag.
        self.knowledge_base = None
        self.retriever = None
        self.contract = None  # populated by ADDIERunner once chapters exist
        if textbook_path:
            from src.grounding import HybridRetriever, TextbookKnowledgeBase
            print(f"[grounding] Loading textbook from: {textbook_path}")
            # Optional VLM extractor for the hybrid ingester. Defensive:
            # if the OpenAI import fails or the API key isn't set we
            # fall back to the standard ingester rather than refusing
            # the run.
            vlm_extractor = None
            if vlm_extraction:
                try:
                    from src.textbook.vlm_adapter import VlmExtractor
                    figures_root = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        ".grounding_cache", "figures",
                    )
                    # Use gpt-4o (not -mini) for VLM extraction:
                    # extraction quality cascades through every
                    # downstream metric and the cost is one-time per
                    # textbook (cached). ~$0.06 per textbook vs
                    # ~$0.006 with mini — well within budget.
                    vlm_extractor = VlmExtractor(
                        figures_dir=figures_root, model="gpt-4o",
                    )
                    print("[grounding] VLM extraction enabled "
                          "(complex pages routed to GPT-4o vision).")
                except Exception as e:
                    print(
                        f"[grounding] VLM extractor unavailable "
                        f"({type(e).__name__}: {e}); falling back to "
                        f"text-only PDF extraction.",
                        flush=True,
                    )
                    vlm_extractor = None
            self.knowledge_base = TextbookKnowledgeBase.from_path(
                textbook_path, vlm_extractor=vlm_extractor,
            )
            print(
                f"[grounding] Loaded '{self.knowledge_base.textbook.title}': "
                f"{len(self.knowledge_base.textbook.chapters)} chapters, "
                f"{len(self.knowledge_base)} chunks."
            )
            # Retriever is constructed eagerly (cheap — BM25 is in-memory)
            # but the dense-embedding API call is deferred to first search.
            # Cache embeddings on disk so repeat runs skip the API call.
            cache_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".grounding_cache",
            )
            # Second-stage cross-encoder reranker. Operates on the top-K
            # candidates from BM25 + dense fusion and rescores them via a
            # pretrained BERT-style relevance model (ms-marco-MiniLM-L-6-v2
            # by default, ~90 MB, loaded lazily on first .score() call).
            #
            # Targets the `retrieval_bad` failure mode the verifier
            # identifies — citations that land on the wrong textbook
            # chunk. The cross-encoder reads (query, passage) as a pair
            # and produces a semantic-relevance score that RRF's
            # order-agnostic fusion can't, so it tends to recover the
            # cases where dense and sparse retrieval agreed on a chunk
            # that wasn't actually about the query.
            #
            # An earlier LLM-based reranker (LLMReranker) was tried and
            # measured no improvement (89.3 % vs 90.2 % precision); the
            # cross-encoder is a different signal entirely (offline BERT
            # vs LLM-as-judge). Defensive code in HybridRetriever.search
            # keeps the first-stage order on any reranker failure, so
            # the caller is never worse off than the no-reranker
            # baseline. Generic across textbooks — no per-source tuning.
            # Defensive construction: the cross-encoder pulls in
            # sentence-transformers / torch which can fail on bleeding-edge
            # versions (SIGBUS / NaN scores observed historically). If
            # construction throws OR if the optional dep is missing, log a
            # warning and continue with first-stage retrieval only — the
            # rest of the grounding pipeline works fine without rerank.
            try:
                from src.grounding.reranker import CrossEncoderReranker
                reranker = CrossEncoderReranker()
            except Exception as e:
                print(
                    f"[grounding] Cross-encoder reranker unavailable "
                    f"({type(e).__name__}: {e}). Falling back to first-stage "
                    f"retrieval (BM25 + dense + RRF) without rerank.",
                    flush=True,
                )
                reranker = None
            self.retriever = HybridRetriever(
                self.knowledge_base, cache_dir=cache_dir, reranker=reranker,
            )

        # Create all deliberations in the workflow
        self.set_catalog(data_catalog)
        self.set_copilot(data_copilot)
        self.create_deliberations()
        
    def set_catalog(self, data_catalog: dict):
        self.catalog_dict = {
            "objectives_definition": "",
            "resource_assessment": "",
            "learner_analysis": "",
            "syllabus_design": "",
            "assessment_planning": "",
            "slides_length": 30,
        }
        
        if self.catalog:
            # Debugging line: Check available keys in data_catalog before accessing them.
            # Added to troubleshoot potential KeyError when loading course_structure from JSON.
            print("Debug: data_catalog keys =", data_catalog.keys())
            self.catalog_dict = {
                "objectives_definition": [data_catalog['course_structure'], data_catalog['institutional_requirements']],
                "resource_assessment": [data_catalog['teaching_constraints'], data_catalog['institutional_requirements']],
                "learner_analysis": [data_catalog['student_profile'], data_catalog['prior_feedback']],
                "syllabus_design": [data_catalog['course_structure'], data_catalog['institutional_requirements'],  data_catalog['instructor_preferences']],
                "assessment_planning": [data_catalog['assessment_design'], data_catalog['instructor_preferences']],
                "slides_length": int(data_catalog['teaching_constraints']['max_slide_count'])
            }
    
    def set_copilot(self, data_copilot: dict):
        self.copilot_catalog = {
            "learning_objectives": "",
            "syllabus": "",
            "slides": "",
            "script": "",
            "assessment": "",
            "overall": "",
        }

        if self.copilot:
            self.copilot_catalog = {
                "learning_objectives": data_copilot["learning_objectives"] if "learning_objectives" in data_copilot else "",
                "syllabus": data_copilot["syllabus"] if "syllabus" in data_copilot else "",
                "slides": data_copilot["slides"] if "slides" in data_copilot else "",
                "script": data_copilot["script"] if "script" in data_copilot else "",
                "assessment": data_copilot["assessment"] if "assessment" in data_copilot else "",
                "overall": data_copilot["overall"] if "overall" in data_copilot else "",
            }
        print(f"Catalog initialized with: {self.catalog_dict}")


    def create_deliberations(self):
        """Create all deliberations in the ADDIE workflow"""
        # Clear any existing deliberations
        self.deliberations = []
        
        # Add foundation deliberations (the first 4)
        self.deliberations.append(self.create_objectives_definition_deliberation()) # Objectives Definition
        self.deliberations.append(self.create_resource_assessment_deliberation()) # Resource Assessment
        self.deliberations.append(self.create_learner_analysis_deliberation()) # Learner Analysis
        self.deliberations.append(self.create_syllabus_design_deliberation()) # Syllabus Design
        self.deliberations.append(self.create_assessment_planning_deliberation()) # Assessment Planning
        self.deliberations.append(self.create_final_exam_deliberation()) # Final Exam Design
        
    
    def create_objectives_definition_deliberation(self) -> Deliberation:
        """Create deliberation for defining instructional goals"""
        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor defining instructional goals",
            llm=self.llm,
            system_prompt="You are a Teaching Faculty responsible for defining clear learning objectives based on accreditation standards, competency gaps, and institutional needs. Your goal is to draft a set of course objectives aligned with industry expectations and discuss with the department committee to refine them for curriculum integration."
        )
        
        instructional_designer = Agent(
            name="Instructional Designer",
            role="Expert in curriculum design and alignment",
            llm=self.llm,
            system_prompt="You are an Instructional Designer responsible for reviewing proposed learning objectives, assessing alignment with accreditation requirements, and suggesting modifications for consistency within the broader curriculum."
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt="You are a Summarizer for instructional goals discussions. Please generate a set of well-defined learning objectives that align with accreditation standards, address curriculum gaps, and meet industry needs.",
            output_constraint="Only generate the learning objectives, no other text."
        )
        
        # Create and return the deliberation
        return Deliberation(
            id="instructional_goals",
            name="Instructional Goals Definition",
            agents=[teaching_faculty, instructional_designer],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt=f"Start by defining clear instructional goals.",
            input_files=self.catalog_dict.get("objectives_definition", []),
            output_format="md",
        )
    
    def create_resource_assessment_deliberation(self) -> Deliberation:
        """Create deliberation for assessing resources and constraints"""
        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor assessing resource requirements",
            llm=self.llm,
            system_prompt="You are a Teaching Faculty responsible for determining the feasibility of courses based on faculty expertise, facility resources, and scheduling constraints. Your goal is to provide input on teaching requirements and ensure necessary instructional resources are available for effective course delivery."
        )
        
        instructional_designer = Agent(
            name="Instructional Designer",
            role="Technology and resource assessment specialist",
            llm=self.llm,
            system_prompt="You are an Instructional Designer responsible for assessing whether current instructional technologies and platforms support proposed courses, identifying potential limitations, and collaborating to propose viable solutions."
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt="You are a Summarizer for Resource & Constraints Assessment. Please generate A detailed assessment of available resources, constraints, and technological requirements for effective course delivery.",
            output_constraint="Only generate the document, no other text."
        )

        # Create and return the deliberation
        return Deliberation(
            id="resource_assessment",
            name="Resource & Constraints Assessment",
            agents=[teaching_faculty, instructional_designer],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt="Evaluate the resources needed and constraints to consider for delivering the course. Consider faculty expertise requirements, necessary computing resources, software requirements, and any scheduling or facility limitations.",
            input_files=self.catalog_dict.get("resource_assessment", []),
            output_format="md",
        )

    def create_learner_analysis_deliberation(self) -> Deliberation:
        """Create deliberation for analyzing target audience and needs"""
        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor analyzing student needs",
            llm=self.llm,
            system_prompt="You are a Teaching Faculty responsible for identifying student learning needs based on prior knowledge, enrollment trends, and academic performance data. Your goal is to analyze gaps in student learning, assess common challenges, and discuss findings to ensure course design meets diverse student needs."
        )
        
        course_coordinator = Agent(
            name="Course Coordinator",
            role="Department administrator overseeing courses",
            llm=self.llm,
            system_prompt="You are a Department Admin responsible for providing institutional data on student demographics, enrollment trends, and past student feedback, then collaborating with professors to determine necessary course adjustments."
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt="You are a Summarizer for target audience discussions. Please generate 1) A comprehensive profile of target students including their prior knowledge, learning needs, and appropriate educational approaches, with 2) Data-driven recommendations for course adjustments",
            output_constraint="Only generate the two documents, no other text."
        )
        
        # Create and return the deliberation
        return Deliberation(
            id="target_audience",
            name="Target Audience & Needs Analysis",
            agents=[teaching_faculty, course_coordinator],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt="Based on the learning objectives defined previously, analyze the target audience for the course. Consider students' typical background, prerequisite knowledge, and career aspirations. Identify potential knowledge gaps and learning needs.",
            input_files=self.catalog_dict.get("learner_analysis", []),
            output_format="md",
        )
    
    def create_syllabus_design_deliberation(self) -> Deliberation:
        """Create deliberation for designing course syllabus"""
        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor designing course syllabus",
            llm=self.llm,
            system_prompt="You are a Professor responsible for creating a structured syllabus that defines course content, pacing, and expected learning outcomes. Your goal is to draft a syllabus including weekly topics, learning objectives, required readings, and grading policies."
        )
        
        instructional_designer = Agent(
            name="Instructional Designer",
            role="Department committee member reviewing syllabus",
            llm=self.llm,
            system_prompt="You are a Department Committee Member responsible for reviewing syllabus drafts, assessing alignment with institutional policies and accreditation requirements, and providing recommendations for improvement."
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt="You are a Summarizer for Course Syllabus Design. Please generate A complete syllabus with course structure, objectives, weekly topics, and assessment schedule. Format the syllabus in a clear, structured manner that can be easily parsed into chapters.",
            output_constraint="Only generate the document, no other text."
        )
        
        # Create and return the deliberation
        return Deliberation(
            id="syllabus_design",
            name="Syllabus & Learning Objectives Design",
            agents=[teaching_faculty, instructional_designer],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt="Develop a comprehensive syllabus for the course. Include weekly topics, required readings, learning objectives, and assessment methods. Ensure alignment with previously defined instructional goals and student needs.",
            input_files=self.catalog_dict.get("syllabus_design", []),
            output_format="md",
        )
    
    def create_assessment_planning_deliberation(self) -> Deliberation:
        """Create deliberation for planning course assessments and evaluations"""
        
        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor planning course assessments",
            llm=self.llm,
            system_prompt=(
                "You are a Professor responsible for designing a course's assessment and evaluation strategy. "
                "Your task is to define project-based, milestone-driven, and real-world-relevant assessments, "
                "including formats, timing, grading rubrics, and submission logistics. Avoid traditional exam-heavy approaches."
            )
        )
        
        instructional_designer = Agent(
            name="Instructional Designer",
            role="Department committee member reviewing assessment plans",
            llm=self.llm,
            system_prompt=(
                "You are a Department Committee Member responsible for evaluating assessment plans to ensure "
                "they align with institutional policies, learning outcomes, and best practices in competency-based education. "
                "Provide constructive feedback on assessment design, balance, and fairness."
            )
        )
        
        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt=(
                "You are a Summarizer for Course Assessment Planning. Please generate a structured document that outlines "
                "assessment types, milestone structure, grading criteria, submission formats, and delivery platforms. "
                "Ensure clarity, real-world relevance, and alignment with course objectives."
            ),
            output_constraint="Only generate the final assessment planning document, no extra explanations."
        )
        
        # Create and return the deliberation
        return Deliberation(
            id="assessment_planning",
            name="Assessment & Evaluation Planning",
            agents=[teaching_faculty, instructional_designer],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt=(
                "Design a complete assessment and evaluation plan for the course. "
                "Include project-based evaluations, milestone breakdowns (e.g., proposals, progress reports), "
                "question types (open-ended, MCQs), grading rubrics, and submission formats (.pdf, .ipynb via Canvas LMS). "
                "Replace the final exam with a cumulative or staged final project. Emphasize real-world application and analytical thinking."
            ),
            input_files=self.catalog_dict.get("assessment_planning", []),
            output_format="md",
        )
    
    def create_final_exam_deliberation(self) -> Deliberation:
        """Create deliberation for designing a project-based final assessment"""

        # Create agents for this process
        teaching_faculty = Agent(
            name="Teaching Faculty",
            role="Professor designing the final project",
            llm=self.llm,
            system_prompt=(
                "You are a Professor designing a project-based final assessment that replaces the traditional exam. "
                "The final project should align with course learning objectives and simulate real-world problem-solving. "
                "Consider incorporating multiple milestones (e.g., proposal, progress update, final deliverable), "
                "interdisciplinary elements, and collaborative or individual work formats. "
                "The assessment must promote critical thinking, applied skills, and authentic data usage."
            )
        )

        instructional_designer = Agent(
            name="Instructional Designer",
            role="Department committee member reviewing final project design",
            llm=self.llm,
            system_prompt=(
                "You are a Department Committee Member responsible for reviewing and refining the design of a final project "
                "that serves as the course’s summative assessment. Ensure alignment with course objectives, student workload balance, "
                "inclusive learning principles, and institutional policy. Offer suggestions on clarity, scaffolding, fairness, "
                "and the use of feedback loops like peer or instructor checkpoints."
            )
        )

        summarizer = Agent(
            name="Summarizer",
            role="Executive summary creator",
            llm=self.llm,
            system_prompt=(
                "You are a Summarizer for Final Project Planning. Please generate a structured final project plan "
                "that includes a description, objectives, timeline with milestones, deliverables, grading rubric, "
                "submission formats, and academic integrity guidelines. The project should reflect real-world relevance and encourage analytical thinking."
            ),
            output_constraint="Only generate the final project plan document. Do not include extra explanations or commentary."
        )

        # Create and return the deliberation
        return Deliberation(
            id="final_exam_project",
            name="Final Project Assessment Design",
            agents=[teaching_faculty, instructional_designer],
            max_rounds=1,
            summary_agent=summarizer,
            instruction_prompt=(
                "Collaboratively design a final project to replace the traditional final exam. "
                "The project should reflect course objectives, be broken into multiple milestones "
                "(e.g., proposal, draft, final submission), and emphasize real-world data or scenarios. "
                "Include details such as team vs. individual work, submission format (.pdf, .ipynb, etc.), Canvas LMS compatibility, "
                "assessment rubrics, peer/instructor feedback checkpoints, and academic integrity considerations. "
                "The final deliverable should demonstrate applied learning and higher-order thinking."
            ),
            input_files=self.catalog_dict.get("assessment_planning", []),
            output_format="md",
        )

        
    def run(self, output_dir: str = "./outputs/") -> List[str]:
        """Run the ADDIE workflow using the ADDIERunner
        
        Args:
            output_dir: Directory to save results in (defaults to ./outputs/)
            
        Returns:
            List of results from each deliberation
        """
        runner = ADDIERunner(self, output_dir=output_dir, resume=self.resume)
        return runner.run()
