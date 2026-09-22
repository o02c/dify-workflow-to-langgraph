#!/usr/bin/env python3
"""Run a generated LangGraph package and print its final state as JSON.

The generated output is a self-contained package run with ``python -m <pkg>``
from its parent directory (ADR-0007). Its ``__main__.py`` prints the final state
with ``print(result)`` -- a Python ``repr``, which is fine to read but awkward to
assert on from another language.

This runs the same thing and emits JSON instead, so a caller in any language can
check that the graph really executed: which nodes were visited, which branch a
Branching Node resolved to, what an End Node forwarded. ``scripts/verify-windows.ps1``
uses it to prove generated workflows run on a Windows host, and it doubles as a
way to inspect a generated package by hand.

    python scripts/run_generated.py <parent_dir> <package_name>
    python scripts/run_generated.py out wf --initial '{"start_node": {}}'
    python scripts/run_generated.py out wf --initial-file state.json

Output is ASCII-only JSON (``ensure_ascii=True``) so it survives any console code
page, which matters on Windows where stdout defaults to the OEM code page.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run_package(parent_dir: Path, package: str, initial: dict) -> dict:
    """Import a generated package, invoke its graph, and return the final state.

    Args:
        parent_dir: Directory containing the generated package.
        package: Package (directory) name; must be a valid Python identifier.
        initial: Initial GraphState passed to ``invoke()``.

    Returns:
        The final GraphState, as a plain dict.

    Raises:
        SystemExit: If the package cannot be found or imported.
    """
    parent = parent_dir.resolve()
    if not (parent / package / "__init__.py").is_file():
        raise SystemExit(f"not a generated package: {parent / package}")

    # Import as a package from its parent, exactly as `python -m <pkg>` does, so
    # the generated relative imports are exercised rather than bypassed.
    sys.path.insert(0, str(parent))
    try:
        module = __import__(package, fromlist=["build_graph"])
    except ImportError as exc:
        raise SystemExit(f"could not import {package}: {exc}") from exc

    return module.build_graph().invoke(initial)


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("parent_dir", type=Path, help="Directory containing the package")
    parser.add_argument("package", help="Generated package name")
    parser.add_argument(
        "--initial",
        default="{}",
        help='Initial state as JSON (default: {}). Example: \'{"start_node": {}}\'',
    )
    parser.add_argument(
        "--initial-file",
        type=Path,
        help="Read the initial state from a JSON file instead. Preferred from "
             "PowerShell, whose native-argument quoting mangles inline JSON.",
    )
    args = parser.parse_args()

    raw = args.initial
    if args.initial_file:
        raw = args.initial_file.read_text(encoding="utf-8")

    try:
        initial = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"initial state is not valid JSON: {exc}") from exc

    state = run_package(args.parent_dir, args.package, initial)

    # default=str keeps the call total: stub bodies emit plain data, but a
    # hand-implemented node may return something json cannot encode, and a
    # readable placeholder beats aborting the run.
    print(json.dumps(state, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
