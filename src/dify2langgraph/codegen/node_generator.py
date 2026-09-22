"""Node file generator for LangGraph workflows.

This module generates individual node files in the nodes/ directory.
"""

import json
from pathlib import Path

from dify2langgraph.codegen.handlers import get_handler
from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph

logger = get_logger(__name__)


def generate_nodes_directory(
    graph: WorkflowGraph,
    output_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate nodes/ directory with individual node files.

    Args:
        graph: Parsed workflow graph.
        output_dir: Directory to write the generated files.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    nodes_dir = output_dir / "nodes"
    nodes_dir.mkdir(parents=True, exist_ok=True)

    sorted_nodes = sorted(graph.nodes.values(), key=lambda n: n.id)

    # Generate individual node files
    for node in sorted_nodes:
        _generate_node_file(node, nodes_dir, graph, node_name_map)

    # Generate __init__.py that re-exports all node functions
    _generate_nodes_init(sorted_nodes, nodes_dir, node_name_map)

    logger.info("Generated: %s/ (%d node files)", nodes_dir, len(sorted_nodes))


def _generate_node_file(
    node: NodeInfo,
    nodes_dir: Path,
    graph: WorkflowGraph,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate a single node file.

    Args:
        node: NodeInfo instance.
        nodes_dir: The nodes/ directory path.
        graph: Parsed workflow graph (used to pick a branching node's default branch).
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    func_name, class_name = get_node_names(node.id, node_name_map)
    filename = f"{func_name}.py"

    # Prepare node metadata for agent
    handler = get_handler(node.type)
    output_fields = handler.output_fields(node)
    node_config = {
        "id": node.id,
        "state_key": func_name,  # LLM-generated name used as state key
        "type": node.type,
        "title": node.title,
        "dependencies": sorted(node.dependencies),
        "variable_references": [
            {
                "raw": ref.raw,
                "node_id": ref.node_id,
                "field_path": ref.field_path,
                "state_access": ref.to_state_access(node_name_map),
            }
            for ref in node.references
        ],
        "expected_outputs": output_fields,
        "dify_config": node.data,  # Full original Dify node configuration
    }

    # Format JSON with proper indentation
    config_json = json.dumps(node_config, indent=4, ensure_ascii=False)

    lines = [
        f'"""Node: {node.title} (type: {node.type}).',
        "",
        "This file is auto-generated. Implement the node logic below.",
        '"""',
        "",
        "from langgraph.types import Command",
        "",
    ]

    # Local imports, sorted as one block: the handler's extra imports (e.g. the
    # Retriever port) can sort before `..state`, so they cannot just be appended.
    local_imports = [
        "from ..state import " + ", ".join(sorted(["GraphState", class_name])),
        *handler.body_imports(node),
    ]
    lines.extend(sorted(local_imports))

    lines += [
        "",
        "# Full node configuration from Dify DSL (for reference)",
        f"NODE_CONFIG_JSON = '''{config_json}'''",
        "",
        "",
        f"def {func_name}(state: GraphState) -> Command:",
        f'    """Execute node: {node.title}.',
        "",
        f"    Node ID: {node.id}",
        f"    Type: {node.type}",
    ]

    # Add dependency info to docstring
    if node.dependencies:
        deps = ", ".join(sorted(node.dependencies))
        lines.append(f"    Dependencies: {deps}")

    lines.extend([
        "",
        "    Expected outputs:",
    ])

    for field_name, field_type in output_fields.items():
        lines.append(f"        - {field_name}: {field_type}")

    lines.extend([
        "",
        "    Args:",
        "        state: Current graph state.",
        "",
        "    Returns:",
        "        Command with state update for this node's output.",
        '    """',
    ])

    # Add variable reference comments in function body
    if node.references:
        lines.append("    # How to access input variables:")
        for ref in node.references:
            lines.append(f"    # {ref.raw} -> {ref.to_state_access(node_name_map)}")
        lines.append("")

    # Generate the node body. The handler owns the output values: most types emit
    # a placeholder Stub, but some (e.g. End) emit a real deterministic body that
    # forwards upstream values. A Branching Node handler defaults its decision
    # field to a real branch key so the generated router resolves.
    if handler.emits_stub_body:
        lines.append(f"    # TODO: Implement {node.type} node logic")
        lines.append("    # See NODE_CONFIG for full Dify configuration details")
    else:
        lines.append(f"    # Deterministic {node.type} node (generated from the Dify DSL)")
    lines.append("")
    prelude = handler.body_prelude(node, graph, node_name_map)
    if prelude:
        lines.extend(prelude)
        lines.append("")
    stub_output = handler.stub_output(node, graph, node_name_map)
    lines.append(f"    output: {class_name} = {{")
    for field_name, literal in stub_output.items():
        lines.append(f'        "{field_name}": {literal},')
    lines.append("    }")
    lines.append("")
    lines.append(f'    return Command(update={{"{func_name}": output}})')
    lines.append("")

    content = "\n".join(lines)
    output_path = nodes_dir / filename
    output_path.write_text(content, encoding="utf-8", newline="\n")


def _generate_nodes_init(
    nodes: list[NodeInfo],
    nodes_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate nodes/__init__.py that re-exports all node functions.

    Args:
        nodes: List of NodeInfo instances.
        nodes_dir: The nodes/ directory path.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    lines = [
        '"""Node functions for LangGraph workflow.',
        "",
        "This module re-exports all node functions for easy importing.",
        '"""',
        "",
    ]

    # Import and re-export each node function
    for node in nodes:
        func_name, _ = get_node_names(node.id, node_name_map)
        lines.append(f"from .{func_name} import {func_name}")

    lines.append("")
    lines.append("__all__ = [")
    for node in nodes:
        func_name, _ = get_node_names(node.id, node_name_map)
        lines.append(f'    "{func_name}",')
    lines.append("]")
    lines.append("")

    content = "\n".join(lines)
    output_path = nodes_dir / "__init__.py"
    output_path.write_text(content, encoding="utf-8", newline="\n")
