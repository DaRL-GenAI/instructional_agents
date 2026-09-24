"""Command-line entry point for course evaluation.

The implementation lives in ``src/evaluate.py``; this module only keeps the
historical ``python evaluate.py --exp <name>`` invocation working.
"""
import argparse
import json
import os

from src.evaluate import *  # noqa: F401,F403 — re-export for backwards compatibility
from src.evaluate import main


if __name__ == "__main__":
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path) and not os.environ.get("OPENAI_API_KEY"):
        with open(config_path, "r", encoding="utf-8") as f:
            os.environ.setdefault("OPENAI_API_KEY", json.load(f).get("OPENAI_API_KEY", ""))

    parser = argparse.ArgumentParser(description="Evaluate generated course materials")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="OpenAI model to use (default: gpt-4o-mini)")
    parser.add_argument("--exp", type=str, default="test", help="Experiment name for logging")
    parser.add_argument("--rigorous", action="store_true", help="Deterministic multi-sample scoring with anchored rubric bands")
    args = parser.parse_args()
    main(model_name=args.model, exp_name=args.exp, rigorous=args.rigorous)
