"""Coding agent subgraph for automatic lint error fixing.

This subgraph implements a lint → fix → verify loop using LangGraph.
"""

import hashlib
from pathlib import Path
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from dify2langgraph.agents.linter import LintResult, run_ruff, run_ty
from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)


class ChangeRecord(TypedDict):
    """Record of a single code change."""

    iteration: int
    content_hash: str  # Hash of file content for quick comparison
    error_count: int


class CodingState(TypedDict):
    """State for the coding agent subgraph."""

    file_path: str
    file_content: str
    lint_results: list[LintResult]
    messages: list  # Chat history for LLM
    iteration: int
    max_iterations: int
    fixed: bool
    changes: list[ChangeRecord]  # History of changes for loop detection


CODING_SYSTEM_PROMPT = """You are an expert Python developer who fixes lint errors.

When given code with lint errors:
1. Analyze the errors carefully
2. Fix ONLY the errors - do not change logic or add features
3. Return the complete fixed code

IMPORTANT:
- Be precise and minimal. Only fix what's needed to resolve lint errors.
- If previous fix attempts are shown, DO NOT revert those changes.
- Build upon previous fixes, don't undo them.
- If you see the same error after a fix attempt, try a DIFFERENT approach.
"""


def _content_hash(content: str) -> str:
    """Generate a hash of file content for comparison."""
    return hashlib.md5(content.encode()).hexdigest()


def lint_node(state: CodingState) -> dict:
    """Run linters on the file."""
    file_path = state["file_path"]
    content = Path(file_path).read_text(encoding="utf-8")

    results = []
    results.append(run_ruff(file_path))
    results.append(run_ty(file_path))

    all_passed = all(r.success for r in results)
    error_count = sum(len(r.errors) if r.errors else (0 if r.success else 1) for r in results)

    # Record this state for loop detection
    change_record: ChangeRecord = {
        "iteration": state["iteration"],
        "content_hash": _content_hash(content),
        "error_count": error_count,
    }

    return {
        "lint_results": results,
        "fixed": all_passed,
        "file_content": content,
        "changes": state["changes"] + [change_record],
    }


def _is_looping(changes: list[ChangeRecord]) -> bool:
    """Detect if we're in a loop (same content hash seen before)."""
    if len(changes) < 2:
        return False

    current_hash = changes[-1]["content_hash"]
    previous_hashes = [c["content_hash"] for c in changes[:-1]]

    return current_hash in previous_hashes


def should_fix(state: CodingState) -> str:
    """Determine if we should attempt to fix errors."""
    if state["fixed"]:
        return "done"
    if state["iteration"] >= state["max_iterations"]:
        return "done"
    # Detect infinite loop: same content appeared before
    if _is_looping(state["changes"]):
        logger.debug("Loop detected at iteration %d, stopping.", state["iteration"])
        return "done"
    return "fix"


def prepare_fix_prompt(state: CodingState) -> dict:
    """Prepare the prompt for the LLM to fix errors."""
    file_path = state["file_path"]
    content = Path(file_path).read_text(encoding="utf-8")

    # Format lint errors
    error_lines = []
    for result in state["lint_results"]:
        if not result.success:
            error_lines.append(f"## {result.tool} errors:")
            if result.errors:
                for err in result.errors:
                    error_lines.append(f"- Line {err.get('location', {}).get('row', '?')}: {err.get('message', result.output)}")
            else:
                error_lines.append(result.output)

    errors_text = "\n".join(error_lines)

    # Format change history for context
    history_text = ""
    if state["changes"]:
        history_lines = ["## Previous Fix Attempts:"]
        for change in state["changes"]:
            history_lines.append(
                f"- Iteration {change['iteration']}: {change['error_count']} errors remaining"
            )
        history_text = "\n".join(history_lines) + "\n\n"

    iteration = state["iteration"] + 1
    messages = [
        SystemMessage(content=CODING_SYSTEM_PROMPT),
        HumanMessage(content=f"""Fix the following lint errors in this Python file.

## File: {file_path}
## Attempt: {iteration}

{history_text}## Current Lint Errors:
{errors_text}

## Current Code:
```python
{content}
```

Return ONLY the fixed Python code, no explanations.
DO NOT revert any previous fixes - build upon them."""),
    ]

    return {
        "file_content": content,
        "messages": messages,
        "iteration": iteration,
    }


def fix_node(state: CodingState, llm) -> dict:
    """Use LLM to fix the code."""
    response = llm.invoke(state["messages"])

    # Extract code from response
    fixed_code = response.content
    if "```python" in fixed_code:
        fixed_code = fixed_code.split("```python")[1].split("```")[0]
    elif "```" in fixed_code:
        fixed_code = fixed_code.split("```")[1].split("```")[0]

    fixed_code = fixed_code.strip()

    # Write fixed code
    Path(state["file_path"]).write_text(fixed_code, encoding="utf-8")

    return {
        "file_content": fixed_code,
        "messages": state["messages"] + [AIMessage(content=fixed_code)],
    }


def build_coding_graph(llm):
    """Build the coding agent subgraph.

    Args:
        llm: LangChain chat model instance.

    Returns:
        Compiled StateGraph.
    """
    graph = StateGraph(CodingState)  # ty: ignore[invalid-argument-type]

    # Add nodes
    graph.add_node("lint", lint_node)
    graph.add_node("prepare_fix", prepare_fix_prompt)
    graph.add_node("fix", lambda state: fix_node(state, llm))

    # Add edges
    graph.add_edge(START, "lint")
    graph.add_conditional_edges(
        "lint",
        should_fix,
        {
            "fix": "prepare_fix",
            "done": END,
        },
    )
    graph.add_edge("prepare_fix", "fix")
    graph.add_edge("fix", "lint")  # Loop back to verify

    return graph.compile()


def fix_file(
    file_path: str | Path,
    llm,
    max_iterations: int = 3,
) -> CodingState:
    """Fix lint errors in a single file.

    Args:
        file_path: Path to the Python file.
        llm: LangChain chat model instance.
        max_iterations: Maximum fix attempts.

    Returns:
        Final state with results.
    """
    graph = build_coding_graph(llm)

    initial_state: CodingState = {
        "file_path": str(file_path),
        "file_content": "",
        "lint_results": [],
        "messages": [],
        "iteration": 0,
        "max_iterations": max_iterations,
        "fixed": False,
        "changes": [],
    }

    return graph.invoke(initial_state)


def fix_directory(
    directory: Path,
    llm,
    max_iterations: int = 3,
) -> dict[str, CodingState]:
    """Fix lint errors in all Python files in a directory.

    Args:
        directory: Directory containing Python files.
        llm: LangChain chat model instance.
        max_iterations: Maximum fix attempts per file.

    Returns:
        Dict mapping file paths to their final states.
    """
    results = {}

    for py_file in directory.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        logger.info("Processing: %s", py_file)
        results[str(py_file)] = fix_file(py_file, llm, max_iterations)

    return results
