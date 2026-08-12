"""End-to-end tests that generate code and actually run the compiled LangGraph.

Unlike test_translator.py (which only checks the generated source compiles and
contains expected strings), these tests build and invoke the generated graph in
an isolated subprocess -- exactly what a user does with `python graph.py`.
"""

import json
import subprocess
import sys
from pathlib import Path

from dify2langgraph.cli import translate

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Snippet run inside the generated output dir: build the graph, invoke it with a
# minimal initial state, and print the resulting state keys as JSON.
_RUN_SNIPPET = """
import json
import sys

sys.path.insert(0, ".")
from graph import build_graph

result = build_graph().invoke({initial})
print(json.dumps(sorted(result.keys())))
"""


def _generate_and_run(output_dir: Path, fixture: str, initial: dict) -> list[str]:
    """Generate code for a fixture, run its graph, and return the result keys.

    Args:
        output_dir: Directory to generate into (and run from).
        fixture: Fixture filename under tests/fixtures/.
        initial: Initial state passed to the compiled graph's invoke().

    Returns:
        Sorted list of state keys present after invocation.
    """
    translate(FIXTURES_DIR / fixture, output_dir)

    snippet = _RUN_SNIPPET.format(initial=repr(initial))
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        cwd=output_dir,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"generated graph failed to run:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


class TestGeneratedGraphRuns:
    """The generated graph must build and execute end-to-end."""

    def test_simple_workflow_runs(self, tmp_path):
        """A linear start -> llm -> end graph builds, invokes, and visits every node."""
        keys = _generate_and_run(
            tmp_path, "simple_workflow.yml", {"start_node": {}}
        )
        assert keys == ["end_node", "llm_node", "start_node"]

    def test_guardduty_workflow_runs(self, tmp_path):
        """A branching workflow with RAG/tool nodes still builds and invokes."""
        keys = _generate_and_run(
            tmp_path, "guardduty_handler.yml", {"node_1722391426202": {}}
        )
        # Every node currently gets a stub, so invocation completes without error.
        assert "node_1722391426202" in keys  # start
        assert "node_1722397570856" in keys  # question-classifier

    def test_question_classifier_routes_to_single_branch(self, tmp_path):
        """A question-classifier reaches exactly one of its downstream ends.

        Routing is generated per ADR-0003: the stub defaults the decision field
        (``class_id``) to the first branch key, so the router resolves to a single
        successor instead of fanning out to every branch.
        """
        keys = _generate_and_run(
            tmp_path, "guardduty_handler.yml", {"node_1722391426202": {}}
        )
        # The two end nodes are the two branches of the classifier; only one
        # should be reached now that routing is correct.
        ends = {"node_1722399235845", "node_1722399356175"}
        assert len(ends & set(keys)) == 1

    def test_if_else_routes_to_single_branch(self, tmp_path):
        """An if-else reaches exactly one of its true/false branches.

        The stub defaults ``selected_branch`` to the first branch key (``true``),
        so the router resolves to a single successor instead of fanning out.
        """
        keys = _generate_and_run(
            tmp_path, "ifelse_workflow.yml", {"start_node": {}}
        )
        ends = {"end_true", "end_false"}
        assert len(ends & set(keys)) == 1
