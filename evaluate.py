import os
import json
from typing import List, Dict, Optional
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


class CourseEvaluationSystem:
    """
    Main system for evaluating course materials
    """
    def __init__(self, model_name: str, exp_name: str):
        self.llm = LLM(model_name=model_name)
        self.program_chair = ValidationAgent("Program Chair", self.llm)
        self.test_student = ValidationAgent("Test Student", self.llm)
        self.evaluator = EvaluationAgent(self.llm)
        self.exp_name = exp_name

        self.eval_dir = Path(f"eval/{model_name}-Evaluation_{self.exp_name}/evaluation_results")
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        self.valid_dir = Path(f"eval/{model_name}-Evaluation_{self.exp_name}/validation_reports")
        self.valid_dir.mkdir(parents=True, exist_ok=True)

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

def main(model_name, exp_name):
    """
    Main function to process course materials
    """
    print("Starting Course Material Evaluation System...")

    system = CourseEvaluationSystem(model_name, exp_name)
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
    
    args = parser.parse_args()
    main(model_name=args.model, exp_name=args.exp)