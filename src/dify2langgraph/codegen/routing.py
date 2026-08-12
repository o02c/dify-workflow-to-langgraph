"""Deterministic routing helpers for Branching Nodes (ADR-0003).

A Branching Node (``question-classifier`` / ``if-else``) is wired with
``add_conditional_edges`` plus a generated ``route_<node>(state)`` function whose
branch-key -> target mapping is derived from the DSL edge ``sourceHandle``.
Everything here is deterministic; only the branch *decision* lives in the
(possibly LLM-backed) node body, while the *wiring* stays in graph.py.
"""

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.parser.dsl_parser import EdgeInfo, NodeInfo, WorkflowGraph

# Node types that route to one of several successors based on a runtime decision.
BRANCHING_NODE_TYPES = frozenset({"question-classifier", "if-else"})

# sourceHandle value Dify uses for a plain (non-branching) successor edge.
PLAIN_SOURCE_HANDLE = "source"

# Per-type: which field of the Node Output drives the route.
_DECISION_FIELD = {
    "question-classifier": "class_id",
    "if-else": "selected_branch",
}


def is_branching_node(node: NodeInfo) -> bool:
    """Whether this node routes conditionally (needs add_conditional_edges)."""
    return node.type in BRANCHING_NODE_TYPES


def decision_field(node: NodeInfo) -> str:
    """The Node Output field whose value selects the branch."""
    return _DECISION_FIELD[node.type]


def branch_edges(graph: WorkflowGraph, node_id: str) -> list[EdgeInfo]:
    """Outgoing edges of a branching node, in DSL order."""
    return [e for e in graph.edges if e.source_node_id == node_id]


def branch_map(
    graph: WorkflowGraph,
    node_id: str,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> dict[str, str]:
    """Map each branch key (sourceHandle) to its target function name."""
    result: dict[str, str] = {}
    for edge in branch_edges(graph, node_id):
        if edge.source_handle is None:
            continue
        target_func, _ = get_node_names(edge.target_node_id, node_name_map)
        result[edge.source_handle] = target_func
    return result


def default_branch_key(graph: WorkflowGraph, node_id: str) -> str | None:
    """First branch key -- the stub's default decision so the graph still runs."""
    for edge in branch_edges(graph, node_id):
        if edge.source_handle is not None:
            return edge.source_handle
    return None
