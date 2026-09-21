"""State file generator for LangGraph workflows.

This module generates the state.py file with GraphState TypedDict definitions.
"""

from pathlib import Path

from dify2langgraph.codegen.handlers import get_handler
from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph

logger = get_logger(__name__)


def get_node_output_fields(node: NodeInfo) -> dict[str, str]:
    """Infer output fields for a node based on its type and configuration.

    Delegates to the node's :class:`~dify2langgraph.codegen.handlers.NodeHandler`;
    unknown types get a generic ``{"output": "Any"}`` from the fallback.

    Args:
        node: NodeInfo instance.

    Returns:
        Dictionary mapping field names to their types.
    """
    return get_handler(node.type).output_fields(node)


def generate_state_file(
    graph: WorkflowGraph,
    output_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate state.py with GraphState TypedDict.

    Args:
        graph: Parsed workflow graph.
        output_dir: Directory to write the generated file.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    lines = [
        '"""Generated GraphState for LangGraph workflow.',
        "",
        "This file is auto-generated. Do not edit directly.",
        '"""',
        "",
        "from typing import Any, TypedDict",
        "",
        "",
    ]

    # Generate TypedDict for each node's output
    for node_id in graph.nodes:
        node = graph.nodes[node_id]
        func_name, class_name = get_node_names(node_id, node_name_map)
        fields = get_node_output_fields(node)

        lines.extend([
            f"class {class_name}(TypedDict, total=False):",
            f'    """Output of node: {node.title} (type: {node.type})."""',
            "",
        ])

        for field_name, field_type in fields.items():
            lines.append(f"    {field_name}: {field_type}")

        lines.extend(["", ""])

    # Generate main GraphState
    lines.extend([
        "class GraphState(TypedDict, total=False):",
        '    """State container for all node outputs.',
        "",
        "    Each key corresponds to a node ID in the workflow.",
        "    Values are typed dictionaries containing the node's output data.",
        '    """',
        "",
    ])

    for node_id in graph.nodes:
        node = graph.nodes[node_id]
        func_name, class_name = get_node_names(node_id, node_name_map)
        lines.append(f'    {func_name}: {class_name}  # {node.type}: {node.title}')

    content = "\n".join(lines) + "\n"
    output_path = output_dir / "state.py"
    # newline="\n" pins LF on every platform. Left to the default, Python's text
    # mode rewrites "\n" to os.linesep, so a native Windows run would emit CRLF
    # while the container (Linux) emits LF -- the same DSL would produce
    # byte-different output depending on how the converter was run (ADR-0001).
    output_path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Generated: %s", output_path)
