import json
import os
import argparse



class RefinementRunner:

    def __init__(self, model_name, exp_name, threshold=3.0, retries=3):
        self.model_name = model_name
        self.exp_name = exp_name
        self.threshold = threshold
        self.retries = retries

        self.generated_course_path = f"exp/{exp_name}"
        self.evaluation_folder = f"eval/{model_name}-Evaluation_{exp_name}/evaluation_results"
        self.evaluation_json = f"{self.evaluation_folder}/evaluation_scores.json"

    def load_evaluation_results(self):
        if not os.path.exists(self.evaluation_json):
            raise FileNotFoundError(f"Evaluation results not found: {self.evaluation_json}")

        with open(self.evaluation_json, "r") as f:
            data = json.load(f)

        return data
        

    def build_repair_queue(self):
        results = self.load_evaluation_results()
        repair_queue = []

        for section_name, section_data in results.items():
            if section_name == "overall_summary":
                continue
            route = self.get_route_for_file_type(section_name)
            files = section_data.get("files", [])
            
            for file_data in files:
                eval_filename = file_data.get("filename")
                average = file_data.get("average")

                if eval_filename is None or average is None:
                    continue

                source_path = self.map_eval_filename_to_source_path(eval_filename)
                source_exists = os.path.exists(source_path) if source_path else False
                refined_path = self.map_source_path_to_refined_path(source_path)

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
        
        with open(source_path, "r") as f:
            content = f.read()
        return content
            
    def build_refinement_packet(self, queue_item):
        content = self.load_source_content(queue_item)

        packet = {
            "file_type": queue_item.get("file_type"),
            "route": queue_item.get("route"),
            "eval_filename": queue_item.get("eval_filename"),
            "source_path": queue_item.get("source_path"),
            "average": queue_item.get("average"),
            "metrics": queue_item.get("metrics"),
            "refined_path": queue_item.get("refined_path"),
            "content": content
        }

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

        with open(refined_path, "w") as f:
            f.write(refined_content)

        print(f"Saved refined content to: {refined_path}")

        return refined_path

    
    def run(self):
        queue = self.build_repair_queue()
        if not queue:
            return queue
        self.print_repair_queue(queue)
        
        packet = self.build_refinement_packet(queue[0])

        print(f"Packet Keys: {packet.keys()}")
        print(f"Content Length: {len(packet['content'])}")
        output_dir = self.ensure_output_directory(
            packet["refined_path"]
        )
        print(f"Output directory ready: {output_dir}")
        saved_path = self.save_refined_content(
            packet,
            packet["content"]
        )
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
    args = parser.parse_args()

    runner = RefinementRunner(
        model_name=args.model,
        exp_name=args.exp,
        threshold=args.threshold,
        retries=args.retries
    )

    runner.run()

if __name__ == "__main__":
    main()