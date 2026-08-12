"""Graph file generator for LangGraph workflows.

This module generates the graph.py file with StateGraph construction.
"""

from pathlib import Path

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.codegen.routing import (
    branch_map,
    decision_field,
    is_branching_node,
)
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import WorkflowGraph

logger = get_logger(__name__)


def generate_graph_file(
    graph: WorkflowGraph,
    output_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate graph.py with StateGraph construction.

    Args:
        graph: Parsed workflow graph.
        output_dir: Directory to write the generated file.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    lines = [
        '"""Generated LangGraph workflow definition.',
        "",
        "This file is auto-generated. Do not edit directly.",
        '"""',
        "",
        "from langgraph.graph import END, START, StateGraph",
        "",
        "from state import GraphState",
    ]

    # Import node functions
    node_funcs = [get_node_names(n.id, node_name_map)[0] for n in graph.nodes.values()]
    if node_funcs:
        imports = ", ".join(sorted(node_funcs))
        lines.append(f"from nodes import {imports}")

    # Router functions for Branching Nodes (ADR-0003)
    branching_nodes = [n for n in graph.nodes.values() if is_branching_node(n)]
    for node in branching_nodes:
        func_name, _ = get_node_names(node.id, node_name_map)
        field = decision_field(node)
        lines.extend([
            "",
            "",
            f"def route_{func_name}(state: GraphState) -> str:",
            f'    """Route for branching node: {node.title} ({node.type})."""',
            f'    return state["{func_name}"]["{field}"]',
        ])

    lines.extend([
        "",
        "",
        "def build_graph():",
        '    """Build and return the compiled workflow graph."""',
        "    graph = StateGraph(GraphState)  # ty: ignore[invalid-argument-type]",
        "",
        "    # Add nodes",
    ])

    for node_id in graph.nodes:
        func_name, _ = get_node_names(node_id, node_name_map)
        lines.append(f'    graph.add_node("{func_name}", {func_name})')

    lines.append("")
    lines.append("    # Add edges")

    branching_ids = {n.id for n in branching_nodes}

    # Add start edge
    if graph.start_node_id:
        start_func, _ = get_node_names(graph.start_node_id, node_name_map)
        lines.append(f'    graph.add_edge(START, "{start_func}")')

    # Plain edges -- edges out of a Branching Node are wired conditionally below.
    for edge in graph.edges:
        if edge.source_node_id in branching_ids:
            continue

        source_func, _ = get_node_names(edge.source_node_id, node_name_map)
        target_func, _ = get_node_names(edge.target_node_id, node_name_map)
        lines.append(f'    graph.add_edge("{source_func}", "{target_func}")')

    # Conditional edges for Branching Nodes (ADR-0003)
    if branching_nodes:
        lines.append("")
        lines.append("    # Conditional edges (branching)")
    for node in branching_nodes:
        func_name, _ = get_node_names(node.id, node_name_map)
        mapping = branch_map(graph, node.id, node_name_map)
        # repr() the keys/targets so odd characters in a sourceHandle can't break
        # the emitted literal (matches how node_generator emits the stub default).
        pairs = ", ".join(f"{key!r}: {target!r}" for key, target in mapping.items())
        lines.append(
            f'    graph.add_conditional_edges('
            f'"{func_name}", route_{func_name}, {{{pairs}}})'
        )

    # Add edges from end nodes to END
    for end_node_id in graph.end_node_ids:
        end_func, _ = get_node_names(end_node_id, node_name_map)
        lines.append(f'    graph.add_edge("{end_func}", END)')

    # Use start node's name for example input
    if graph.start_node_id:
        start_func, _ = get_node_names(graph.start_node_id, node_name_map)
    else:
        start_func = "start"

    lines.extend([
        "",
        "    return graph.compile()",
        "",
        "",
        'if __name__ == "__main__":',
        "    workflow = build_graph()",
        "    # Example: provide input for the start node",
        f'    initial_state: GraphState = {{"{start_func}": {{}}}}',
        "    result = workflow.invoke(initial_state)",
        "    print(result)",
        "",
    ])

    content = "\n".join(lines)
    output_path = output_dir / "graph.py"
    output_path.write_text(content, encoding="utf-8")
    logger.info("Generated: %s", output_path)
