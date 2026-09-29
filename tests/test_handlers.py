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
        handler = get_handler("some-future-node")
        # A type that exists nowhere, so the test cannot go stale as handlers are
        # added. Downstream reads of a real unknown type are covered by the
        # DSL-reference safety net (see test_generated).
        assert handler.output_fields(_node("some-future-node")) == {"output": "Any"}
        assert handler.is_branching is False


class TestOutputFields:
    """Each handler reports the Node Output fields for its type."""

    def test_llm(self):
        """Dify's LLM node outputs reasoning_content too, so a selector can read it."""
        assert get_handler("llm").output_fields(_node("llm")) == {
            "text": "str",
            "reasoning_content": "str",
            "finish_reason": "str",
            "usage": "dict[str, Any]",
        }

    def test_code(self):
        """A code node's outputs come from the DSL, which declares them with types.

        The previous fixed set was invented: Dify's code node has no `stdout` or
        `stderr` output, and `result` exists only when the author named it that.
        A downstream read of a declared name therefore raised KeyError at run time.
        """
        node = _node("code", {
            "type": "code",
            "outputs": {
                "body_head": {"type": "string", "children": None},
                "rows": {"type": "array[object]", "children": None},
            },
        })

        assert get_handler("code").output_fields(node) == {
            "body_head": "str",
            "rows": "list[dict[str, Any]]",
        }

    def test_code_declaring_nothing(self):
        """Declaring no outputs means no outputs; nothing is invented for it.

        What a downstream selector reads is still declared, by the safety net in
        effective_output_fields (see test_translator/test_generated).
        """
        assert get_handler("code").output_fields(_node("code")) == {}

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

    def test_template_transform(self):
        assert get_handler("template-transform").output_fields(
            _node("template-transform")
        ) == {"output": "str"}

    def test_answer(self):
        assert get_handler("answer").output_fields(_node("answer")) == {
            "answer": "str",
            "files": "list[Any]",
        }

    def test_agent(self):
        assert get_handler("agent").output_fields(_node("agent")) == {
            "text": "str",
            "files": "list[dict[str, Any]]",
        }

    def test_knowledge_retrieval(self):
        assert get_handler("knowledge-retrieval").output_fields(
            _node("knowledge-retrieval")
        ) == {"result": "list[dict[str, Any]]"}

    def test_tool(self):
        """Dify's fixed three. Plugin-declared extras are not in the DSL."""
        assert get_handler("tool").output_fields(_node("tool")) == {
            "text": "str",
            "files": "list[Any]",
            "json": "list[dict[str, Any]]",
        }

    def test_http_request(self):
        """It had no handler at all, so `body` was undeclared and unreadable."""
        assert get_handler("http-request").output_fields(_node("http-request")) == {
            "body": "str",
            "status_code": "float",
            "headers": "dict[str, Any]",
            "files": "list[Any]",
        }

    def test_parameter_extractor_reads_its_declared_parameters(self):
        """Like `code`, the DSL names them -- plus Dify's three own fields."""
        node = _node("parameter-extractor", {
            "type": "parameter-extractor",
            "parameters": [
                {"name": "city", "type": "string"},
                {"name": "days", "type": "number"},
                {"name": "ok", "type": "bool"},  # Dify's legacy spelling
            ],
        })

        assert get_handler("parameter-extractor").output_fields(node) == {
            "city": "str",
            "days": "float",
            "ok": "bool",
            "__is_success": "int",
            "__reason": "str",
            "__usage": "dict[str, Any]",
        }

    def test_list_operator_types_come_from_the_node(self):
        node = _node("list-operator", {
            "type": "list-operator",
            "var_type": "array[object]",
            "item_var_type": "object",
        })

        assert get_handler("list-operator").output_fields(node) == {
            "result": "list[dict[str, Any]]",
            "first_record": "dict[str, Any]",
            "last_record": "dict[str, Any]",
        }

    def test_document_extractor_follows_its_input_shape(self):
        single = _node("document-extractor", {"type": "document-extractor"})
        many = _node("document-extractor", {
            "type": "document-extractor", "is_array_file": True,
        })

        assert get_handler("document-extractor").output_fields(single) == {"text": "str"}
        assert get_handler("document-extractor").output_fields(many) == {
            "text": "list[str]",
        }

    def test_nodes_with_no_readable_output_declare_none(self):
        """Dify exposes nothing from these, so a bare `output` field would be a lie.

        `assigner` writes to conversation variables; the iteration/loop markers are
        no-op anchors.
        """
        for node_type in ("assigner", "iteration-start", "loop-start", "loop-end"):
            assert get_handler(node_type).output_fields(_node(node_type)) == {}, node_type

    def test_variable_aggregator(self):
        assert get_handler("variable-aggregator").output_fields(
            _node("variable-aggregator")
        ) == {"output": "Any"}


