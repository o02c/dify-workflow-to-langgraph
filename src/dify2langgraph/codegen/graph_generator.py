"""Graph file generator for LangGraph workflows.

This module generates the graph.py file with StateGraph construction.
"""

from pathlib import Path

from dify2langgraph.codegen.naming import get_node_names
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

    # Add start edge
    if graph.start_node_id:
        start_func, _ = get_node_names(graph.start_node_id, node_name_map)
        lines.append(f'    graph.add_edge(START, "{start_func}")')

    # Add regular edges
    for edge in graph.edges:
        # Skip edges from start node (already handled)
        if edge.source_node_id == graph.start_node_id and not edge.source_handle:
            continue

        source_func, _ = get_node_names(edge.source_node_id, node_name_map)
        target_func, _ = get_node_names(edge.target_node_id, node_name_map)

        # Handle conditional edges (with source_handle)
        if edge.source_handle:
            lines.append(
                f'    # Conditional edge: {source_func} '
                f'({edge.source_handle}) -> {target_func}'
            )

        lines.append(
            f'    graph.add_edge("{source_func}", "{target_func}")'
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
