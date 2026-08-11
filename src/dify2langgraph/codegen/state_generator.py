"""State file generator for LangGraph workflows.

This module generates the state.py file with GraphState TypedDict definitions.
"""

from pathlib import Path

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph

logger = get_logger(__name__)


def get_node_output_fields(node: NodeInfo) -> dict[str, str]:
    """Infer output fields for a node based on its type and configuration.

    Args:
        node: NodeInfo instance.

    Returns:
        Dictionary mapping field names to their types.
    """
    node_type = node.type
    data = node.data

    # Default fields by node type
    if node_type == "start":
        # Start node outputs are defined by its variables
        fields: dict[str, str] = {}
        for var in data.get("variables", []):
            var_name = var.get("variable", "")
            var_type = var.get("type", "text-input")
            if var_name:
                if var_type == "number":
                    fields[var_name] = "float"
                elif var_type == "select":
                    fields[var_name] = "str"
                else:
                    fields[var_name] = "str"
        return fields if fields else {"inputs": "dict[str, Any]"}

    elif node_type == "llm":
        return {
            "text": "str",
            "usage": "dict[str, int]",
        }

    elif node_type == "knowledge-retrieval":
        return {
            "result": "list[dict[str, Any]]",
        }

    elif node_type == "code":
        return {
            "result": "Any",
            "stdout": "str",
            "stderr": "str",
        }

    elif node_type == "tool":
        return {
            "text": "str",
            "files": "list[dict[str, Any]]",
        }

    elif node_type == "if-else":
        return {
            "selected_branch": "str",
        }

    elif node_type == "question-classifier":
        return {
            "class_name": "str",
            "class_id": "str",
        }

    elif node_type == "template-transform":
        return {
            "output": "str",
        }

    elif node_type == "variable-aggregator":
        return {
            "output": "Any",
        }

    elif node_type == "end":
        # End node may have defined outputs
        end_fields: dict[str, str] = {}
        for output in data.get("outputs", []):
            var_name = output.get("variable", "")
            if var_name:
                end_fields[var_name] = "Any"
        return end_fields if end_fields else {"result": "Any"}

    elif node_type == "answer":
        return {
            "answer": "str",
        }

    elif node_type == "agent":
        return {
            "text": "str",
            "files": "list[dict[str, Any]]",
        }

    else:
        # Unknown type - generic output
        return {
            "output": "Any",
        }


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
    output_path.write_text(content, encoding="utf-8")
    logger.info("Generated: %s", output_path)
