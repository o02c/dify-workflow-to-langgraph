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

import yaml

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


def _generate_and_run(output_dir: Path, fixture: str | Path, initial: dict) -> dict:
    """Generate a fixture into a package, run it as `python -m`-style, return state.

    Generates into ``output_dir/wf`` (a self-contained package) and imports it as
    ``wf`` from ``output_dir`` -- so the run exercises the generated relative
    imports, not a sys.path hack.

    Args:
        output_dir: Parent directory; the package is generated into ``output_dir/wf``.
        fixture: Fixture filename under tests/fixtures/, or a path to a
            generated variant of one.
        initial: Initial state passed to the compiled graph's invoke(). Must
            carry the workflow's declared inputs under the Start Node's own
            state key; missing required ones raise rather than default.

    Returns:
        The final GraphState after invocation (node key -> output dict).
    """
    source = fixture if isinstance(fixture, Path) else FIXTURES_DIR / fixture
    translate(source, output_dir / _PKG)

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


class TestGeneratedEnvModule:
    """Secret resolution, exercised through a real import.

    Not via ``exec`` of the source: ``find_dotenv`` locates the file by walking
    the call stack, so an ``exec``'d copy searches from the *test* file and finds
    the repository's own ``.env`` instead of the package's.
    """

    def _generate(self, tmp_path: Path) -> None:
        """Generate the env fixture as an importable package under tmp_path."""
        translate(FIXTURES_DIR / "env_sys_workflow.yml", tmp_path / _PKG)

    def _read_secret(self, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
        """Import the generated package and print `env.SECRET`.

        Args:
            tmp_path: Directory holding the generated package.
            **env: Environment overrides for the child. ``SECRET`` is removed
                from the inherited environment first so a developer's own shell
                cannot satisfy the test.

        Returns:
            The completed child process.
        """
        child_env = {k: v for k, v in os.environ.items() if k != "SECRET"}
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env.update(env)
        return subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, '.')\n"
             f"from {_PKG} import env\nprint(env.SECRET)"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )

    def test_a_missing_secret_raises_with_the_variable_named(self, tmp_path):
        """Returning "" would surface later as an unexplained downstream error."""
        self._generate(tmp_path)

        proc = self._read_secret(tmp_path)

        assert proc.returncode != 0
        assert "SECRET" in proc.stderr
        assert "RuntimeError" in proc.stderr

    def test_a_secret_comes_from_the_environment(self, tmp_path):
        """Exported in the shell, it resolves to that value."""
        self._generate(tmp_path)

        proc = self._read_secret(tmp_path, SECRET="from-environment")

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "from-environment"

    def test_a_secret_can_come_from_a_dotenv_file(self, tmp_path):
        """USAGE tells the customer to put credentials in `.env`; it has to work.

        It used to work only by accident: ``llm.py`` also calls ``load_dotenv``,
        so a secret in ``.env`` resolved if and only if that module happened to be
        imported before the first ``env.SECRET`` read -- the same ``.env`` and the
        same workflow succeeded or failed depending on import order.
        """
        self._generate(tmp_path)
        (tmp_path / ".env").write_text("SECRET=from-dotenv\n", encoding="utf-8")

        proc = self._read_secret(tmp_path)

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "from-dotenv"

    def test_an_exported_variable_wins_over_the_dotenv_file(self, tmp_path):
        """`load_dotenv` must not override what the process already has set."""
        self._generate(tmp_path)
        (tmp_path / ".env").write_text("SECRET=from-dotenv\n", encoding="utf-8")

        proc = self._read_secret(tmp_path, SECRET="from-environment")

        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "from-environment"


