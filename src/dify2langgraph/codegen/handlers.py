"""Node Handler registry.

Each Dify Node type maps to one :class:`NodeHandler` that owns the type-specific
knowledge the generators need:

- ``output_fields(node)`` -- the Node Output ``TypedDict`` fields
- ``stub_output(node, graph)`` -- the placeholder Node Body values (the Stub)
- ``is_branching`` / ``decision_field`` -- routing shape for a Branching Node

The state / node / graph generators are thin orchestrators that look a handler up
by type via :func:`get_handler`; an unknown type falls back to the base
:class:`NodeHandler`, which emits a generic typed Stub so the generated code still
compiles. Adding support for a Node type is adding one handler here.

Structural (type-agnostic) routing helpers -- deriving the branch map from the
DSL ``sourceHandle`` -- live in :mod:`dify2langgraph.codegen.routing`.
"""

import json
from typing import Any

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.codegen.routing import default_branch_key
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph


def placeholder_literal(field_type: str) -> str:
    """Python literal used as a Stub's placeholder for a given type annotation."""
    if field_type == "str":
        return '"placeholder"'
    if field_type == "float":
        return "0.0"
    if field_type == "int":
        return "0"
    if field_type == "bool":
        return "False"
    if field_type.startswith("list"):
        return "[]"
    if field_type.startswith("dict"):
        return "{}"
    # "Any" and anything unknown
    return "None"


class NodeHandler:
    """Fallback handler: a generic typed Stub wired as a single successor.

    Subclasses override :meth:`output_fields` (and, for Branching Nodes, set
    ``is_branching`` / ``decision_field``). The base implementation is what an
    unknown Node type gets.
    """

    node_type: str = "*"
    is_branching: bool = False
    decision_field: str | None = None
    # False when the handler emits a real deterministic body (not a TODO Stub).
    emits_stub_body: bool = True

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        """Field name -> type annotation for this node's Node Output."""
        return {"output": "Any"}

    def body_imports(self, node: NodeInfo) -> list[str]:
        """Extra import lines the generated node body needs (e.g. the Retriever)."""
        return []

    def body_prelude(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> list[str]:
        """Lines emitted inside the node body before the output dict.

        Most node types need nothing here. The Start node uses it to pull the
        caller's workflow inputs out of state and reject missing required ones.

        Args:
            node: The Node being generated.
            graph: The parsed workflow, for resolving references.
            node_name_map: Optional node_id -> (snake_case, CamelCase) mapping.

        Returns:
            Source lines, already indented to the function body.
        """
        return []

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        """Field name -> Python expression for the node body's output dict.

        The base implementation emits placeholder literals (a Stub). Handlers may
        override to emit real expressions (e.g. the End node forwards upstream
        values via normalized state accesses).
        """
        return {
            name: placeholder_literal(ftype)
            for name, ftype in self.output_fields(node).items()
        }


def start_variables(node: NodeInfo) -> list[dict[str, Any]]:
    """Declared workflow input variables of a Start Node, in DSL order.

    Args:
        node: The Start Node.

    Returns:
        The variable declarations that have a name.
    """
    return [v for v in node.data.get("variables", []) if v.get("variable")]


def start_input_example(node: NodeInfo) -> str:
    """Python literal for an example workflow input dict.

    The Start Node rejects missing required inputs, so the generated
    ``__main__.py`` has to pass something for ``python -m <package>`` to remain a
    working demonstration rather than an immediate ValueError.

    Args:
        node: The Start Node.

    Returns:
        A dict literal such as ``{"query": "example"}``.
    """
    variables = start_variables(node)
    if not variables:
        return "{}"
    pairs = []
    for var in variables:
        declared = var.get("default")
        if declared is not None:
            value = repr(declared)
        else:
            value = "0.0" if var.get("type") == "number" else '"example"'
        pairs.append(f"{json.dumps(var['variable'])}: {value}")
    return "{" + ", ".join(pairs) + "}"


class StartHandler(NodeHandler):
    node_type = "start"
    # Deterministic: surfaces the caller's workflow inputs. It used to emit a
    # Stub that returned {"query": "placeholder"}, which *overwrote* whatever the
    # caller passed -- so a generated workflow could not be given inputs at all.
    emits_stub_body = False

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for var in start_variables(node):
            fields[var["variable"]] = "float" if var.get("type") == "number" else "str"
        return fields or {"inputs": "dict[str, Any]"}

    def body_prelude(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> list[str]:
        key, _ = get_node_names(node.id, node_name_map)
        # A variable that declares a default always has a value to fall back on,
        # so it is never "missing" even when the DSL marks it required.
        required = [
            v["variable"]
            for v in start_variables(node)
            if v.get("required") and v.get("default") is None
        ]

        lines = [
            "    # Workflow inputs are supplied by the caller in this node's own",
            "    # state slot (ADR-0002):",
            f'    #     build_graph().invoke({{{json.dumps(key)}: {{...}}}})',
            f"    supplied = state.get({json.dumps(key)}, {{}})",
        ]
        if required:
            names = ", ".join(json.dumps(name) for name in required)
            lines += [
                "",
                f"    missing = [name for name in ({names},) if name not in supplied]",
                "    if missing:",
                "        raise ValueError(",
                f'            "{key} is missing required workflow input(s): "',
                '            + ", ".join(missing)',
                "        )",
            ]
        return lines

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        variables = start_variables(node)
        if not variables:
            return {"inputs": 'supplied.get("inputs", {})'}

        result: dict[str, str] = {}
        for var in variables:
            name = var["variable"]
            literal = json.dumps(name)
            declared = var.get("default")
            if declared is not None:
                # The workflow author set this in Dify; honouring it is what makes
                # the generated package behave like the original workflow.
                result[name] = f"supplied.get({literal}, {declared!r})"
            elif var.get("required"):
                result[name] = f"supplied[{literal}]"
            else:
                fallback = "0.0" if var.get("type") == "number" else '""'
                result[name] = f"supplied.get({literal}, {fallback})"
        return result


class LlmHandler(NodeHandler):
    node_type = "llm"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "usage": "dict[str, int]"}


class KnowledgeRetrievalHandler(NodeHandler):
    node_type = "knowledge-retrieval"
    emits_stub_body = False  # deterministic: calls the Retriever port

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"result": "list[dict[str, Any]]"}

    def body_imports(self, node: NodeInfo) -> list[str]:
        return ["from ..retriever import get_retriever"]

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        # Retrieve through the Retriever port: the query comes from the node's
        # query_variable_selector (normalized to a canonical state access) and the
        # dataset_ids from the Dify config.
        selector = node.data.get("query_variable_selector") or []
        dataset_ids = node.data.get("dataset_ids") or []
        if len(selector) >= 2 and selector[0] in graph.nodes:
            key, _ = get_node_names(str(selector[0]), node_name_map)
            query = f'state["{key}"]'
            for part in selector[1:]:
                query += f'["{part}"]'
        else:
            query = '""'
        call = f"get_retriever().retrieve(query={query}, dataset_ids={dataset_ids!r}"
        retrieval_model = self._retrieval_model(node)
        if retrieval_model:
            call += f", retrieval_model={retrieval_model!r}"
        call += ")"
        return {"result": call}

    @staticmethod
    def _retrieval_model(node: NodeInfo) -> dict[str, object]:
        """Project the Node's multiple_retrieval_config into a retrieval_model.

        Only the DSL-carried fields (top_k, score_threshold); search_method and the
        rest are defaulted by the Retriever adapter (a dataset/deploy concern). The
        adapter also fills the API's other required fields. Reranking passthrough is
        not handled (it needs a rerank provider/model config).
        """
        config = node.data.get("multiple_retrieval_config") or {}
        model: dict[str, object] = {}
        if config.get("top_k") is not None:
            model["top_k"] = config["top_k"]
        threshold = config.get("score_threshold")
        if threshold is not None:
            model["score_threshold_enabled"] = True
            model["score_threshold"] = threshold
        return model


