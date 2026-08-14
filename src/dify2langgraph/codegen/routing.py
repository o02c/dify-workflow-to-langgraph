"""Structural routing helpers for Branching Nodes.

These helpers derive the branch-key -> target mapping from the DSL edge
``sourceHandle``. They are type-agnostic: *which* output field drives the route
(and whether a Node branches at all) is type-specific knowledge that lives on the
Node Handler in :mod:`dify2langgraph.codegen.handlers`.
"""

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.parser.dsl_parser import EdgeInfo, WorkflowGraph

# sourceHandle value Dify uses for a plain (non-branching) successor edge.
PLAIN_SOURCE_HANDLE = "source"


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
