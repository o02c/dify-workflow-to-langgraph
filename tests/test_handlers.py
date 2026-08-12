"""Tests for the Node Handler registry (ADR-0005)."""

from pathlib import Path

from dify2langgraph.codegen.handlers import (
    decision_field,
    get_handler,
    is_branching,
)
from dify2langgraph.parser.dsl_parser import DifyDSLParser, NodeInfo

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _node(node_type: str, data: dict | None = None) -> NodeInfo:
    return NodeInfo(id="n1", type=node_type, title="t", data=data or {})


class TestRegistryLookup:
    """get_handler resolves a handler per type, with a fallback for the rest."""

    def test_known_type_returns_specific_handler(self):
        assert get_handler("llm").node_type == "llm"
        assert get_handler("question-classifier").node_type == "question-classifier"

    def test_unknown_type_falls_back_to_generic_stub(self):
        handler = get_handler("http-request")  # not implemented in v1
        assert handler.output_fields(_node("http-request")) == {"output": "Any"}
        assert handler.is_branching is False


class TestOutputFields:
    """Each handler reports the Node Output fields for its type."""

    def test_llm(self):
        assert get_handler("llm").output_fields(_node("llm")) == {
            "text": "str",
            "usage": "dict[str, int]",
        }

    def test_code(self):
        assert get_handler("code").output_fields(_node("code")) == {
            "result": "Any",
            "stdout": "str",
            "stderr": "str",
        }

    def test_start_uses_declared_variables(self):
        node = _node(
            "start",
            {
                "variables": [
                    {"variable": "query", "type": "text-input"},
                    {"variable": "count", "type": "number"},
                ]
            },
        )
        assert get_handler("start").output_fields(node) == {
            "query": "str",
            "count": "float",
        }

    def test_start_without_variables_defaults_to_inputs(self):
        assert get_handler("start").output_fields(_node("start")) == {
            "inputs": "dict[str, Any]"
        }

    def test_end_uses_declared_outputs(self):
        node = _node("end", {"outputs": [{"variable": "result"}, {"variable": "meta"}]})
        assert get_handler("end").output_fields(node) == {
            "result": "Any",
            "meta": "Any",
        }

    def test_end_without_outputs_defaults_to_result(self):
        assert get_handler("end").output_fields(_node("end")) == {"result": "Any"}


class TestBranching:
    """Branching Nodes expose is_branching + the field that drives the route."""

    def test_question_classifier_is_branching(self):
        node = _node("question-classifier")
        assert is_branching(node) is True
        assert decision_field(node) == "class_id"

    def test_if_else_is_branching(self):
        node = _node("if-else")
        assert is_branching(node) is True
        assert decision_field(node) == "selected_branch"

    def test_plain_node_is_not_branching(self):
        node = _node("llm")
        assert is_branching(node) is False
        assert decision_field(node) is None


class TestStubOutput:
    """The Stub body's placeholder values, including the branching default."""

    def test_generic_placeholders(self):
        handler = get_handler("code")
        node = _node("code")
        # graph is unused for a non-branching node's stub.
        stub = handler.stub_output(node, graph=None)  # type: ignore[arg-type]
        assert stub == {"result": "None", "stdout": '"placeholder"', "stderr": '"placeholder"'}

    def test_branching_defaults_decision_field_to_first_branch_key(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "ifelse_workflow.yml")
        node = graph.nodes["ifelse_node"]
        stub = get_handler(node.type).stub_output(node, graph)
        # First outgoing branch of the if-else is the 'true' handle.
        assert stub["selected_branch"] == "'true'"
