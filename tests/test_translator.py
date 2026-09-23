"""Tests for the translator module."""

import ast
import subprocess
import tempfile
from pathlib import Path

import pytest

from dify2langgraph.cli import translate
from dify2langgraph.codegen import (
    generate_graph_file,
    generate_nodes_directory,
    generate_state_file,
    sanitize_function_name,
)
from dify2langgraph.parser import DifyDSLParser

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSanitizeFunctionName:
    """Tests for function name sanitization."""

    def test_simple_name(self):
        """Test that simple names pass through."""
        assert sanitize_function_name("start_node") == "start_node"

    def test_hyphen_to_underscore(self):
        """Test that hyphens are converted to underscores."""
        assert sanitize_function_name("if-else") == "if_else"

    def test_space_to_underscore(self):
        """Test that spaces are converted to underscores."""
        assert sanitize_function_name("my node") == "my_node"

    def test_numeric_prefix(self):
        """Test that numeric prefixes get 'node_' added."""
        assert sanitize_function_name("1722391426202") == "node_1722391426202"

    def test_already_valid(self):
        """Test that valid names are unchanged."""
        assert sanitize_function_name("llm_node") == "llm_node"


class TestGenerateStateFile:
    """Tests for state.py generation."""

    def test_generates_state_file(self):
        """Test that state.py is generated with correct content."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_state_file(graph, output_dir)

            state_file = output_dir / "state.py"
            assert state_file.exists()

            content = state_file.read_text(encoding="utf-8")
            assert "class GraphState(TypedDict, total=False):" in content
            assert "start_node:" in content
            assert "llm_node:" in content
            assert "end_node:" in content


class TestGenerateNodesDirectory:
    """Tests for nodes/ directory generation."""

    def test_generates_nodes_directory(self):
        """Test that nodes/ directory is generated with individual files."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_nodes_directory(graph, output_dir)

            nodes_dir = output_dir / "nodes"
            assert nodes_dir.exists()
            assert (nodes_dir / "__init__.py").exists()
            assert (nodes_dir / "start_node.py").exists()
            assert (nodes_dir / "llm_node.py").exists()
            assert (nodes_dir / "end_node.py").exists()

    def test_node_file_content(self):
        """Test that individual node files have correct content."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_nodes_directory(graph, output_dir)

            llm_content = (output_dir / "nodes" / "llm_node.py").read_text(encoding="utf-8")
            assert "def llm_node(state: GraphState)" in llm_content
            assert "start_node.query" in llm_content

    def test_init_exports_all_nodes(self):
        """Test that __init__.py exports all node functions."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_nodes_directory(graph, output_dir)

            init_content = (output_dir / "nodes" / "__init__.py").read_text(encoding="utf-8")
            assert "from .start_node import start_node" in init_content
            assert "from .llm_node import llm_node" in init_content
            assert "from .end_node import end_node" in init_content

    def test_numeric_node_id_prefixed(self):
        """Test that numeric node IDs get proper function names."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "guardduty_handler.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_nodes_directory(graph, output_dir)

            # Numeric ID should be prefixed with node_
            assert (output_dir / "nodes" / "node_1722391426202.py").exists()


class TestGenerateGraphFile:
    """Tests for graph.py generation."""

    def test_generates_graph_file(self):
        """Test that graph.py is generated with correct structure."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_graph_file(graph, output_dir)

            graph_file = output_dir / "graph.py"
            assert graph_file.exists()

            content = graph_file.read_text(encoding="utf-8")
            assert "from langgraph.graph import END, START, StateGraph" in content
            assert "def build_graph()" in content
            assert "graph = StateGraph(GraphState)" in content
            assert 'graph.add_node("start_node"' in content
            assert "graph.add_edge(START," in content

    def test_branching_node_uses_conditional_edges(self):
        """A question-classifier is wired with a router + add_conditional_edges (ADR-0003)."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "guardduty_handler.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_graph_file(graph, output_dir)

            content = (output_dir / "graph.py").read_text(encoding="utf-8")
            # A router function reads the classifier's decision field.
            assert "def route_node_1722397570856(state: GraphState) -> str:" in content
            assert 'return state["node_1722397570856"]["class_id"]' in content
            # The branch is wired conditionally, mapping each sourceHandle to a target.
            assert (
                'graph.add_conditional_edges("node_1722397570856", '
                "route_node_1722397570856, " in content
            )
            assert "'1': 'node_1722397470145'" in content
            assert "'1722398080959': 'node_1722399356175'" in content
            # The branch targets must NOT also be reached via a plain fan-out edge.
            assert 'graph.add_edge("node_1722397570856"' not in content

    def test_if_else_uses_selected_branch_router(self):
        """An if-else routes on selected_branch with true/false handles (ADR-0003)."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "ifelse_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_graph_file(graph, output_dir)

            content = (output_dir / "graph.py").read_text(encoding="utf-8")
            assert "def route_ifelse_node(state: GraphState) -> str:" in content
            assert 'return state["ifelse_node"]["selected_branch"]' in content
            assert (
                'graph.add_conditional_edges("ifelse_node", route_ifelse_node, '
                in content
            )
            assert "'true': 'end_true'" in content
            assert "'false': 'end_false'" in content
            assert 'graph.add_edge("ifelse_node"' not in content


