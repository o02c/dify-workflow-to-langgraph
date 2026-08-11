"""Tests for the Dify DSL parser."""

from pathlib import Path

import pytest

from dify2langgraph.parser import (
    VARIABLE_REFERENCE_PATTERN,
    DifyDSLParser,
    VariableReference,
    replace_variable_references,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestVariableReference:
    """Tests for VariableReference class."""

    def test_parse_simple_reference(self):
        """Test parsing a simple node.field reference."""
        ref = VariableReference.parse("llm_node.text")
        assert ref.node_id == "llm_node"
        assert ref.field_path == ["text"]
        assert ref.raw == "llm_node.text"

    def test_parse_nested_reference(self):
        """Test parsing a nested reference with multiple fields."""
        ref = VariableReference.parse("start_node.inputs.query")
        assert ref.node_id == "start_node"
        assert ref.field_path == ["inputs", "query"]

    def test_parse_numeric_node_id(self):
        """Test parsing a reference with numeric node ID."""
        ref = VariableReference.parse("1722391426202.type")
        assert ref.node_id == "1722391426202"
        assert ref.field_path == ["type"]

    def test_to_state_access_simple(self):
        """Test converting simple reference to state access."""
        ref = VariableReference.parse("llm_node.text")
        assert ref.to_state_access() == 'state["llm_node"]["text"]'

    def test_to_state_access_nested(self):
        """Test converting nested reference to state access."""
        ref = VariableReference.parse("start.inputs.query")
        assert ref.to_state_access() == 'state["start"]["inputs"]["query"]'


class TestVariableReferencePattern:
    """Tests for the variable reference regex pattern."""

    def test_match_simple_reference(self):
        """Test matching a simple variable reference."""
        text = "Hello {{#user.name#}}"
        matches = VARIABLE_REFERENCE_PATTERN.findall(text)
        assert matches == ["user.name"]

    def test_match_multiple_references(self):
        """Test matching multiple variable references."""
        text = "{{#node1.field1#}} and {{#node2.field2#}}"
        matches = VARIABLE_REFERENCE_PATTERN.findall(text)
        assert matches == ["node1.field1", "node2.field2"]

    def test_match_numeric_node_id(self):
        """Test matching numeric node IDs (common in Dify)."""
        text = "Value: {{#1722391426202.type#}}"
        matches = VARIABLE_REFERENCE_PATTERN.findall(text)
        assert matches == ["1722391426202.type"]

    def test_match_nested_path(self):
        """Test matching nested field paths."""
        text = "{{#start_node.inputs.query.value#}}"
        matches = VARIABLE_REFERENCE_PATTERN.findall(text)
        assert matches == ["start_node.inputs.query.value"]

    def test_no_match_without_hash(self):
        """Test that references without # are not matched."""
        text = "{{node.field}}"
        matches = VARIABLE_REFERENCE_PATTERN.findall(text)
        assert matches == []


class TestReplaceVariableReferences:
    """Tests for the replace_variable_references function."""

    def test_replace_single_reference(self):
        """Test replacing a single variable reference."""
        text = "Answer: {{#llm_node.text#}}"
        result = replace_variable_references(text)
        assert result == 'Answer: {state["llm_node"]["text"]}'

    def test_replace_multiple_references(self):
        """Test replacing multiple variable references."""
        text = "{{#node1.a#}} + {{#node2.b#}}"
        result = replace_variable_references(text)
        assert result == '{state["node1"]["a"]} + {state["node2"]["b"]}'

    def test_replace_with_numeric_id(self):
        """Test replacing reference with numeric node ID."""
        text = "Type: {{#1722391426202.type#}}"
        result = replace_variable_references(text)
        assert result == 'Type: {state["1722391426202"]["type"]}'

    def test_no_replacement_without_reference(self):
        """Test that text without references is unchanged."""
        text = "Hello, world!"
        result = replace_variable_references(text)
        assert result == "Hello, world!"


class TestDifyDSLParser:
    """Tests for the DifyDSLParser class."""

    @pytest.fixture
    def parser(self):
        """Create a parser instance."""
        return DifyDSLParser()

    def test_parse_simple_workflow(self, parser):
        """Test parsing a simple workflow DSL."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        # Check nodes
        assert len(graph.nodes) == 3
        assert "start_node" in graph.nodes
        assert "llm_node" in graph.nodes
        assert "end_node" in graph.nodes

        # Check node types
        assert graph.nodes["start_node"].type == "start"
        assert graph.nodes["llm_node"].type == "llm"
        assert graph.nodes["end_node"].type == "end"

        # Check edges
        assert len(graph.edges) == 2

        # Check start/end identification
        assert graph.start_node_id == "start_node"
        assert "end_node" in graph.end_node_ids

    def test_parse_guardduty_workflow(self, parser):
        """Test parsing the GuardDuty handler workflow."""
        filepath = FIXTURES_DIR / "guardduty_handler.yml"
        graph = parser.parse_file(filepath)

        # Check nodes count
        assert len(graph.nodes) == 7

        # Check node types present
        node_types = {n.type for n in graph.nodes.values()}
        assert "start" in node_types
        assert "question-classifier" in node_types
        assert "knowledge-retrieval" in node_types
        assert "llm" in node_types
        assert "tool" in node_types
        assert "end" in node_types

        # Check edges
        assert len(graph.edges) == 6

        # Check start node
        assert graph.start_node_id == "1722391426202"

        # Check multiple end nodes
        assert len(graph.end_node_ids) == 2

    def test_extract_variable_references(self, parser):
        """Test extracting variable references from nodes."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        # LLM node should have reference to start_node.query
        llm_node = graph.nodes["llm_node"]
        assert len(llm_node.references) > 0

        ref_raws = [r.raw for r in llm_node.references]
        assert "start_node.query" in ref_raws

    def test_extract_variable_references_guardduty(self, parser):
        """Test extracting variable references from GuardDuty workflow."""
        filepath = FIXTURES_DIR / "guardduty_handler.yml"
        graph = parser.parse_file(filepath)

        # LLM node (1722398149172) has multiple variable references
        llm_node = graph.nodes["1722398149172"]
        ref_raws = [r.raw for r in llm_node.references]

        # Should contain references to start node variables
        assert "1722391426202.type" in ref_raws
        assert "1722391426202.severity" in ref_raws
        assert "1722391426202.finding" in ref_raws

    def test_dependencies_extracted(self, parser):
        """Test that node dependencies are correctly extracted."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        # LLM node depends on start_node (via {{#start_node.query#}})
        llm_node = graph.nodes["llm_node"]
        assert "start_node" in llm_node.dependencies

        # End node uses value_selector format [node_id, field]
        end_node = graph.nodes["end_node"]
        assert "llm_node" in end_node.dependencies

    def test_value_selector_references(self, parser):
        """Test that value_selector format references are extracted."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        # End node has value_selector: [llm_node, text]
        end_node = graph.nodes["end_node"]
        ref_raws = [r.raw for r in end_node.references]
        assert "llm_node.text" in ref_raws

    def test_query_variable_selector_references(self, parser):
        """Test that query_variable_selector format is extracted."""
        filepath = FIXTURES_DIR / "guardduty_handler.yml"
        graph = parser.parse_file(filepath)

        # Knowledge retrieval node has query_variable_selector
        kr_node = graph.nodes["1722397470145"]
        assert "1722391426202" in kr_node.dependencies

    def test_extract_all_node_ids(self, parser):
        """Test extracting all node IDs from DSL."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        with open(filepath) as f:
            import yaml
            dsl_data = yaml.safe_load(f)

        node_ids = parser.extract_all_node_ids(dsl_data)
        assert set(node_ids) == {"start_node", "llm_node", "end_node"}

    def test_dependency_order(self, parser):
        """Test topological sort for dependency order."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        order = parser.get_dependency_order(graph)

        # Start should come before LLM, LLM before end
        start_idx = order.index("start_node")
        llm_idx = order.index("llm_node")
        end_idx = order.index("end_node")

        assert start_idx < llm_idx < end_idx

    def test_node_titles_extracted(self, parser):
        """Test that node titles are correctly extracted."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        assert graph.nodes["start_node"].title == "Start"
        assert graph.nodes["llm_node"].title == "LLM Node"
        assert graph.nodes["end_node"].title == "End"


class TestEdgeParsing:
    """Tests for edge parsing functionality."""

    @pytest.fixture
    def parser(self):
        return DifyDSLParser()

    def test_edge_source_target(self, parser):
        """Test that edge source and target are correctly parsed."""
        filepath = FIXTURES_DIR / "simple_workflow.yml"
        graph = parser.parse_file(filepath)

        # Find edge from start to llm
        start_to_llm = next(
            (e for e in graph.edges if e.source_node_id == "start_node"),
            None
        )
        assert start_to_llm is not None
        assert start_to_llm.target_node_id == "llm_node"

    def test_conditional_edge_handle(self, parser):
        """Test that conditional edges preserve source handle."""
        filepath = FIXTURES_DIR / "guardduty_handler.yml"
        graph = parser.parse_file(filepath)

        # Find conditional edges from question-classifier
        classifier_edges = [
            e for e in graph.edges
            if e.source_node_id == "1722397570856"
        ]

        # Should have edges with different handles
        handles = {e.source_handle for e in classifier_edges}
        assert len(handles) >= 2  # At least two branches
