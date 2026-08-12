"""Node Handler registry (ADR-0005).

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

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        """Field name -> type annotation for this node's Node Output."""
        return {"output": "Any"}

    def stub_output(self, node: NodeInfo, graph: WorkflowGraph) -> dict[str, str]:
        """Field name -> Python literal for the Stub body's output dict."""
        return {
            name: placeholder_literal(ftype)
            for name, ftype in self.output_fields(node).items()
        }


class StartHandler(NodeHandler):
    node_type = "start"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for var in node.data.get("variables", []):
            name = var.get("variable", "")
            if not name:
                continue
            fields[name] = "float" if var.get("type") == "number" else "str"
        return fields or {"inputs": "dict[str, Any]"}


class LlmHandler(NodeHandler):
    node_type = "llm"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "usage": "dict[str, int]"}


class KnowledgeRetrievalHandler(NodeHandler):
    node_type = "knowledge-retrieval"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"result": "list[dict[str, Any]]"}


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

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for output in node.data.get("outputs", []):
            name = output.get("variable", "")
            if name:
                fields[name] = "Any"
        return fields or {"result": "Any"}


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

    So the generated Router (ADR-0003) resolves to a single successor and the
    graph runs end-to-end before the body is implemented.
    """

    is_branching = True

    def stub_output(self, node: NodeInfo, graph: WorkflowGraph) -> dict[str, str]:
        output = super().stub_output(node, graph)
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