class TestTranslate:
    """Integration tests for the translate function."""

    def test_translate_simple_workflow(self):
        """Test translating a simple workflow generates all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            input_file = FIXTURES_DIR / "simple_workflow.yml"

            translate(input_file, output_dir)

            assert (output_dir / "state.py").exists()
            assert (output_dir / "nodes" / "__init__.py").exists()
            assert (output_dir / "graph.py").exists()

    def test_translate_guardduty_workflow(self):
        """Test translating a more complex workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            input_file = FIXTURES_DIR / "guardduty_handler.yml"

            translate(input_file, output_dir)

            # Check all files generated
            assert (output_dir / "state.py").exists()
            assert (output_dir / "nodes" / "__init__.py").exists()
            assert (output_dir / "graph.py").exists()

            # Check state has all nodes
            state_content = (output_dir / "state.py").read_text(encoding="utf-8")
            assert "1722391426202:" in state_content  # start node
            assert "1722399235845:" in state_content  # end node

    def test_generated_state_is_valid_python(self):
        """Test that generated state.py is valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            # Try to compile the generated file
            state_content = (output_dir / "state.py").read_text(encoding="utf-8")
            compile(state_content, "state.py", "exec")

    def test_generated_node_files_are_valid_python(self):
        """Test that generated node files are valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            # Check each node file compiles
            for node_file in (output_dir / "nodes").glob("*.py"):
                content = node_file.read_text(encoding="utf-8")
                compile(content, node_file.name, "exec")

    def test_generated_graph_is_valid_python(self):
        """Test that generated graph.py is valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            graph_content = (output_dir / "graph.py").read_text(encoding="utf-8")
            compile(graph_content, "graph.py", "exec")


class TestSelfContainedPackage:
    """The generated output is a package with relative imports (ADR-0007)."""

    def test_emits_package_files(self):
        """__init__.py and __main__.py are generated for the output package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            init_content = (output_dir / "__init__.py").read_text(encoding="utf-8")
            assert "from .graph import build_graph" in init_content

            main_content = (output_dir / "__main__.py").read_text(encoding="utf-8")
            assert "from .graph import build_graph" in main_content
            assert "workflow.invoke(initial_state)" in main_content

    def test_graph_uses_relative_imports(self):
        """graph.py imports state/nodes as siblings, not top-level modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            content = (output_dir / "graph.py").read_text(encoding="utf-8")
            assert "from .state import GraphState" in content
            assert "from .nodes import " in content
            # No standalone-run demo (moved to __main__.py).
            assert 'if __name__ == "__main__"' not in content

    def test_node_files_use_relative_imports_without_sys_path(self):
        """Node files import the parent package's state, no sys.path hack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            content = (output_dir / "nodes" / "llm_node.py").read_text(encoding="utf-8")
            assert "from ..state import GraphState" in content
            assert "sys.path" not in content

    def test_retriever_template_and_knowledge_node_wiring(self):
        """retriever.py is bundled and a knowledge-retrieval node calls the port."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "guardduty_handler.yml", output_dir)

            assert (output_dir / "retriever.py").exists()

            kr = (output_dir / "nodes" / "node_1722397470145.py").read_text(encoding="utf-8")
            assert "from ..retriever import get_retriever" in kr
            assert "get_retriever().retrieve(" in kr


class TestStartNodeInputContract:
    """Where a workflow's inputs live is fixed by the generator, not guessed."""

    def test_start_body_reads_the_callers_slot(self):
        """ADR-0002 address, emitted deterministically rather than left to an LLM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "start_node.py").read_text(encoding="utf-8")

            assert 'supplied = state.get("start_node", {})' in body
            assert 'supplied["query"]' in body
            # No TODO marker: the LLM pass skips it, so it cannot invent an address.
            assert "TODO: Implement" not in body

    def test_main_supplies_the_declared_inputs(self):
        """`python -m <pkg>` must still run, so the example carries real inputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "guardduty_handler.yml", output_dir)

            main = (output_dir / "__main__.py").read_text(encoding="utf-8")

            assert '"finding": "example"' in main
            assert '"severity": 0.0' in main  # number, not a string

    def _generate_with_start_variables(self, tmpdir: str, variables: list[dict]) -> str:
        """Generate from simple_workflow with the Start Node's variables replaced."""
        import yaml

        dsl = yaml.safe_load((FIXTURES_DIR / "simple_workflow.yml").read_text(encoding="utf-8"))
        for node in dsl["workflow"]["graph"]["nodes"]:
            if node["data"].get("type") == "start":
                node["data"]["variables"] = variables

        source = Path(tmpdir) / "custom.yml"
        source.write_text(yaml.dump(dsl), encoding="utf-8")
        output_dir = Path(tmpdir) / "out"
        translate(source, output_dir)
        return (output_dir / "nodes" / "start_node.py").read_text(encoding="utf-8")

    def test_dsl_default_is_honoured(self):
        """A default set in Dify must survive into the generated fallback.

        Falling back to "" instead would make the generated package behave
        differently from the workflow it was converted from, silently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            body = self._generate_with_start_variables(
                tmpdir,
                [{"variable": "lang", "type": "text-input", "required": False, "default": "en"}],
            )

            assert "supplied.get(\"lang\", 'en')" in body

    def test_a_default_makes_a_required_variable_satisfiable(self):
        """Required + default is not "missing": there is already a value to use."""
        with tempfile.TemporaryDirectory() as tmpdir:
            body = self._generate_with_start_variables(
                tmpdir,
                [
                    {"variable": "query", "type": "text-input", "required": True},
                    {"variable": "topk", "type": "number", "required": True, "default": 5},
                ],
            )

            assert 'missing = [name for name in ("query",)' in body
            assert "topk" not in body.split("missing = ")[1].split("]")[0]
            # Coerced: the field is typed float, and Dify exports a number's
            # default as a string.
            assert 'supplied.get("topk", 5.0)' in body

    def test_optional_inputs_get_defaults(self):
        """Only required variables are enforced; optional ones fall back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "translation_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "node_1721117927142.py").read_text(encoding="utf-8")

            assert 'supplied["source_text"]' in body  # required
            assert 'supplied.get("country", "")' in body  # required: false


