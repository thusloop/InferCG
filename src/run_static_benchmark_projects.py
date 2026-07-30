"""Run the fixed static-project benchmark with project-specific all_or_ea modes.

By default this writes static candidate graphs only. Use --mode infer to run
online LLM pruning over the same project groups.
"""

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path

from generate_call_graphs import (
    DEFAULT_OUTPUT_DIR,
    SRC_DIR,
    build_function_library,
    function_library_exists,
)


PROJECT_GROUPS = (
    (
        1,
        (
            "asciinema",
            "autojump",
            "fabric",
            "face_classification",
            "Sublist3r",
        ),
    ),
    (
        0,
        (
            "bpytop",
            "furl",
            "rich_cli",
            "sqlparse",
            "sshtunnel",
            "textrank4zh",
        ),
    ),
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate or LLM-prune the static-project benchmark call graphs."
    )
    parser.add_argument("--mode", choices=("candidates", "infer"), default="candidates")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--rebuild-library", action="store_true")
    parser.add_argument("--model", default="gpt-5.4")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL", "https://api.example.com/v1"),
        help="OpenAI-compatible API base URL (default: OPENAI_BASE_URL or https://api.example.com/v1).",
    )
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--confidence-threshold", type=float, default=60.0)
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--checkpoint-only",
        action="store_true",
        help="Reuse cached LLM responses only; never issue online inference requests.",
    )
    return parser.parse_args()


def load_call_graph_main():
    module_spec = importlib.util.spec_from_file_location(
        "autoextension_call_graph_main", SRC_DIR / "main.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if args.mode == "infer" and not args.checkpoint_only and not api_key:
        raise SystemExit("Error: --api-key or OPENAI_API_KEY is required for --mode infer.")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    original_cwd = Path.cwd()
    failures = []
    total_started = time.perf_counter()

    try:
        os.chdir(SRC_DIR)
        if str(SRC_DIR) not in sys.path:
            sys.path.insert(0, str(SRC_DIR))
        call_graph_main = load_call_graph_main()

        for all_or_ea, projects in PROJECT_GROUPS:
            for project_name in projects:
                print("\n=== {} (all_or_ea={}) ===".format(project_name, all_or_ea))
                try:
                    project_path = SRC_DIR.parent / "STAR" / "repo" / project_name
                    if function_library_exists(project_name) and not args.rebuild_library:
                        print("Function library: reusing existing STAR artifacts.")
                    else:
                        library_started = time.perf_counter()
                        library_result = build_function_library(project_name, project_path)
                        print(
                            "Function library: {:.2f}s; third-party dependencies: {}".format(
                                time.perf_counter() - library_started,
                                ", ".join(library_result["resolved_dependencies"]) or "none",
                            )
                        )

                    graph_output_path = str((output_dir / "{}.json".format(project_name)).resolve())
                    metrics_output_path = str(
                        (output_dir / "{}.metrics.json".format(project_name)).resolve()
                    )
                    if args.checkpoint_only:
                        call_graph_main.rebuild_graph_from_checkpoint(
                            name=project_name,
                            all_or_EA=all_or_ea,
                            model=args.model,
                            confidence_threshold=args.confidence_threshold,
                            output_path=graph_output_path,
                            metrics_output_path=metrics_output_path,
                        )
                    else:
                        call_graph_main.solve(
                            name=project_name,
                            all_or_EA=all_or_ea,
                            mode=args.mode,
                            api_key=api_key,
                            base_url=args.base_url,
                            model=args.model,
                            confidence_threshold=args.confidence_threshold,
                            max_candidates=args.max_candidates,
                            start_index=args.start_index,
                            output_path=graph_output_path,
                            metrics_output_path=metrics_output_path,
                            workers=args.workers,
                        )
                except Exception as error:
                    failures.append(project_name)
                    print("Failed: {}".format(error), file=sys.stderr)
    finally:
        os.chdir(original_cwd)

    print("\nBenchmark batch completed in {:.2f}s.".format(time.perf_counter() - total_started))
    if failures:
        raise SystemExit("Failed projects: {}".format(", ".join(failures)))


if __name__ == "__main__":
    main()
