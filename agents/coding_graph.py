"""Coding agent subgraph for automatic lint error fixing.

This subgraph implements a lint → fix → verify loop using LangGraph.
"""

from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agents.linter import LintResult, run_ruff, run_ty


class CodingState(TypedDict):
    """State for the coding agent subgraph."""

    file_path: str
    file_content: str
    lint_results: list[LintResult]
    messages: list  # Chat history for LLM
    iteration: int
    max_iterations: int
    fixed: bool


CODING_SYSTEM_PROMPT = """You are an expert Python developer who fixes lint errors.

When given code with lint errors:
1. Analyze the errors carefully
2. Fix ONLY the errors - do not change logic or add features
3. Return the complete fixed code

Be precise and minimal. Only fix what's needed to resolve lint errors.
"""


def lint_node(state: CodingState) -> dict:
    """Run linters on the file."""
    file_path = state["file_path"]

    results = []
    results.append(run_ruff(file_path))
    results.append(run_ty(file_path))

    all_passed = all(r.success for r in results)

    return {
        "lint_results": results,
        "fixed": all_passed,
    }


def should_fix(state: CodingState) -> str:
    """Determine if we should attempt to fix errors."""
    if state["fixed"]:
        return "done"
    if state["iteration"] >= state["max_iterations"]:
        return "done"
    return "fix"


def prepare_fix_prompt(state: CodingState) -> dict:
    """Prepare the prompt for the LLM to fix errors."""
    file_path = state["file_path"]
    content = Path(file_path).read_text()

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

    messages = [
        SystemMessage(content=CODING_SYSTEM_PROMPT),
        HumanMessage(content=f"""Fix the following lint errors in this Python file.

## File: {file_path}

## Lint Errors:
{errors_text}

## Current Code:
```python
{content}
```

Return ONLY the fixed Python code, no explanations."""),
    ]

    return {
        "file_content": content,
        "messages": messages,
        "iteration": state["iteration"] + 1,
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
    Path(state["file_path"]).write_text(fixed_code)

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
    graph = StateGraph(CodingState)

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

        print(f"Processing: {py_file}")
        results[str(py_file)] = fix_file(py_file, llm, max_iterations)

    return results
