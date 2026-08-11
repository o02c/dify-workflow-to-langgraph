"""Linter tools for code quality checks."""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class LintResult:
    """Result from running a linter."""

    tool: str
    file_path: str
    success: bool
    output: str
    errors: list[dict] = field(default_factory=list)


def run_ruff(file_path: str | Path, fix: bool = False) -> LintResult:
    """Run ruff linter on a file.

    Args:
        file_path: Path to the Python file.
        fix: If True, apply auto-fixes.

    Returns:
        LintResult with parsed output.
    """
    file_path = Path(file_path)
    cmd = ["ruff", "check", str(file_path), "--output-format", "json"]
    if fix:
        cmd.append("--fix")

    result = subprocess.run(cmd, capture_output=True, text=True)

    errors = []
    if result.stdout:
        try:
            errors = json.loads(result.stdout)
        except json.JSONDecodeError:
            pass

    return LintResult(
        tool="ruff",
        file_path=str(file_path),
        success=result.returncode == 0,
        output=result.stdout or result.stderr,
        errors=errors,
    )


def run_ty(file_path: str | Path) -> LintResult:
    """Run ty type checker on a file.

    Args:
        file_path: Path to the Python file.

    Returns:
        LintResult with parsed output.
    """
    file_path = Path(file_path)
    cmd = ["ty", "check", str(file_path)]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # ty outputs errors to stderr
    output = result.stdout + result.stderr

    return LintResult(
        tool="ty",
        file_path=str(file_path),
        success=result.returncode == 0,
        output=output,
        errors=[],  # ty doesn't have structured JSON output
    )


def lint_directory(
    directory: Path,
    tools: list[str] | None = None,
    fix: bool = False,
) -> dict[str, list[LintResult]]:
    """Lint all Python files in a directory.

    Args:
        directory: Directory to lint.
        tools: List of tools to run ("ruff", "ty"). Defaults to both.
        fix: If True, apply ruff auto-fixes.

    Returns:
        Dict mapping file paths to their lint results.
    """
    if tools is None:
        tools = ["ruff", "ty"]

    results: dict[str, list[LintResult]] = {}

    for py_file in directory.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        file_results = []

        if "ruff" in tools:
            file_results.append(run_ruff(py_file, fix=fix))

        if "ty" in tools:
            file_results.append(run_ty(py_file))

        results[str(py_file)] = file_results

    return results


def print_lint_summary(results: dict[str, list[LintResult]]) -> bool:
    """Print a summary of lint results.

    Args:
        results: Dict from lint_directory.

    Returns:
        True if all files passed, False otherwise.
    """
    all_passed = True
    total_errors = 0

    for file_path, file_results in results.items():
        for result in file_results:
            if not result.success:
                all_passed = False
                error_count = len(result.errors) if result.errors else 1
                total_errors += error_count
                logger.info("  %s: %s - %d issue(s)", result.tool, file_path, error_count)

    if all_passed:
        logger.info("All %d files passed linting.", len(results))
    else:
        logger.info("Found %d issue(s) in %d files.", total_errors, len(results))

    return all_passed
