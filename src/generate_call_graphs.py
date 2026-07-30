"""Generate static Python call graphs for one or more project directories.

Example:
    python src/generate_call_graphs.py path/to/project-a path/to/project-b
"""

import argparse
import importlib.util
import os
import sys
import time
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
STAR_DIR = ROOT_DIR / "STAR"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "Ae_data"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build STAR function libraries and static call graphs for project directories."
    )
    parser.add_argument(
        "projects",
        nargs="+",
        type=Path,
        help="One or more Python project directories.",
    )
    parser.add_argument(
        "--names",
        nargs="+",
        help="Optional artifact names, one for each project path. Defaults to each directory name.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for <name>.json and metrics files.",
    )
    parser.add_argument(
        "--all-or-ea",
        type=int,
        choices=(0, 1),
        default=1,
        help="Include external/third-party candidates when set to 1 (default: 1).",
    )
    parser.add_argument(
        "--rebuild-library",
        action="store_true",
        help="Rebuild STAR artifacts and download dependencies even when they already exist.",
    )
    return parser.parse_args()


def resolve_projects(project_paths, names):
    if names is not None and len(names) != len(project_paths):
        raise ValueError("--names must provide exactly one name for each project path.")

    resolved = []
    for index, project_path in enumerate(project_paths):
        project_path = project_path.resolve()
        if not project_path.is_dir():
            raise ValueError("Project path is not a directory: {}".format(project_path))
        if not any(project_path.rglob("*.py")):
            raise ValueError("Project path contains no Python files: {}".format(project_path))
        name = names[index] if names is not None else project_path.name
        if not name or Path(name).name != name:
            raise ValueError("Project name must be a plain file name: {}".format(name))
        resolved.append((name, project_path))

    duplicate_names = {name for name, _ in resolved if sum(item[0] == name for item in resolved) > 1}
    if duplicate_names:
        raise ValueError(
            "Duplicate project directory names: {}. Supply unique names with --names.".format(
                ", ".join(sorted(duplicate_names))
            )
        )
    return resolved


def build_function_library(project_name, project_path):
    original_cwd = Path.cwd()
    try:
        os.chdir(STAR_DIR)
        if str(STAR_DIR) not in sys.path:
            sys.path.insert(0, str(STAR_DIR))
        from ConstructKB.get_pre_sta import get_knowledge

        return get_knowledge(
            project_name,
            str(project_path),
            str(project_path),
            benchmark="static",
        )
    finally:
        os.chdir(original_cwd)


def function_library_exists(project_name):
    required_files = (
        STAR_DIR / "pre_knowledge" / "{}_pre_annotations.json".format(project_name),
        STAR_DIR / "pre_knowledge" / "{}_import_info.json".format(project_name),
        STAR_DIR / "pre_knowledge" / "{}_pre_inherited.json".format(project_name),
    )
    return all(path.is_file() and path.stat().st_size > 0 for path in required_files)


def generate_static_graph(project_name, output_dir, all_or_ea):
    original_cwd = Path.cwd()
    try:
        os.chdir(SRC_DIR)
        if str(SRC_DIR) in sys.path:
            sys.path.remove(str(SRC_DIR))
        sys.path.insert(0, str(SRC_DIR))
        module_spec = importlib.util.spec_from_file_location(
            "autoextension_call_graph_main", SRC_DIR / "main.py"
        )
        call_graph_main = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(call_graph_main)

        call_graph_main.solve(
            name=project_name,
            all_or_EA=all_or_ea,
            mode="candidates",
            output_path=str((output_dir / "{}.json".format(project_name)).resolve()),
            metrics_output_path=str((output_dir / "{}.metrics.json".format(project_name)).resolve()),
        )
    finally:
        os.chdir(original_cwd)


def main():
    args = parse_args()
    try:
        projects = resolve_projects(args.projects, args.names)
    except ValueError as error:
        raise SystemExit("Error: {}".format(error))

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = []
    for project_name, project_path in projects:
        print("\n=== {} ===".format(project_name))
        try:
            if function_library_exists(project_name) and not args.rebuild_library:
                print(
                    "Function library: reusing existing STAR artifacts "
                    "(pass --rebuild-library to regenerate)."
                )
            else:
                library_started = time.perf_counter()
                library_result = build_function_library(project_name, project_path)
                library_seconds = time.perf_counter() - library_started
                print(
                    "Function library: {:.2f}s; third-party dependencies: {}".format(
                        library_seconds,
                        ", ".join(library_result["resolved_dependencies"]) or "none",
                    )
                )
            generate_static_graph(project_name, output_dir, args.all_or_ea)
        except Exception as error:
            failures.append(project_name)
            print("Failed: {}".format(error), file=sys.stderr)

    if failures:
        raise SystemExit("Call-graph generation failed for: {}".format(", ".join(failures)))


if __name__ == "__main__":
    main()