class CodeHandler(NodeHandler):
    node_type = "code"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"result": "Any", "stdout": "str", "stderr": "str"}


class ToolHandler(NodeHandler):
    node_type = "tool"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "files": "list[dict[str, Any]]"}


class TemplateTransformHandler(NodeHandler):
    node_type = "template-transform"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"output": "str"}


class VariableAggregatorHandler(NodeHandler):
    node_type = "variable-aggregator"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"output": "Any"}


class EndHandler(NodeHandler):
    node_type = "end"
    emits_stub_body = False  # deterministic: forwards upstream values

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for output in node.data.get("outputs", []):
            name = output.get("variable", "")
            if name:
                fields[name] = "Any"
        return fields or {"result": "Any"}

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        # The End node is deterministic: each declared output's value_selector
        # [node_id, field...] forwards an upstream value via a normalized canonical
        # state access. Selectors into non-Node namespaces (sys/env) or unknown
        # nodes fall back to a placeholder.
        result: dict[str, str] = {}
        for output in node.data.get("outputs", []):
            name = output.get("variable", "")
            if not name:
                continue
            selector = output.get("value_selector") or []
            if len(selector) >= 2 and selector[0] in graph.nodes:
                key, _ = get_node_names(str(selector[0]), node_name_map)
                access = f'state["{key}"]'
                for part in selector[1:]:
                    access += f'["{part}"]'
                result[name] = access
            else:
                result[name] = "None"
        return result or {"result": "None"}


class AnswerHandler(NodeHandler):
    node_type = "answer"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"answer": "str"}


class AgentHandler(NodeHandler):
    node_type = "agent"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "files": "list[dict[str, Any]]"}


class _BranchingHandler(NodeHandler):
    """Base for Branching Nodes: default the decision field to a valid branch key.

    So the generated Router resolves to a single successor and the graph runs
    end-to-end before the body is implemented.
    """

    is_branching = True

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        output = super().stub_output(node, graph, node_name_map)
        key = default_branch_key(graph, node.id)
        if key is not None and self.decision_field:
            output[self.decision_field] = repr(key)
        return output


class QuestionClassifierHandler(_BranchingHandler):
    node_type = "question-classifier"
    decision_field = "class_id"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"class_name": "str", "class_id": "str"}


class IfElseHandler(_BranchingHandler):
    node_type = "if-else"
    decision_field = "selected_branch"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"selected_branch": "str"}


_HANDLERS: dict[str, NodeHandler] = {
    handler.node_type: handler
    for handler in (
        StartHandler(),
        LlmHandler(),
        KnowledgeRetrievalHandler(),
        CodeHandler(),
        ToolHandler(),
        TemplateTransformHandler(),
        VariableAggregatorHandler(),
        EndHandler(),
        AnswerHandler(),
        AgentHandler(),
        QuestionClassifierHandler(),
        IfElseHandler(),
    )
}

_FALLBACK = NodeHandler()


def get_handler(node_type: str) -> NodeHandler:
    """Return the handler for a Node type, or the generic-Stub fallback."""
    return _HANDLERS.get(node_type, _FALLBACK)


def is_branching(node: NodeInfo) -> bool:
    """Whether this node routes conditionally (needs add_conditional_edges)."""
    return get_handler(node.type).is_branching


def decision_field(node: NodeInfo) -> str | None:
    """The Node Output field whose value selects the branch (None if not branching)."""
    return get_handler(node.type).decision_field
