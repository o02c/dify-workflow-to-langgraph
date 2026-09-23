"""Graph file generator for LangGraph workflows.

This module generates the graph.py file with StateGraph construction.
"""

from pathlib import Path

from dify2langgraph.codegen.handlers import decision_field, is_branching
from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.codegen.routing import branch_map
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph

logger = get_logger(__name__)

# Generated packages ship without a pyproject.toml, so anyone who lints them --
# including our own `--lint` flag -- gets ruff's default line length. Match it so
# a freshly generated package is isort-clean out of the box.
RUFF_DEFAULT_LINE_LENGTH = 88


def format_from_import(module: str, names: list[str]) -> list[str]:
    """Render a `from <module> import ...` statement, wrapping it when too long.

    Args:
        module: Module to import from, e.g. ``.nodes``.
        names: Names to import, already in the desired order.

    Returns:
        Source lines: one line, or a parenthesised block matching ruff's isort.
    """
    single = f"from {module} import {', '.join(names)}"
    if len(single) <= RUFF_DEFAULT_LINE_LENGTH:
        return [single]
    return [f"from {module} import (", *(f"    {name}," for name in names), ")"]


def _is_inside_iteration(node: NodeInfo) -> bool:
    """Whether a node belongs to an iteration's body rather than the main flow.

    Args:
        node: The parsed node.

    Returns:
        True when the DSL marks it as nested inside an iteration.
    """
    return bool(node.data.get("isInIteration") or node.data.get("iteration_id"))


def terminal_node_ids(graph: WorkflowGraph) -> list[str]:
    """Node ids with no outgoing edge, in graph order.

    These are what the compiled graph routes to ``END``. Type `end` is the usual
    case, but a chatflow terminates on an `answer` node and declares no `end`
    node at all, so the shape rather than the type decides.

    Nodes inside an iteration are excluded. An iteration's inner nodes form their
    own sub-graph whose last step has no outgoing edge in the DSL's flat edge
    list, so on shape alone it looks terminal -- and wiring it to ``END`` would
    say the whole workflow finishes when one pass of the loop body does.
    ``json_translate.yml`` already contains one. langgraph validates neither
    dead ends nor unreachable nodes, so nothing downstream would report it.

    Args:
        graph: The parsed workflow.

    Returns:
        The terminal node ids.
    """
    with_outgoing = {edge.source_node_id for edge in graph.edges}
    return [
        node_id
        for node_id, node in graph.nodes.items()
        if node_id not in with_outgoing and not _is_inside_iteration(node)
    ]


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
    # Computed before the import list: END is only imported when something
    # actually reaches it, so a graph with no terminal does not carry an unused
    # import into the generated package.
    terminals = terminal_node_ids(graph)

    lines = [
        '"""Generated LangGraph workflow definition.',
        "",
        "This file is auto-generated. Do not edit directly.",
        '"""',
        "",
        "from langgraph.graph import END, START, StateGraph"
        if terminals
        else "from langgraph.graph import START, StateGraph",
        "",
    ]

    # Local imports, isort order: `.nodes` sorts before `.state`.
    node_funcs = [get_node_names(n.id, node_name_map)[0] for n in graph.nodes.values()]
    if node_funcs:
        lines.extend(format_from_import(".nodes", sorted(node_funcs)))
    lines.append("from .state import GraphState")

    # Router functions for Branching Nodes
    branching_nodes = [n for n in graph.nodes.values() if is_branching(n)]
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

    # Conditional edges for Branching Nodes
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

    # Every node with no outgoing edge terminates the graph, not just ones of type
    # `end`. A chatflow finishes on an `answer` node and declares no `end` at all,
    # so keying off end_node_ids left that node dangling and left END imported but
    # unused (ruff F401 on the generated package).
    for node_id in terminals:
        end_func, _ = get_node_names(node_id, node_name_map)
        lines.append(f'    graph.add_edge("{end_func}", END)')

    lines.extend([
        "",
        "    return graph.compile()",
        "",
    ])

    content = "\n".join(lines)
    output_path = output_dir / "graph.py"
    output_path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Generated: %s", output_path)
