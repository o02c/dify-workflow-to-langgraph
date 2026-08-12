"""Tests for the translator module."""

import tempfile
from pathlib import Path

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

            content = state_file.read_text()
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

            llm_content = (output_dir / "nodes" / "llm_node.py").read_text()
            assert "def llm_node(state: GraphState)" in llm_content
            assert "start_node.query" in llm_content

    def test_init_exports_all_nodes(self):
        """Test that __init__.py exports all node functions."""
        parser = DifyDSLParser()
        graph = parser.parse_file(FIXTURES_DIR / "simple_workflow.yml")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            generate_nodes_directory(graph, output_dir)

            init_content = (output_dir / "nodes" / "__init__.py").read_text()
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

            content = graph_file.read_text()
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

            content = (output_dir / "graph.py").read_text()
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

            content = (output_dir / "graph.py").read_text()
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
            state_content = (output_dir / "state.py").read_text()
            assert "1722391426202:" in state_content  # start node
            assert "1722399235845:" in state_content  # end node

    def test_generated_state_is_valid_python(self):
        """Test that generated state.py is valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            # Try to compile the generated file
            state_content = (output_dir / "state.py").read_text()
            compile(state_content, "state.py", "exec")

    def test_generated_node_files_are_valid_python(self):
        """Test that generated node files are valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            # Check each node file compiles
            for node_file in (output_dir / "nodes").glob("*.py"):
                content = node_file.read_text()
                compile(content, node_file.name, "exec")

    def test_generated_graph_is_valid_python(self):
        """Test that generated graph.py is valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            graph_content = (output_dir / "graph.py").read_text()
            compile(graph_content, "graph.py", "exec")


class TestSelfContainedPackage:
    """The generated output is a package with relative imports (ADR-0007)."""

    def test_emits_package_files(self):
        """__init__.py and __main__.py are generated for the output package."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            init_content = (output_dir / "__init__.py").read_text()
            assert "from .graph import build_graph" in init_content

            main_content = (output_dir / "__main__.py").read_text()
            assert "from .graph import build_graph" in main_content
            assert "workflow.invoke(initial_state)" in main_content

    def test_graph_uses_relative_imports(self):
        """graph.py imports state/nodes as siblings, not top-level modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            content = (output_dir / "graph.py").read_text()
            assert "from .state import GraphState" in content
            assert "from .nodes import " in content
            # No standalone-run demo (moved to __main__.py).
            assert 'if __name__ == "__main__"' not in content

    def test_node_files_use_relative_imports_without_sys_path(self):
        """Node files import the parent package's state, no sys.path hack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "simple_workflow.yml", output_dir)

            content = (output_dir / "nodes" / "llm_node.py").read_text()
            assert "from ..state import GraphState" in content
            assert "sys.path" not in content

    def test_retriever_template_and_knowledge_node_wiring(self):
        """retriever.py is bundled and a knowledge-retrieval node calls the port."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            translate(FIXTURES_DIR / "guardduty_handler.yml", output_dir)

            assert (output_dir / "retriever.py").exists()

            kr = (output_dir / "nodes" / "node_1722397470145.py").read_text()
            assert "from ..retriever import get_retriever" in kr
            assert "get_retriever().retrieve(" in kr
