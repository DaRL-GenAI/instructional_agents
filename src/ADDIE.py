import os
import json
import re
from typing import List, Dict

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
        
        Syllabus Content:
        {syllabus_content}
        
        Example format:
        [
            {{
                "title": "Chapter 1: Introduction to Machine Learning",
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
    def __init__(self, addie_instance, output_dir="output"):
        """
        Initialize the runner with an ADDIE instance
        
        Args:
            addie_instance: An instance of the ADDIE class
        """
        self.addie = addie_instance
        self.course_name = None
        self.output_dir = output_dir
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
    
    def run_foundation_deliberations(self):
        """Run the first 6 foundational deliberations"""
        print(f"\n{'#'*60}\nStarting ADDIE Workflow: Foundation Phase\n{'#'*60}\n")
        
        # Get the first 6 deliberations
        foundation_deliberations = self.addie.deliberations
        
        # Run each deliberation in sequence
        i = 0
        statistics = []
        while i < len(foundation_deliberations):
            deliberation = foundation_deliberations[i]
            print(f"\n{'#'*50}\nDeliberation {i+1}/{len(foundation_deliberations)}: {deliberation.name}\n{'#'*50}\n")
            
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
            
            # Run deliberation with current state and user suggestion
            result, elapsed_time, token_usage = deliberation.run(current_context=str(self.results), user_suggestion=user_suggestion)
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

        # After running the syllabus design deliberation, process the syllabus
        self._process_syllabus()
    
    def _process_syllabus(self):
        """Process the syllabus to extract chapters"""
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
        else:
            print("Error: Syllabus not found in results. Cannot process chapters.")
    
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
            
            # Run SlidesDeliberation for this chapter with retry support
            self._run_slides_generation_with_retry(chapter, chapter_idx, chapter_dir)
        
        # After all chapters, compile the LaTeX source and slides script
        compiler = LaTeXCompiler(self.output_dir)
        compiler.compile_all()
        
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

        # Create a SlidesDeliberation instance for this chapter
        slides_deliberation = self._create_slides_deliberation(chapter, f"chapter_{chapter_idx+1}")
        
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
    
    def _create_slides_deliberation(self, chapter, chapter_dir_name):
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
        
        # Create and return the slides deliberation
        return SlidesDeliberation(
            id=f"slides_{chapter_dir_name}",
            name=f"Slides Generation - {chapter['title']}",
            agents=agents,
            llm=self.addie.llm,
            output_dir=os.path.join(self.output_dir, chapter_dir_name),
            catalog=self.addie.catalog,
            catalog_dict=self.addie.catalog_dict,
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
            
            if chapter_context:
                # Re-run chapter deliberation with combined suggestions but original context
                result = deliberation.run(current_context=context_str, user_suggestion=combined_suggestions)
                
                # Save to chapter directory
                chapter_dir = os.path.join(self.output_dir, f"chapter_{chapter_idx+1}")
                self._save_chapter_result(deliberation, result, chapter_idx, chapter_dir)
            else:
                # Re-run foundation deliberation with combined suggestions but original context
                result = deliberation.run(current_context=context_str, user_suggestion=combined_suggestions)
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
    def __init__(self, course_name, model_name: str = "gpt-4o-mini", copilot: bool = False, catalog: bool = False, data_catalog: dict = {}, data_copilot: dict = {}):
        """
        Initialize ADDIE workflow
        
        Args:
            model_name: Name of the LLM model to use
            copilot: Whether to enable copilot mode with user feedback
        """
        self.course_name = course_name
        self.model_name = model_name
        self.copilot = copilot
        self.catalog = catalog
        self.llm = LLM(model_name=model_name)
        self.deliberations = []
        self.results = []
        
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
        runner = ADDIERunner(self, output_dir=output_dir)
        return runner.run()