class TestRealDslEnvSysWorkflow:
    """Shapes pinned down by env_sys_workflow.yml, built in Dify Cloud.

    Every assertion here failed against the real export before this fixture
    existed -- the hand-written fixtures happened to avoid all of them.
    """

    def test_empty_string_default_does_not_disable_the_required_check(self):
        """Dify writes `default: ''` where no default was set.

        Reading that as a default silently dropped the required-input check for
        every real export: `query` is `required: true` and carries `default: ''`,
        so the generated body had no `missing` list at all.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "node_1785682240366.py").read_text(encoding="utf-8")

            assert 'missing = [name for name in ("query",)' in body
            assert 'supplied["query"]' in body

    def test_number_default_is_coerced_to_the_declared_type(self):
        """`topk` is `type: number` but its default exports as the string '3'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "node_1785682240366.py").read_text(encoding="utf-8")

            assert 'supplied.get("topk", 3.0)' in body

    def test_structured_output_is_declared_and_shaped(self):
        """A downstream read of structured_output used to raise KeyError.

        The End node forwards `[<llm>, "structured_output", "random_number"]`, but
        the LLM handler declared only text/usage, so the generated package crashed
        at run time on any workflow using structured output.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            state = (output_dir / "state.py").read_text(encoding="utf-8")
            body = (output_dir / "nodes" / "node_1785682272592.py").read_text(encoding="utf-8")

            assert "structured_output: dict[str, Any]" in state
            # Shaped from the DSL's own schema, so a downstream read resolves.
            assert '"answer": "placeholder"' in body
            assert '"random_number": 0.0' in body

    def test_sys_selector_resolves_to_the_reserved_key(self):
        """`[sys, app_id]` reaches `state["sys"]["app_id"]` (ADR-0004)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "node_1785682317200.py").read_text(encoding="utf-8")

            assert '"app_id": state["sys"]["app_id"]' in body

    def test_only_referenced_sys_fields_are_declared(self):
        """The sys catalogue is mode-dependent, so the DSL decides what exists.

        `sys.query` is chatflow-only while `sys.app_id` appears in workflow mode --
        a fixed list would be wrong for one of them.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            workflow_dir = Path(tmpdir) / "wf"
            chat_dir = Path(tmpdir) / "chat"
            translate(FIXTURES_DIR / "env_sys_workflow.yml", workflow_dir)
            translate(FIXTURES_DIR / "chatflow_sys_query.yml", chat_dir)

            wf_state = (workflow_dir / "state.py").read_text(encoding="utf-8")
            chat_state = (chat_dir / "state.py").read_text(encoding="utf-8")

            def sys_block(state_source: str) -> str:
                """The SysInputs body only -- a Start variable may share a name."""
                return state_source.split("class SysInputs")[1].split("class ")[0]

            wf_sys = sys_block(wf_state)
            chat_sys = sys_block(chat_state)

            assert "app_id: str" in wf_sys and "user_id: str" in wf_sys
            assert "query" not in wf_sys
            # files is a list of uploads, not an id.
            assert "query: str" in chat_sys and "files: list[Any]" in chat_sys
            assert "app_id" not in chat_sys

    def test_env_is_not_in_state(self):
        """`env` is constants outside state, so GraphState must not carry it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            state = (output_dir / "state.py").read_text(encoding="utf-8")

            assert "env:" not in state

    def test_env_reference_points_at_the_constants_module(self):
        """Not `state["env"][...]`, which nothing can resolve.

        The generated comments and NODE_CONFIG block are what the LLM
        body-generation pass reads, so an address that cannot resolve there
        teaches the model to write code that fails.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            body = (output_dir / "nodes" / "node_1785682272592.py").read_text(encoding="utf-8")

            assert "# env.API_BASE -> env.API_BASE" in body
            assert 'state["env"]' not in body


class TestEnvConstantsModule:
    """env.py: DSL constants, with secrets deliberately left out (ADR-0004)."""

    def _generate(self, tmpdir: str) -> str:
        """Generate the env fixture and return env.py's source."""
        output_dir = Path(tmpdir)
        translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)
        return (output_dir / "env.py").read_text(encoding="utf-8")

    def test_non_secret_values_become_typed_constants(self):
        """An integer stays an integer; a string stays a string."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source = self._generate(tmpdir)

            assert "API_BASE = 'https://example.com'" in source
            assert "MAX_RETRY = 2" in source

    def test_a_secret_value_is_never_written_into_source(self):
        """Dify exports a secret's value in plaintext; it must not land here.

        The fixture's secret is `DUMMY`, so its presence in the generated module
        would mean a real deployment writes a real credential into a file the
        customer commits.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            source = self._generate(tmpdir)

            assert "DUMMY" not in source
            assert "SECRET" in source  # declared, just not valued

    def test_a_missing_secret_raises_with_the_variable_named(self):
        """Returning "" would surface later as an unexplained downstream error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            namespace: dict = {}
            exec(  # noqa: S102 - executing our own generated module, by design
                (output_dir / "env.py").read_text(encoding="utf-8"), namespace
            )
            getattr_ = namespace["__getattr__"]

            with pytest.raises(RuntimeError, match="SECRET"):
                getattr_("SECRET")

    def test_a_present_secret_comes_from_the_environment(self, monkeypatch):
        """Set in the environment, it resolves to that value."""
        monkeypatch.setenv("SECRET", "from-environment")
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "env_sys_workflow.yml", output_dir)

            namespace: dict = {}
            exec(  # noqa: S102
                (output_dir / "env.py").read_text(encoding="utf-8"), namespace
            )

            assert namespace["__getattr__"]("SECRET") == "from-environment"

    def test_no_env_file_when_the_dsl_declares_none(self):
        """Most workflows declare no environment variables at all."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            assert not (output_dir / "env.py").exists()


