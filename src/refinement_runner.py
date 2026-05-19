import json
import os
import argparse
from src.agents import LLM
from src.refinement import RefinementEngine
from pathlib import Path
from src.compile import LaTeXCompiler

class RefinementRunner:

    def __init__(self, model_name, exp_name, route="all", threshold=3.0, retries=3, refine=False):
        self.model_name = model_name
        self.exp_name = exp_name
        self.threshold = threshold
        self.retries = retries
        self.refine = refine
        self.route = route

        self.generated_course_path = f"exp/{exp_name}"
        self.evaluation_folder = f"eval/{model_name}-Evaluation_{exp_name}/evaluation_results"
        self.evaluation_json = f"{self.evaluation_folder}/evaluation_scores.json"

    def load_evaluation_results(self):
        if not os.path.exists(self.evaluation_json):
            raise FileNotFoundError(f"Evaluation results not found: {self.evaluation_json}")

        with open(self.evaluation_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        return data


    def build_repair_queue(self):
        results = self.load_evaluation_results()
        repair_queue = []

        for section_name, section_data in results.items():
            if section_name == "overall_summary":
                continue
            route = self.get_route_for_file_type(section_name)
            if self.route != "all" and route != self.route:
                continue
            files = section_data.get("files", [])

            for file_data in files:
                eval_filename = file_data.get("filename")
                average = file_data.get("average")

                if eval_filename is None or average is None:
                    continue

                source_path = self.map_eval_filename_to_source_path(eval_filename)
                source_exists = os.path.exists(source_path) if source_path else False
                refined_path = self.map_source_path_to_refined_path(source_path)
                validation_reports = self.map_eval_filename_to_validation_reports(
                    section_name,
                    eval_filename
                )

                if average < self.threshold:
                    metrics = file_data.get("scores", {})

                    queue_item = {
                        "file_type": section_name,
                        "eval_filename": eval_filename,
                        "average": average,
                        "metrics": metrics,
                        "route": route,
                        "source_path": source_path,
                        "source_exists": source_exists,
                        "validation_reports": validation_reports,
                        "refined_path": refined_path
                    }

                    repair_queue.append(queue_item)

        return repair_queue

    def print_repair_queue(self, queue):
        print("REFINEMENT QUEUE")
        print("================")
        print(f"Experiment: {self.exp_name}")
        print(f"Model: {self.model_name}")
        print(f"Threshold: {self.threshold}")
        print(f"Max Attempts: {self.retries}")
        print(f"Files Queued: {len(queue)}")

        for i, item in enumerate(queue, 1):
            print(f"\n{i}. {item['eval_filename']}")
            print(f"   Type: {item['file_type']}")
            print(f"   Route: {item['route']}")
            print(f"   Average: {round(item['average'], 2)}")
            print(f"   Source: {item['source_path']}")
            print(f"   Refined Path: {item['refined_path']}")
            print(f"   Exists: {item['source_exists']}")

            reports = item.get("validation_reports", [])
            found_reports = sum(
                1 for report in reports
                if report.get("exists")
            )
            total_reports = len(reports)
            print(f"   Validation Reports Found: "
                f"{found_reports}/{total_reports}"
            )

            print("   Metrics:")
            for metric_name, metric_data in item["metrics"].items():
                score = metric_data.get("score")
                print(f"   - {metric_name}: {score}")


    def map_eval_filename_to_source_path(self, eval_filename):
        if eval_filename == "result_instructional_goals.md":
            return f"{self.generated_course_path}/result_instructional_goals.md"
        if eval_filename == "result_syllabus_design.md":
            return f"{self.generated_course_path}/result_syllabus_design.md"

        parts = eval_filename.split("_")
        if len(parts) < 3:
            return None
        if parts[0] != "chapter":
            return None

        chapter = parts[1]
        file_part = parts[2]

        if "." not in file_part:
            return None

        name = file_part.split(".")[0]
        if name == "assessment":
            return f"{self.generated_course_path}/chapter_{chapter}/assessment.md"
        if name == "script":
            return f"{self.generated_course_path}/chapter_{chapter}/script.md"
        if name == "slides":
            return f"{self.generated_course_path}/chapter_{chapter}/slides.tex"
        return None

    def map_eval_filename_to_validation_reports(self, file_type, eval_filename):
        if file_type != "assessment":
            return []

        validation_dir = ( f"eval/{self.model_name}-Evaluation_{self.exp_name}/validation_reports" )
        roles = ["Program_Chair", "Test_Student"]

        reports = []

        for role in roles:
            report_filename = f"{role}_{file_type}_{eval_filename.replace('.md', '_validation.md')}"
            report_path = f"{validation_dir}/{report_filename}"

            reports.append({
                "role": role,
                "path": report_path,
                "exists": os.path.exists(report_path)
           })

        return reports

    def load_validation_reports(self, queue_item):
        reports = queue_item.get("validation_reports", [])

        combined_feedback = []

        for report in reports:
            if not report.get("exists"):
                continue

            path = report.get("path")
            role = report.get("role")

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                compact_content = self.compact_validation_report(content)


            combined_feedback.append(
                f"VALIDATION REPORT: {role}\n\n{compact_content}"
            )


        return "\n\n".join(combined_feedback)

    def compact_validation_report(self, content):
        lower_content = content.lower()

        lines = content.splitlines()

        strengths_idx = None
        rating_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if strengths_idx is None and stripped.startswith("#") and "strengths" in stripped:
                strengths_idx = i
            if rating_idx is None and stripped.startswith("#") and "rating" in stripped:
                rating_idx = i

        if strengths_idx is None or rating_idx is None:
            return content[:3000]
        if rating_idx <= strengths_idx:
            return content[:3000]

        return "\n".join(lines[strengths_idx:rating_idx]).strip()

    def get_route_for_file_type(self, file_type):
        if file_type == "assessment":
            return "assessment"
        if file_type == "slide_scripts":
            return "script"
        if file_type == "slide_content":
            return "slides"
        if file_type == "syllabus":
            return "syllabus"
        if file_type == "learning_objectives":
            return "objectives"
        return "general"


    def load_source_content(self, queue_item):
        source_path = queue_item.get("source_path")
        if not queue_item.get("source_exists") or not source_path:
            raise FileNotFoundError(f"Source file not found: {source_path}")

        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content

    def build_refinement_packet(self, queue_item):
        content = self.load_source_content(queue_item)
        validation_feedback = self.load_validation_reports(queue_item)

        packet = {
            "file_type": queue_item.get("file_type"),
            "route": queue_item.get("route"),
            "eval_filename": queue_item.get("eval_filename"),
            "source_path": queue_item.get("source_path"),
            "average": queue_item.get("average"),
            "metrics": queue_item.get("metrics"),
            "refined_path": queue_item.get("refined_path"),
            "content": content,
            "validation_feedback": validation_feedback,
            "validation_reports": queue_item.get("validation_reports"),
        }

        if queue_item.get("route") == "script":
            source_path = queue_item.get("source_path")
            slides_path = source_path.replace("script.md", "slides.tex")
            refined_slides_path = slides_path.replace(
                self.generated_course_path,
                f"{self.generated_course_path}/refined",
                1
            )

            if os.path.exists(refined_slides_path):
                slides_path = refined_slides_path

            if not os.path.exists(slides_path):
                raise FileNotFoundError(
                    f"Matching slides file not found for script: {slides_path}"
                )

            with open(slides_path, "r", encoding="utf-8") as f:
                packet["slides_content"] = f.read()

            packet["slides_path"] = slides_path

        return packet

    def map_source_path_to_refined_path(self, source_path):
        if not source_path:
            return None

        refined_root = f"{self.generated_course_path}/refined"
        refined_path = source_path.replace(self.generated_course_path, refined_root, 1)

        return refined_path

    def ensure_output_directory(self, refined_path):
        if not refined_path:
            raise ValueError("Refined path is required before creating output directory")

        output_dir = os.path.dirname(refined_path)
        os.makedirs(output_dir, exist_ok=True)

        return output_dir

    def save_refined_content(self, packet, refined_content):
        refined_path = packet.get("refined_path")

        if not refined_path:
            raise ValueError("Refined path is required before writing output")
        self.ensure_output_directory(refined_path)

        with open(refined_path, "w", encoding="utf-8") as f:
            f.write(refined_content)

        print(f"Saved refined content to: {refined_path}")

        return refined_path

    def extract_latex_errors(self, cache_dir):

        error_lines = []
        unique_errors = set()

        log_files = [
            "slides_compilation.log",
            "slides_pdflatex.log"
        ]

        keywords = [
            "LaTeX Error",
            "Undefined control sequence",
            "Emergency stop",
            "Fatal error",
            "Missing $",
            "Missing }",
            "! "
        ]

        for log_name in log_files:

            log_path = Path(cache_dir) / log_name

            if not log_path.exists():
                continue

            try:

                with open(log_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for line in lines:

                    stripped = line.strip()

                    if any(keyword in stripped for keyword in keywords):
                        if stripped not in unique_errors:
                            error_lines.append(stripped)
                            unique_errors.add(stripped)

            except Exception:
                continue

        if not error_lines:
            error_lines.append(
                "PDF compilation failed with no specific LaTeX errors found"
            )

        return error_lines[:10]

    def compile_refined_slides(self, saved_path):

        tex_path = Path(saved_path)
        compiler = LaTeXCompiler(f"{self.generated_course_path}/refined")
        latex_available = compiler.validate_latex_environment()

        if not latex_available:
            return {
                "compile_status": "NOT_RUN",
                "compile_errors": ["pdflatex not available"],
                "pdf_path": None
            }

        try:
            cache_dir = compiler.create_cache_directory(tex_path)

            pdf_file = compiler.compile_latex(tex_path, cache_dir)

            if pdf_file and pdf_file.exists():
                compiler.move_pdf_to_source_location(pdf_file, tex_path)
                final_pdf_path = tex_path.with_suffix(".pdf")

                return {
                    "compile_status": "PASS",
                    "compile_errors": [],
                    "pdf_path": str(final_pdf_path)
                }

            compile_errors = self.extract_latex_errors(
                cache_dir
            )

            return {
                "compile_status": "FAIL",
                "compile_errors": compile_errors,
                "pdf_path": None
            }

        except Exception as e:
            return {
                "compile_status": "FAIL",
                "compile_errors": [str(e)],
                "pdf_path": None
            }



    def run(self):
        queue = self.build_repair_queue()
        self.print_repair_queue(queue)

        if not queue:
            return queue

        if not self.refine:
            print("\nPreview only. Use --refine to run refinement.")
            return queue

        llm = LLM(self.model_name)
        engine = RefinementEngine(llm)
        refinement_results = []

        for item in queue:
            if item["route"] not in ["assessment", "slides", "script", "syllabus", "objectives"]:
                print(
                    f"Skipping {item['eval_filename']}: "
                    f"route '{item['route']}' not implemented yet"
                )
                continue
            try:
                print(f"\nRefining {item['eval_filename']}...")

                packet = self.build_refinement_packet(item)

                result = engine.refine_packet(packet, self.retries)

                saved_path = self.save_refined_content(
                    packet,
                    result["refined_content"]
                )

                compile_result = {
                    "compile_status": "NOT_RUN",
                    "compile_errors": [],
                    "pdf_path": None
                }

                if packet["route"] == "slides":

                    compile_result = self.compile_refined_slides(
                        saved_path
                    )

                report_entry = {
                    "eval_filename": packet.get("eval_filename"),
                    "source_path": packet.get("source_path"),
                    "refined_path": saved_path,
                    "route": packet.get("route"),
                    "average": packet.get("average"),
                    "metrics": packet.get("metrics"),
                    "constraints": result.get("constraints"),
                    "repair_plan": result.get("repair_plan"),
                    "structure_facts": result.get("structure_facts"),
                    "original_structure_facts": result.get(
                        "original_structure_facts"
                    ),
                    "validation_reports": packet.get("validation_reports"),
                    "validation_feedback_included": bool(
                        packet.get("validation_feedback")
                    ),
                    "max_retries": self.retries,
                    "retries_used": result.get("retries_used"),
                    "pipeline_status": "success",
                    "validation_status": result.get("validation_status"),
                    "final_validation": result.get("final_validation"),
                    "validation_history": result.get("validation_history"),
                    "compile_status": compile_result["compile_status"],
                    "compile_errors": compile_result["compile_errors"],
                    "pdf_path": compile_result["pdf_path"]
                }

                refinement_results.append(report_entry)
            except Exception as e:
                report_entry = {
                    "eval_filename": item.get("eval_filename"),
                    "source_path": item.get("source_path"),
                    "refined_path": item.get("refined_path"),
                    "route": item.get("route"),
                    "average": item.get("average"),
                    "metrics": item.get("metrics"),
                    "pipeline_status": "failed",
                    "validation_status": "NOT_RUN",
                    "error": str(e)
                }
                refinement_results.append(report_entry)
                continue
        report_path = (
            f"{self.generated_course_path}/refined/refinement_report.json"
        )

        self.ensure_output_directory(report_path)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(refinement_results, f, indent=4)

        print(f"\nSaved refinement report to: {report_path}")

        return queue



def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Model name to use for evaluation"
    )
    parser.add_argument(
        "--exp",
        type=str,
        default="default",
        help="Experiment name to refine"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=3.0,
        help="Score threshold for selecting files to refine."
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="Maximum refinement attempts"
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Run refinement pipeline"
    )
    parser.add_argument(
    "--route",
    type=str,
    default="all",
    choices=["all", "assessment", "slides", "script", "syllabus", "objectives"],
    help="Only refine files for this route"
)

    args = parser.parse_args()

    runner = RefinementRunner(
        model_name=args.model,
        exp_name=args.exp,
        threshold=args.threshold,
        retries=args.retries,
        refine=args.refine,
        route=args.route
    )

    runner.run()

if __name__ == "__main__":
    main()