class TestBranching:
    """Branching Nodes expose is_branching + the field that drives the route."""

    def test_question_classifier_is_branching(self):
        node = _node("question-classifier")
        assert is_branching(node) is True
        assert decision_field(node) == "class_id"

    def test_if_else_is_branching(self):
        node = _node("if-else")
        assert is_branching(node) is True
        # Dify's own name for the output. `selected_branch` was invented here, so
        # anyone implementing the body would compute the right value under a name
        # nothing else uses.
        assert decision_field(node) == "selected_case_id"

    def test_plain_node_is_not_branching(self):
        node = _node("llm")
        assert is_branching(node) is False
        assert decision_field(node) is None


class TestStubOutput:
    """The Stub body's placeholder values, including the branching default."""

    def test_generic_placeholders(self):
        """Each declared field gets a literal of its own declared type."""
        handler = get_handler("code")
        node = _node("code", {
            "type": "code",
            "outputs": {
                "body_head": {"type": "string", "children": None},
                "count": {"type": "number", "children": None},
                "rows": {"type": "array[object]", "children": None},
            },
        })
        # graph is unused for a non-branching node's stub.
        stub = handler.stub_output(node, graph=None)  # type: ignore[arg-type]
        assert stub == {"body_head": '"placeholder"', "count": "0.0", "rows": "[]"}

    def test_branching_defaults_decision_field_to_first_branch_key(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "ifelse_workflow.yml")
        node = graph.nodes["ifelse_node"]
        stub = get_handler(node.type).stub_output(node, graph)
        # First outgoing branch of the if-else is the 'true' handle.
        assert stub["selected_case_id"] == "'true'"


class TestEndDeterministicBody:
    """The End node forwards upstream values via normalized accesses (ADR-0004)."""

    def test_end_forwards_value_selector_as_state_access(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "simple_workflow.yml")
        node = graph.nodes["end_node"]
        stub = get_handler(node.type).stub_output(node, graph)
        # `.get` rather than `[...]`: an upstream node on a branch that was not
        # taken has no entry in state, and Dify resolves that selector to None.
        assert stub == {"result": 'state.get("llm_node", {}).get("text")'}

    def test_end_forwards_numeric_id_via_canonical_key(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "translation_workflow.yml")
        node = graph.nodes["1721119092752"]
        stub = get_handler(node.type).stub_output(node, graph)
        assert stub == {"output": 'state.get("node_1721118907775", {}).get("text")'}

    def test_end_without_outputs_defaults_to_none(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "guardduty_handler.yml")
        node = graph.nodes["1722399235845"]
        stub = get_handler(node.type).stub_output(node, graph)
        assert stub == {"result": "None"}

    def test_end_handler_marks_body_as_deterministic(self):
        assert get_handler("end").emits_stub_body is False
        # Start is deterministic too (ADR-0009): it surfaces the caller's inputs.
        assert get_handler("start").emits_stub_body is False
        # if-else was the only registered handler never named here.
        assert get_handler("if-else").node_type == "if-else"
        assert get_handler("llm").emits_stub_body is True


class TestKnowledgeRetrievalBody:
    """knowledge-retrieval calls the Retriever port (ADR-0006)."""

    def test_calls_retriever_with_normalized_query_and_dataset_ids(self):
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "guardduty_handler.yml")
        node = graph.nodes["1722397470145"]
        stub = get_handler(node.type).stub_output(node, graph)
        assert stub == {
            "result": "get_retriever().retrieve("
            'query=state.get("node_1722391426202", {}).get("finding") or "", '
            "dataset_ids=['a6d5e1e3-28c6-417c-aad8-6f2e3bfc7fd1'])"
        }

    def test_imports_the_retriever_port(self):
        node = _node("knowledge-retrieval")
        handler = get_handler("knowledge-retrieval")
        assert handler.body_imports(node) == ["from ..retriever import get_retriever"]
        assert handler.emits_stub_body is False

    def test_no_retrieval_model_when_config_absent(self):
        """A node without multiple_retrieval_config emits no retrieval_model kwarg.

        The adapter then fills all required fields itself (search_method from env).
        """
        graph = DifyDSLParser().parse_file(FIXTURES_DIR / "guardduty_handler.yml")
        node = graph.nodes["1722397470145"]
        call = get_handler(node.type).stub_output(node, graph)["result"]
        assert "retrieval_model=" not in call

    def test_projects_top_k_and_score_threshold_from_config(self):
        """multiple_retrieval_config (top_k, score_threshold) projects into the call."""
        node = _node(
            "knowledge-retrieval",
            {
                "query_variable_selector": ["start", "q"],
                "dataset_ids": ["ds-1"],
                "multiple_retrieval_config": {"top_k": 5, "score_threshold": 0.6},
            },
        )
        # Minimal graph containing the referenced 'start' node so the query resolves.
        graph = DifyDSLParser().parse({"workflow": {"graph": {"nodes": [
            {"id": "start", "data": {"type": "start"}},
        ], "edges": []}}})
        call = get_handler(node.type).stub_output(node, graph)["result"]
        assert "'top_k': 5" in call
        assert "'score_threshold_enabled': True" in call
        assert "'score_threshold': 0.6" in call
