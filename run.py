import os
import time
import argparse
import json


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


def run_instructional_design(course_name: str, copilot = None, catalog = None, model_name: str = "gpt-4o-mini", exp_name: str = "test", seed: int = None, temperature: float = None, resume: bool = False):
    """
    Main function to run the instructional design workflow by sequentially
    executing the six deliberation processes

    Args:
        copilot: Whether to enable copilot mode with user feedback
        model_name: Name of the LLM model to use
        exp_name: Name of the experiment for logging purposes
        resume: If True, skip deliberations whose outputs already exist in
            exp/{exp_name}/ and resume chapter generation from the last
            incomplete chapter (or mid-chapter checkpoint).

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


    from src.ADDIE import ADDIE
    addie = ADDIE(course_name, model_name=model_name, copilot=use_copilot, catalog=use_catalog, data_catalog=data_catalog, data_copilot=data_copilot, seed=seed, temperature=temperature, resume=resume)

    # Run the workflow
    output_dir = f"./exp/{exp_name}/"
    os.makedirs(output_dir, exist_ok=True)
    if resume:
        print(f"[resume] Resuming from existing outputs in {output_dir}")
    addie.run(output_dir=output_dir)
    
    # Calculate execution time
    execution_time = time.time() - start_time
    hours, rem = divmod(execution_time, 3600)
    minutes, seconds = divmod(rem, 60)
    
    # Print completion message
    print("\n" + "="*80)
    print(f"WORKFLOW COMPLETED IN: {int(hours):02d}:{int(minutes):02d}:{seconds:.2f}")
    print("="*80 + "\n")


def run_optimization(storage_id: str, user_requirements: str, model_name: str = "gpt-4o-mini",
                     exp_name: str = "optimize", chapter_name: str = None,
                     mode: str = "regenerate"):
    """
    Run the optimization workflow on existing slide materials.

    Args:
        storage_id: ID of the stored PDF files
        user_requirements: User's requirements for improvement
        model_name: Name of the LLM model to use
        exp_name: Experiment name for output directory
        chapter_name: Specific chapter to optimize (None = all chapters)
        mode: "regenerate" (per-slide full rewrite) or "refine" (localized
            frame-level rewrite via SlideRefiner)
    """
    # Ensure the OPENAI_API_KEY is set
    if not os.environ.get("OPENAI_API_KEY"):
        api_key = input("Please enter your OpenAI API key: ").strip()
        if not api_key:
            print("Error: OpenAI API key is required to run this workflow.")
            return
        os.environ["OPENAI_API_KEY"] = api_key

    output_dir = f"./exp/{exp_name}/"
    os.makedirs(output_dir, exist_ok=True)

    from src.ADDIE_optimize import ADDIEOptimizer
    optimizer = ADDIEOptimizer(model_name=model_name)
    optimizer.run(
        storage_id=storage_id,
        user_requirements=user_requirements,
        output_dir=output_dir,
        exp_name=exp_name,
        chapter_name=chapter_name,
        mode=mode,
    )


def main():
    """CLI entry point for instructional-agents."""
    # Load config if available
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        os.environ.setdefault("OPENAI_API_KEY", config.get("OPENAI_API_KEY", ""))

    # Set up command line arguments
    parser = argparse.ArgumentParser(description="Run instructional design workflow")

    parser.add_argument("course_name", type=str, nargs='?', default=None,
                        help="Name of the course (not required for --convert-pptx)")

    parser.add_argument(
        "--copilot",
        type=str,
        nargs='?',
        const="default_copilot",
        help="Enable copilot mode. Optionally specify copilot source name."
    )

    parser.add_argument(
        "--catalog",
        type=str,
        nargs='?',
        const="default_catalog",
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

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (passed to OpenAI API)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Sampling temperature (passed to OpenAI API)"
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume an interrupted run: skip deliberations whose outputs "
             "already exist in exp/<exp_name>/ and pick up chapter generation "
             "from the last incomplete chapter (or mid-chapter checkpoint)."
    )

    # Optimize mode arguments
    parser.add_argument(
        "--optimize",
        type=str,
        nargs='?',
        const=None,
        default=False,
        help="Optimize mode: provide storage_id of uploaded PDFs"
    )

    parser.add_argument(
        "--requirements",
        type=str,
        default="",
        help="User requirements for optimization (used with --optimize)"
    )

    parser.add_argument(
        "--chapter",
        type=str,
        default=None,
        help="Specific chapter to optimize (used with --optimize)"
    )

    # PPTX conversion arguments
    parser.add_argument(
        "--pptx",
        action="store_true",
        help="Also generate PPTX slides alongside PDF during course generation"
    )

    parser.add_argument(
        "--convert-pptx",
        type=str,
        default=None,
        metavar="DIR",
        help="Convert existing .tex files to .pptx. Provide exp directory path (e.g., ./exp/my_course/)"
    )

    args = parser.parse_args()

    # PPTX-only conversion mode (no ADDIE workflow, no API key needed)
    if args.convert_pptx is not None:
        from src.latex_to_pptx import LaTeXToPPTXConverter
        converter = LaTeXToPPTXConverter()
        results = converter.convert_directory(args.convert_pptx)
        if results:
            print(f"\nGenerated {len(results)} PPTX files:")
            for r in results:
                print(f"  {r}")
        else:
            print("No .tex files found to convert.")
        return

    # course_name is required for generate/optimize modes
    if not args.course_name:
        parser.error("course_name is required for generate/optimize modes")

    # Determine which mode to run
    if args.optimize is not False:
        # Optimize mode
        if args.optimize is None:
            print("Error: --optimize requires a storage_id value.")
            print("Usage: python run.py <course_name> --optimize <storage_id> --requirements \"...\"")
            exit(1)
        run_optimization(
            storage_id=args.optimize,
            user_requirements=args.requirements,
            model_name=args.model,
            exp_name=args.exp,
            chapter_name=args.chapter,
        )
    else:
        # Generate mode (default)
        run_instructional_design(
            course_name=args.course_name,
            copilot=args.copilot,
            catalog=args.catalog,
            model_name=args.model,
            exp_name=args.exp,
            seed=args.seed,
            temperature=args.temperature,
            resume=args.resume,
        )


if __name__ == "__main__":
    main()