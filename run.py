import os
import time
import argparse
import json

from src.ADDIE import ADDIE


def load_catalog(catalog_dir: str = "catalog", catalog_name: str = "merged_catalog") -> dict:
    if catalog_dir == "copilot" and catalog_name == "default_copilot":
        default_copilot = {
            "learning_objectives": "",
            "syllabus": "",
            "slides": "",
            "script": "",
            "assessment": "",
            "overall": ""
        }
        return default_copilot

    merged_file = os.path.join(catalog_dir, f"{catalog_name}.json")

    try:
        with open(merged_file, "r", encoding="utf-8") as f:
            data_catalog = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load {catalog_name}.json: {e}")
        return {}

    for section, content in data_catalog.items():
        if isinstance(content, dict):
            print(f"{section}: {list(content.keys())} fields loaded.")
        else:
            print(f"{section}: loaded (type: {type(content).__name__})")

    return data_catalog


def run_instructional_design(course_name: str, copilot = None, catalog = None, model_name: str = "gpt-4o-mini", exp_name: str = "test"):
    """
    Main function to run the instructional design workflow by sequentially
    executing the six deliberation processes
    
    Args:
        copilot: Whether to enable copilot mode with user feedback
        model_name: Name of the LLM model to use
        exp_name: Name of the experiment for logging purposes
    
    Returns:
        List of results from each process
    """
    # Ensure the OPENAI_API_KEY is set
    if not os.environ.get("OPENAI_API_KEY"):
        api_key = input("Please enter your OpenAI API key: ").strip()
        if not api_key:
            print("Error: OpenAI API key is required to run this workflow.")
            return
        os.environ["OPENAI_API_KEY"] = api_key
    
    # Determine catalog flag and catalog source name
    use_catalog = catalog is not None
    catalog_source = catalog if use_catalog else None
    data_catalog = None
    
    use_copilot = copilot is not None
    copilot_source = copilot if use_copilot else None
    data_copilot = None

    # load input files
    if use_catalog:
        print(f"Loading catalog from source: {catalog_source}")
        data_catalog = load_catalog(catalog_dir="catalog", catalog_name=catalog_source)

    if use_copilot:
        print(f"Using copilot source: {copilot_source}")
        data_copilot = load_catalog(catalog_dir="copilot", catalog_name=copilot_source)

    # Get information about copilot mode
    mode_str = "COPILOT" if use_copilot else "AUTOMATIC"
    print("\n" + "="*80)
    print(f"INSTRUCTIONAL DESIGN WORKFLOW EXECUTION - {mode_str} MODE")
    print(f"Using SlidesDeliberation for enhanced slide generation")
    print("="*80 + "\n")

    if use_copilot:
        print("copilot mode enabled. You will be prompted for suggestions after each deliberation.")
        print("You can also choose to re-run a deliberation with your suggestions.\n")
    
    # Start timer
    start_time = time.time()
    
    # Create ADDIE instance
    print("Using catalog data for the workflow.")


    addie = ADDIE(course_name, model_name=model_name, copilot=use_copilot, catalog=use_catalog, data_catalog=data_catalog, data_copilot=data_copilot)

    # Run the workflow
    output_dir = f"./exp/{exp_name}/"
    os.makedirs(output_dir, exist_ok=True)
    addie.run(output_dir=output_dir)
    
    # Calculate execution time
    execution_time = time.time() - start_time
    hours, rem = divmod(execution_time, 3600)
    minutes, seconds = divmod(rem, 60)
    
    # Print completion message
    print("\n" + "="*80)
    print(f"WORKFLOW COMPLETED IN: {int(hours):02d}:{int(minutes):02d}:{seconds:.2f}")
    print("="*80 + "\n")


if __name__ == "__main__":
    with open("config.json", "r") as f:
        config = json.load(f)
    os.environ["OPENAI_API_KEY"] = config.get("OPENAI_API_KEY", "")

    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Run instructional design workflow")

    parser.add_argument("course_name", type=str, help="Name of the course")

    parser.add_argument(
        "--copilot", 
        type=str,
        nargs='?',  # optional, provided with string if available
        const="default_copilot",  # If user provides --copilot but no value, use "default"
        help="Enable copilot mode. Optionally specify copilot source name."
    )

    parser.add_argument(
        "--catalog", 
        type=str,
        nargs='?',  # optional, provided with string if available
        const="default_catalog",  # If user provides --catalog but no value, use "default"
        help="Enable catalog mode. Optionally specify catalog source name."
    )

    parser.add_argument(
        "--model", 
        type=str, 
        default="gpt-4o-mini",
        help="OpenAI model to use (default: gpt-4o-mini)"
    )

    parser.add_argument(
        "--exp", 
        type=str,
        default="test",
        help="Experiment name for logging"
    )

    args = parser.parse_args()

    # Run workflow with specified options
    run_instructional_design(
        course_name=args.course_name,
        copilot=args.copilot,
        catalog=args.catalog,
        model_name=args.model,
        exp_name=args.exp,
    )