class TestChatflowShape:
    """A chatflow ends on an `answer` node and declares no `end` node at all."""

    def test_answer_node_terminates_the_graph(self):
        """Keying END off `end` nodes left the terminal dangling.

        It also left `END` imported but unused, which ruff flags in the generated
        package.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "chatflow_sys_query.yml", output_dir)

            graph = (output_dir / "graph.py").read_text(encoding="utf-8")

            assert 'graph.add_edge("answer", END)' in graph
            assert "import END" in graph or "END, START" in graph

    def test_node_all_is_sorted(self):
        """ruff's RUF022 flags an unsorted __all__ in the generated package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "chatflow_sys_query.yml", output_dir)

            init = (output_dir / "nodes" / "__init__.py").read_text(encoding="utf-8")
            names = [
                line.strip().strip('",')
                for line in init.split("__all__ = [")[1].split("]")[0].splitlines()
                if line.strip()
            ]

            assert names == sorted(names)

    def test_start_with_no_variables_is_a_passthrough(self):
        """In a chatflow the user's input is sys.query, not a Start variable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "chatflow_sys_query.yml", output_dir)

            body = (output_dir / "nodes" / "node_1790170151582.py").read_text(encoding="utf-8")

            assert 'supplied.get("inputs", {})' in body
            assert "missing" not in body


class TestGeneratedOutputIsByteStableAcrossPlatforms:
    """The same DSL must produce the same bytes wherever the converter runs."""

    def test_copied_templates_are_normalised_to_lf(self):
        """A CRLF template must not reach the output (ADR-0001).

        llm.py and retriever.py are copied into every generated package. A byte
        copy would carry whatever the checkout has, and Git for Windows defaults
        to core.autocrlf=true -- so a plain clone there would produce CRLF output
        while the container produced LF, and the two would stop being
        byte-identical. Unlike the assertion below, this one bites on any OS.
        """
        from dify2langgraph import cli

        with tempfile.TemporaryDirectory() as tmpdir:
            crlf_templates = Path(tmpdir) / "templates"
            crlf_templates.mkdir()
            for template in cli.TEMPLATES_DIR.glob("*.py"):
                crlf_templates.joinpath(template.name).write_bytes(
                    template.read_bytes().replace(b"\n", b"\r\n")
                )

            output_dir = Path(tmpdir) / "out"
            output_dir.mkdir()
            original = cli.TEMPLATES_DIR
            cli.TEMPLATES_DIR = crlf_templates
            try:
                cli.copy_templates(output_dir)
            finally:
                cli.TEMPLATES_DIR = original

            copied = sorted(output_dir.glob("*.py"))
            assert copied, "no templates were copied"
            crlf = [p.name for p in copied if b"\r\n" in p.read_bytes()]
            assert not crlf, f"CRLF survived the copy: {crlf}"

    def test_every_generated_write_pins_the_newline(self):
        """No write of generated content may take Python's default newline.

        Text mode rewrites "\n" to os.linesep, so an unpinned write emits CRLF on
        Windows and LF everywhere else. That is invisible to the assertion below
        when the suite runs on macOS or Linux, which is most of the time -- so
        check the calls themselves rather than only their output.
        """
        package = Path(__file__).resolve().parents[1] / "src" / "dify2langgraph"
        offenders = []
        for module in sorted(package.rglob("*.py")):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "write_text"
                    and not any(kw.arg == "newline" for kw in node.keywords)
                ):
                    offenders.append(f"{module.relative_to(package)}:{node.lineno}")

        assert not offenders, "write_text without newline=: " + ", ".join(offenders)

    def test_generated_files_use_lf_line_endings(self):
        """No CRLF in any generated file, on any host OS (ADR-0001).

        Python's text mode rewrites "\n" to ``os.linesep`` unless ``newline`` is
        pinned, so a native Windows run would emit CRLF while the container
        (Linux) emits LF. That would make the output byte-different depending on
        how the user happened to run the converter, and would churn the whole
        file in git when they switch between the two documented paths.

        This assertion is trivially true on macOS/Linux and is the one that
        actually bites on Windows -- which is the point of keeping it.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "guardduty_handler.yml", output_dir)

            generated = sorted(output_dir.rglob("*.py"))
            assert generated, "fixture produced no files"

            crlf = [p.name for p in generated if b"\r\n" in p.read_bytes()]
            assert not crlf, f"CRLF line endings in: {crlf}"


class TestGeneratedCodeIsLintClean:
    """Generated packages must pass ruff with no project configuration.

    A generated package ships without a pyproject.toml, so whoever lints it --
    including the CLI's own `--lint` flag -- gets ruff's defaults, notably an
    88-character line length. Import ordering and line wrapping in the generators
    are therefore load-bearing, and `--isolated` is what reproduces that.
    """

    def test_all_fixtures_generate_ruff_clean_packages(self, fixtures_dir: Path) -> None:
        workflows = sorted(fixtures_dir.glob("*.yml"))
        assert workflows, "no workflow fixtures found"

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for workflow in workflows:
                translate(workflow, out / workflow.stem)

            result = subprocess.run(
                ["ruff", "check", "--isolated", "--output-format", "concise", str(out)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        assert result.returncode == 0, f"ruff findings:\n{result.stdout}{result.stderr}"
