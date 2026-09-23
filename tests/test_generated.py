"""End-to-end tests that generate code and actually run the compiled LangGraph.

Unlike test_translator.py (which only checks the generated source compiles and
contains expected strings), these tests build and invoke the generated graph in
an isolated subprocess -- exactly what a user does with `python -m <package>`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from dify2langgraph.cli import translate

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Name of the generated package directory (a valid Python identifier so it can be
# imported as a package, exercising the relative imports -- ADR-0007).
_PKG = "wf"

# Snippet run from the package's parent dir: import the generated package, invoke
# its graph with a minimal initial state, and print the resulting state as JSON.
_RUN_SNIPPET = """
import json
import sys

sys.path.insert(0, ".")
from wf import build_graph

result = build_graph().invoke({initial})
print(json.dumps(result))
"""


def _run_python(
    args: list[str], cwd: Path, io_encoding: str = "utf-8"
) -> subprocess.CompletedProcess:
    """Run a child Python with a pinned stdio codec on both ends.

    Generated packages carry non-ASCII text (node titles, prompts, model output).
    Left to the default, the child encodes stdout with the OS console codepage --
    cp932 on Japanese Windows -- and the parent decodes with that same codepage,
    so the round trip differs per host. Pin both sides instead.

    Args:
        args: Arguments after the interpreter (e.g. ``["-m", "wf"]``).
        cwd: Working directory for the child process.
        io_encoding: Codec forced on the child's stdio and used to decode it.
            Pass a narrow codec to reproduce a legacy Windows console anywhere.

    Returns:
        The completed process, with stdout/stderr decoded as ``io_encoding``.
    """
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding=io_encoding,
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": io_encoding},
    )


def _generate_and_run(output_dir: Path, fixture: str, initial: dict) -> dict:
    """Generate a fixture into a package, run it as `python -m`-style, return state.

    Generates into ``output_dir/wf`` (a self-contained package) and imports it as
    ``wf`` from ``output_dir`` -- so the run exercises the generated relative
    imports, not a sys.path hack.

    Args:
        output_dir: Parent directory; the package is generated into ``output_dir/wf``.
        fixture: Fixture filename under tests/fixtures/.
        initial: Initial state passed to the compiled graph's invoke(). Must
            carry the workflow's declared inputs under the Start Node's own
            state key; missing required ones raise rather than default.

    Returns:
        The final GraphState after invocation (node key -> output dict).
    """
    translate(FIXTURES_DIR / fixture, output_dir / _PKG)

    snippet = _RUN_SNIPPET.format(initial=repr(initial))
    proc = _run_python(["-c", snippet], output_dir)
    assert proc.returncode == 0, f"generated graph failed to run:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


class TestGeneratedGraphRuns:
    """The generated graph must build and execute end-to-end."""

    def test_simple_workflow_runs(self, tmp_path):
        """A linear start -> llm -> end graph builds, invokes, and visits every node."""
        state = _generate_and_run(
            tmp_path, "simple_workflow.yml", {"start_node": {"query": "example"}}
        )
        assert sorted(state) == ["end_node", "llm_node", "start_node"]

    def test_package_runs_as_module(self, tmp_path):
        """`python -m <pkg>` runs the __main__ entry point end-to-end (ADR-0007)."""
        translate(FIXTURES_DIR / "simple_workflow.yml", tmp_path / _PKG)
        proc = _run_python(["-m", _PKG], tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "start_node" in proc.stdout  # __main__ prints the final state

    def test_package_prints_non_ascii_state_on_legacy_codepage(self, tmp_path):
        """`python -m <pkg>` survives a console codec that cannot encode the state.

        Once node bodies are implemented, real workflows put Japanese/Chinese text
        in the state. On Windows stdout defaults to the console codepage, and a
        state it cannot encode kills the run with UnicodeEncodeError. The generated
        ``__main__.py`` escapes those characters instead; force a narrow codec on
        the child to reproduce that console on any host.
        """
        translate(FIXTURES_DIR / "simple_workflow.yml", tmp_path / _PKG)

        # Stand in for an implemented node: return text the codec cannot encode.
        node = tmp_path / _PKG / "nodes" / "llm_node.py"
        src = node.read_text(encoding="utf-8")
        assert '"text": "placeholder"' in src
        node.write_text(
            src.replace('"text": "placeholder"', '"text": "\u7ffb\u8a33\u7d50\u679c"'),
            encoding="utf-8",
        )

        proc = _run_python(["-m", _PKG], tmp_path, io_encoding="cp1252")
        assert proc.returncode == 0, proc.stderr
        assert "\\u7ffb" in proc.stdout  # escaped, not crashed

    def test_workflow_inputs_reach_the_graph(self, tmp_path):
        """The caller's inputs survive the Start Node (ADR-0009).

        They used to be overwritten: the Start Node emitted a Stub returning
        {"query": "placeholder"}, so a generated workflow could not be given
        inputs at all, whatever the caller passed.
        """
        state = _generate_and_run(
            tmp_path, "simple_workflow.yml", {"start_node": {"query": "CALLER_VALUE"}}
        )

        assert state["start_node"]["query"] == "CALLER_VALUE"
        # And it flows downstream: End forwards the LLM node's text (ADR-0004).
        assert state["end_node"]["result"] == state["llm_node"]["text"]

    def test_missing_required_input_fails_loudly(self, tmp_path):
        """A required input that was never supplied must not be invented."""
        translate(FIXTURES_DIR / "simple_workflow.yml", tmp_path / _PKG)
        runner = Path(__file__).resolve().parents[1] / "scripts" / "run_generated.py"
        proc = _run_python([str(runner), str(tmp_path), _PKG], tmp_path)

        assert proc.returncode != 0
        assert "missing required workflow input" in proc.stdout + proc.stderr
        assert "query" in proc.stdout + proc.stderr

    def test_end_node_forwards_upstream_value(self, tmp_path):
        """The End node deterministically forwards an upstream field (ADR-0004).

        Its ``result`` output is wired to ``state["llm_node"]["text"]``, so after a
        run the End output equals the LLM node's text rather than a placeholder.
        """
        state = _generate_and_run(
            tmp_path, "simple_workflow.yml", {"start_node": {"query": "example"}}
        )
        assert state["end_node"]["result"] == state["llm_node"]["text"]

    def test_guardduty_workflow_runs(self, tmp_path):
        """A branching workflow with RAG/tool nodes still builds and invokes."""
        state = _generate_and_run(
            tmp_path, "guardduty_handler.yml",
            {"node_1722391426202": {"finding": "f", "type": "t", "severity": 1.0}}
        )
        # Every node currently gets a stub, so invocation completes without error.
        assert "node_1722391426202" in state  # start
        assert "node_1722397570856" in state  # question-classifier
        # knowledge-retrieval calls the Retriever port; unconfigured -> [] (ADR-0006),
        # so the graph still runs end-to-end without Dify API credentials.
        assert state["node_1722397470145"]["result"] == []

    def test_question_classifier_routes_to_single_branch(self, tmp_path):
        """A question-classifier reaches exactly one of its downstream ends.

        Routing is generated per ADR-0003: the stub defaults the decision field
        (``class_id``) to the first branch key, so the router resolves to a single
        successor instead of fanning out to every branch.
        """
        state = _generate_and_run(
            tmp_path, "guardduty_handler.yml",
            {"node_1722391426202": {"finding": "f", "type": "t", "severity": 1.0}}
        )
        # The two end nodes are the two branches of the classifier; only one
        # should be reached now that routing is correct.
        ends = {"node_1722399235845", "node_1722399356175"}
        assert len(ends & set(state)) == 1

    def test_if_else_routes_to_single_branch(self, tmp_path):
        """An if-else reaches exactly one of its true/false branches.

        The stub defaults ``selected_branch`` to the first branch key (``true``),
        so the router resolves to a single successor instead of fanning out.
        """
        state = _generate_and_run(
            tmp_path, "ifelse_workflow.yml", {"start_node": {"query": "example"}}
        )
        ends = {"end_true", "end_false"}
        assert len(ends & set(state)) == 1


class TestRealWorkflows:
    """End-to-end runs against real Dify workflow exports (see fixtures/SOURCES.md)."""

    def test_env_sys_workflow_runs(self, tmp_path):
        """A real export using structured output and sys.* builds and invokes.

        Before structured_output was declared, this raised
        KeyError: 'structured_output' the moment the End node read through it.
        """
        state = _generate_and_run(
            tmp_path,
            "env_sys_workflow.yml",
            {
                "node_1785682240366": {"query": "hello", "topk": 5.0},
                # sys.* is supplied by the caller under its reserved key (ADR-0004);
                # the End node forwards sys.app_id.
                "sys": {"app_id": "APP-1", "user_id": "U-9"},
            },
        )

        # The caller's value survives, and the declared defaults fill the rest.
        assert state["node_1785682240366"]["query"] == "hello"
        assert state["node_1785682240366"]["lang"] == "en"
        # structured_output is shaped from the schema, so End resolves through it.
        assert state["node_1785682317200"]["random_number"] == 0.0
        # sys.* reaches the End output from the caller's reserved key.
        assert state["node_1785682317200"]["app_id"] == "APP-1"


    """End-to-end runs against real Dify workflow exports (see fixtures/SOURCES.md)."""

    def test_translation_workflow_routes_to_single_if_else_branch(self, tmp_path):
        """A real workflow with an if-else reaches exactly one branch target."""
        state = _generate_and_run(
            tmp_path,
            "translation_workflow.yml",
            {
                "node_1721117927142": {
                    "target_lang": "ja",
                    "source_text": "hello",
                    "source_lang": "en",
                }
            },
        )
        # if-else 1721118545228: 'true' -> ...559807, 'false' -> ...668192.
        branches = {"node_1721118559807", "node_1721118668192"}
        assert len(branches & set(state)) == 1

    def test_chatflow_builds_and_runs(self, tmp_path):
        """A chatflow export runs even though it declares no `end` node.

        Its terminal is an `answer` node, and its user input arrives as sys.query
        rather than as a Start variable.
        """
        state = _generate_and_run(
            tmp_path, "chatflow_sys_query.yml", {"sys": {"query": "hello", "files": []}}
        )

        assert state["sys"]["query"] == "hello"
        assert "answer" in state

    def test_json_translate_workflow_builds_and_runs(self, tmp_path):
        """A real workflow using code/tool/iteration still builds and invokes.

        Iteration internals are stubbed via the fallback handler (ADR-0005 leaves
        the iteration shape open), but the graph must still compile and run.
        """
        state = _generate_and_run(
            tmp_path, "json_translate.yml", {"node_1731659178787": {"json_data": "{}"}}
        )
        assert "node_1731659178787" in state  # start node ran