class TestEnvImportIsNotGuessedFromText:
    """`from .. import env` is decided from the DSL, not from the generated text.

    The decision used to be "does any generated line contain the substring
    ``env.``", which any workflow could trip by accident.
    """

    def test_a_default_that_merely_mentions_env_still_imports(self, tmp_path):
        """A URL like `https://env.example.com/` is data, not a reference.

        Sniffing for the substring emitted ``from .. import env`` for a package
        where ``env.py`` was never generated, so *nothing* in it could be
        imported -- and Python blamed a circular import, pointing at the wrong
        file entirely.
        """
        dsl = yaml.safe_load(
            (FIXTURES_DIR / "simple_workflow.yml").read_text(encoding="utf-8")
        )
        for node in dsl["workflow"]["graph"]["nodes"]:
            if node["data"].get("type") == "start":
                node["data"]["variables"][0]["default"] = "https://env.example.com/x"
                node["data"]["variables"][0]["required"] = False
        fixture = tmp_path / "spurious.yml"
        fixture.write_text(yaml.dump(dsl), encoding="utf-8")

        translate(fixture, tmp_path / _PKG)
        assert not (tmp_path / _PKG / "env.py").exists()
        source = (tmp_path / _PKG / "nodes" / "start_node.py").read_text(encoding="utf-8")
        assert "import env" not in source

        proc = _run_python(["-m", _PKG], tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "env.example.com" in proc.stdout  # the default still reaches state


def _fixture_variant(tmp_path: Path, fixture: str, mutate) -> Path:
    """A fixture with `mutate` applied to its parsed DSL, written to tmp_path.

    Args:
        tmp_path: Where to write the variant.
        fixture: Fixture filename under tests/fixtures/.
        mutate: Callable taking the parsed DSL dict and editing it in place.

    Returns:
        Path to the written YAML.
    """
    dsl = yaml.safe_load((FIXTURES_DIR / fixture).read_text(encoding="utf-8"))
    mutate(dsl)
    path = tmp_path / "variant.yml"
    path.write_text(yaml.dump(dsl, allow_unicode=True), encoding="utf-8")
    return path


class TestSysInputsAreRequiredByName:
    """`sys.*` is caller-supplied, so omitting it must say which field is missing."""

    def test_the_entry_point_example_supplies_sys(self, tmp_path):
        """`python -m <pkg>` has to run out of the box on a sys-using workflow.

        Without a `sys` entry in the generated example the command died with
        `KeyError: 'sys'` -- the first thing a user tries, broken.
        """
        translate(FIXTURES_DIR / "env_sys_workflow.yml", tmp_path / _PKG)

        proc = _run_python(["-m", _PKG], tmp_path)

        assert proc.returncode == 0, proc.stderr
        assert '"sys"' in (tmp_path / _PKG / "__main__.py").read_text(encoding="utf-8")

    def test_omitting_sys_names_the_missing_field(self, tmp_path):
        """A bare `KeyError: 'sys'` named neither the field nor who supplies it."""
        translate(FIXTURES_DIR / "env_sys_workflow.yml", tmp_path / _PKG)

        snippet = _RUN_SNIPPET.format(
            initial=repr({"node_1785682240366": {"query": "q", "topk": 3}})
        )
        proc = _run_python(["-c", snippet], tmp_path)

        assert proc.returncode != 0
        assert "missing required sys input(s)" in proc.stderr
        assert "app_id" in proc.stderr

    def test_numeric_sys_fields_are_not_typed_as_strings(self, tmp_path):
        """`dialogue_count` and `timestamp` are numbers in Dify.

        Defaulting an unknown field to `str` annotated them wrongly and put
        `"dialogue_count": "example"` into the generated entry point.
        """

        def add_numeric_sys(dsl: dict) -> None:
            for node in dsl["workflow"]["graph"]["nodes"]:
                if node["data"].get("type") == "end":
                    node["data"]["outputs"] += [
                        {
                            "value_selector": ["sys", "dialogue_count"],
                            "value_type": "number",
                            "variable": "turns",
                        },
                        {
                            "value_selector": ["sys", "timestamp"],
                            "value_type": "number",
                            "variable": "at",
                        },
                    ]
                    break

        fixture = _fixture_variant(tmp_path, "env_sys_workflow.yml", add_numeric_sys)
        translate(fixture, tmp_path / _PKG)

        state = (tmp_path / _PKG / "state.py").read_text(encoding="utf-8")
        main = (tmp_path / _PKG / "__main__.py").read_text(encoding="utf-8")

        assert "dialogue_count: int" in state
        assert "timestamp: int" in state
        assert '"dialogue_count": 0' in main
        assert '"dialogue_count": "example"' not in main


class TestEnvConstantsReachABody:
    """The only path where a node body actually reads `env.*`.

    No committed fixture exercises it: the env references in `env_sys_workflow`
    land in a prompt and an if-else condition, both of which reach comments rather
    than code. So the `from .. import env` decision had no test at all.
    """

    def test_an_end_output_selecting_env_imports_and_resolves_it(self, tmp_path):
        """A deterministic body reading a constant gets the import, and runs."""

        def forward_env(dsl: dict) -> None:
            for node in dsl["workflow"]["graph"]["nodes"]:
                if node["data"].get("type") == "end":
                    node["data"]["outputs"].append({
                        "value_selector": ["env", "API_BASE"],
                        "value_type": "string",
                        "variable": "base",
                    })
                    break

        fixture = _fixture_variant(tmp_path, "env_sys_workflow.yml", forward_env)
        translate(fixture, tmp_path / _PKG)

        body = (tmp_path / _PKG / "nodes" / "node_1785682317200.py").read_text(
            encoding="utf-8"
        )
        assert "from .. import env" in body
        assert '"base": env.API_BASE' in body

        snippet = _RUN_SNIPPET.format(
            initial=repr({
                "node_1785682240366": {"query": "q", "topk": 3},
                "sys": {"app_id": "APP-1", "user_id": "U-9"},
            })
        )
        proc = _run_python(["-c", snippet], tmp_path)
        assert proc.returncode == 0, proc.stderr
        assert "https://example.com" in proc.stdout

    def test_a_reference_to_a_deleted_variable_stays_out_of_the_body(self, tmp_path):
        """Dify does not scrub selectors when the author deletes the variable.

        Emitting `env.GONE` as code turned a stale reference into an
        AttributeError at run time; a placeholder is visibly a placeholder.
        """

        def strip_declarations(dsl: dict) -> None:
            for node in dsl["workflow"]["graph"]["nodes"]:
                if node["data"].get("type") == "end":
                    node["data"]["outputs"].append({
                        "value_selector": ["env", "API_BASE"],
                        "value_type": "string",
                        "variable": "base",
                    })
                    break
            dsl["workflow"]["environment_variables"] = []

        fixture = _fixture_variant(tmp_path, "env_sys_workflow.yml", strip_declarations)
        translate(fixture, tmp_path / _PKG)

        assert not (tmp_path / _PKG / "env.py").exists()
        body = (tmp_path / _PKG / "nodes" / "node_1785682317200.py").read_text(
            encoding="utf-8"
        )
        assert "import env" not in body
        # The reference still appears in the comment block -- that is where a
        # developer is told what the DSL asked for, and generation logs a warning
        # naming it. What must not happen is it becoming executable.
        assert '"base": env.API_BASE' not in body

        snippet = _RUN_SNIPPET.format(
            initial=repr({
                "node_1785682240366": {"query": "q", "topk": 3},
                "sys": {"app_id": "APP-1", "user_id": "U-9"},
            })
        )
        proc = _run_python(["-c", snippet], tmp_path)
        assert proc.returncode == 0, proc.stderr


class TestNestedStructuredOutput:
    """A selector through structured_output has to resolve at any depth."""

    def test_a_nested_selector_resolves(self, tmp_path):
        """Shaping only the top level left the identical KeyError one level down."""

        def nest_schema(dsl: dict) -> None:
            for node in dsl["workflow"]["graph"]["nodes"]:
                if node["data"].get("structured_output_enabled"):
                    schema = node["data"]["structured_output"]["schema"]
                    schema["properties"]["addr"] = {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                    }
                elif node["data"].get("type") == "end":
                    node["data"]["outputs"].append({
                        "value_selector": [
                            "1785682272592",
                            "structured_output",
                            "addr",
                            "city",
                        ],
                        "value_type": "string",
                        "variable": "city",
                    })

        fixture = _fixture_variant(tmp_path, "env_sys_workflow.yml", nest_schema)
        state = _generate_and_run(
            tmp_path,
            fixture,
            {
                "node_1785682240366": {"query": "q", "topk": 3},
                "sys": {"app_id": "APP-1", "user_id": "U-9"},
            },
        )

        assert state["node_1785682317200"]["city"] == "placeholder"


class TestUnusableEnvVariableNamesAreRejected:
    """A DSL name goes into a Python assignment target, so it cannot be trusted.

    Dify's only rule is `/^\\w+$/` not starting with a digit, which admits every
    Python keyword and every name the generated module defines itself.
    """

    def _with_env_vars(self, tmp_path: Path, variables: list[dict]) -> Path:
        """Generate the env fixture with `environment_variables` replaced."""

        def replace(dsl: dict) -> None:
            dsl["workflow"]["environment_variables"] = variables

        fixture = _fixture_variant(tmp_path, "env_sys_workflow.yml", replace)
        translate(fixture, tmp_path / _PKG)
        return tmp_path / _PKG

    def test_a_keyword_name_does_not_break_the_package(self, tmp_path):
        """`class = 'x'` is a SyntaxError -- the whole package stops importing."""
        pkg = self._with_env_vars(tmp_path, [
            {"id": "1", "name": "class", "value": "x", "value_type": "string"},
            {"id": "2", "name": "API_BASE", "value": "https://ok", "value_type": "string"},
        ])

        source = (pkg / "env.py").read_text(encoding="utf-8")
        assert "class = " not in source
        assert "API_BASE = 'https://ok'" in source
        proc = _run_python(["-c", f"import sys; sys.path.insert(0, '.'); import {_PKG}.env"],
                           tmp_path)
        assert proc.returncode == 0, proc.stderr

    def test_a_name_the_module_already_uses_is_not_emitted(self, tmp_path):
        """`os = 'x'` after `import os` compiles, then breaks every secret read."""
        pkg = self._with_env_vars(tmp_path, [
            {"id": "1", "name": "os", "value": "x", "value_type": "string"},
            {"id": "2", "name": "TOKEN", "value": "plaintext", "value_type": "secret"},
        ])

        assert "\nos = " not in (pkg / "env.py").read_text(encoding="utf-8")
        proc = _run_python(
            ["-c", "import sys; sys.path.insert(0, '.')\n"
                   f"from {_PKG} import env\nprint(env.TOKEN)"],
            tmp_path,
        )
        # Reading an unset secret must still fail *as a missing secret*. With `os`
        # shadowed by a string constant the same read died with
        # "'str' object has no attribute 'environ'" instead.
        assert proc.returncode != 0
        assert "RuntimeError" in proc.stderr and "TOKEN" in proc.stderr
        assert "'str' object has no attribute" not in proc.stderr

    def test_a_non_secret_with_no_value_does_not_abort_the_translation(self, tmp_path):
        """It used to raise a bare `KeyError: 'value'` and generate nothing."""
        pkg = self._with_env_vars(tmp_path, [
            {"id": "1", "name": "FOO", "value_type": "string"},
            {"id": "2", "name": "API_BASE", "value": "https://ok", "value_type": "string"},
        ])

        source = (pkg / "env.py").read_text(encoding="utf-8")
        assert "FOO" not in source
        assert "API_BASE = 'https://ok'" in source


class TestTerminalNodes:
    """Which nodes reach `END`, and what the graph module imports."""

    def test_an_iteration_s_inner_leaf_does_not_terminate_the_workflow(self, tmp_path):
        """Its body's last step has no outgoing edge, so on shape alone it looks
        terminal -- and wiring it to END says the workflow ends when one pass does.

        `json_translate.yml` contains exactly that node (`合并`, isInIteration).
        """
        translate(FIXTURES_DIR / "json_translate.yml", tmp_path / _PKG)

        graph = (tmp_path / _PKG / "graph.py").read_text(encoding="utf-8")

        assert 'graph.add_edge("node_1731659778623", END)' not in graph
        assert 'graph.add_edge("node_1731659992069", END)' in graph

    def test_a_graph_with_no_terminal_does_not_import_END(self, tmp_path):
        """An unused import is a lint failure in the generated package."""

        def bury_the_end(dsl: dict) -> None:
            for node in dsl["workflow"]["graph"]["nodes"]:
                if node["data"].get("type") == "end":
                    node["data"]["isInIteration"] = True

        fixture = _fixture_variant(tmp_path, "simple_workflow.yml", bury_the_end)
        translate(fixture, tmp_path / _PKG)

        graph = (tmp_path / _PKG / "graph.py").read_text(encoding="utf-8")
        assert "END" not in graph
        proc = _run_python(["-m", "ruff", "check", str(tmp_path / _PKG)], tmp_path)
        assert proc.returncode == 0, proc.stdout + proc.stderr
