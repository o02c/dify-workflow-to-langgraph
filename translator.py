"""Main entry point for Dify DSL to LangGraph converter.

This module orchestrates the conversion process:
1. Parse Dify DSL YAML file
2. Analyze node dependencies
3. Generate LangGraph Python code
4. Output to the specified directory
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

from generator.parser import DifyDSLParser, WorkflowGraph

# Templates directory (relative to this file)
TEMPLATES_DIR = Path(__file__).parent / "templates"


def _sanitize_function_name(node_id: str) -> str:
    """Convert node ID to valid Python function name.

    Args:
        node_id: Original node ID.

    Returns:
        Sanitized function name.
    """
    # Replace hyphens and other invalid chars with underscores
    name = node_id.replace("-", "_").replace(" ", "_")
    # Ensure it doesn't start with a number
    if name[0].isdigit():
        name = f"node_{name}"
    return name


def _sanitize_class_name(node_id: str) -> str:
    """Convert node ID to valid Python class name (PascalCase).

    Args:
        node_id: Original node ID.

    Returns:
        Sanitized class name in PascalCase.
    """
    # Replace hyphens and spaces with underscores first
    name = node_id.replace("-", "_").replace(" ", "_")

    # Handle numeric prefix
    if name[0].isdigit():
        name = f"Node{name}"
    else:
        # Convert to PascalCase
        parts = name.split("_")
        name = "".join(part.capitalize() for part in parts)

    return name


def _get_node_names(
    node_id: str,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Get function name and class name for a node.

    Args:
        node_id: Original node ID.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).

    Returns:
        Tuple of (function_name, class_name).
    """
    if node_name_map and node_id in node_name_map:
        snake, camel = node_name_map[node_id]
        return snake, f"{camel}Output"
    return _sanitize_function_name(node_id), _sanitize_class_name(node_id) + "Output"


def _get_node_output_fields(node) -> dict[str, str]:
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
        fields = {}
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
        fields = {}
        for output in data.get("outputs", []):
            var_name = output.get("variable", "")
            if var_name:
                fields[var_name] = "Any"
        return fields if fields else {"result": "Any"}

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
        func_name, class_name = _get_node_names(node_id, node_name_map)
        fields = _get_node_output_fields(node)

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
        func_name, class_name = _get_node_names(node_id, node_name_map)
        lines.append(f'    {func_name}: {class_name}  # {node.type}: {node.title}')

    content = "\n".join(lines) + "\n"
    output_path = output_dir / "state.py"
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")


def _get_placeholder_value(field_type: str) -> str:
    """Get a placeholder value for a given type annotation.

    Args:
        field_type: Type annotation string.

    Returns:
        Python literal string for placeholder.
    """
    if field_type == "str":
        return '"placeholder"'
    elif field_type == "float":
        return "0.0"
    elif field_type == "int":
        return "0"
    elif field_type == "bool":
        return "False"
    elif field_type.startswith("list"):
        return "[]"
    elif field_type.startswith("dict"):
        return "{}"
    elif field_type == "Any":
        return "None"
    else:
        return "None"


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
        _generate_node_file(node, nodes_dir, node_name_map)

    # Generate __init__.py that re-exports all node functions
    _generate_nodes_init(sorted_nodes, nodes_dir, node_name_map)

    print(f"Generated: {nodes_dir}/ ({len(sorted_nodes)} node files)")


def _generate_node_file(
    node,
    nodes_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate a single node file.

    Args:
        node: NodeInfo instance.
        nodes_dir: The nodes/ directory path.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    func_name, class_name = _get_node_names(node.id, node_name_map)
    filename = f"{func_name}.py"

    # Prepare node metadata for agent
    output_fields = _get_node_output_fields(node)
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
        "import json",
        "import sys",
        "from pathlib import Path",
        "",
        "from langgraph.types import Command",
        "",
        "# Add parent directory to path for imports",
        "sys.path.insert(0, str(Path(__file__).parent.parent))",
        "",
        f"from state import GraphState, {class_name}",
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

    # Generate placeholder with proper output structure
    lines.append(f"    # TODO: Implement {node.type} node logic")
    lines.append("    # See NODE_CONFIG for full Dify configuration details")
    lines.append("")
    lines.append(f"    output: {class_name} = {{")
    for field_name, field_type in output_fields.items():
        placeholder = _get_placeholder_value(field_type)
        lines.append(f'        "{field_name}": {placeholder},')
    lines.append("    }")
    lines.append("")
    lines.append(f'    return Command(update={{"{func_name}": output}})')
    lines.append("")

    content = "\n".join(lines)
    output_path = nodes_dir / filename
    output_path.write_text(content, encoding="utf-8")


def _generate_nodes_init(
    nodes: list,
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
        func_name, _ = _get_node_names(node.id, node_name_map)
        lines.append(f"from .{func_name} import {func_name}")

    lines.append("")
    lines.append("__all__ = [")
    for node in nodes:
        func_name, _ = _get_node_names(node.id, node_name_map)
        lines.append(f'    "{func_name}",')
    lines.append("]")
    lines.append("")

    content = "\n".join(lines)
    output_path = nodes_dir / "__init__.py"
    output_path.write_text(content, encoding="utf-8")


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
    node_funcs = [_get_node_names(n.id, node_name_map)[0] for n in graph.nodes.values()]
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
        func_name, _ = _get_node_names(node_id, node_name_map)
        lines.append(f'    graph.add_node("{func_name}", {func_name})')

    lines.append("")
    lines.append("    # Add edges")

    # Add start edge
    if graph.start_node_id:
        start_func, _ = _get_node_names(graph.start_node_id, node_name_map)
        lines.append(f'    graph.add_edge(START, "{start_func}")')

    # Add regular edges
    for edge in graph.edges:
        # Skip edges from start node (already handled)
        if edge.source_node_id == graph.start_node_id and not edge.source_handle:
            continue

        source_func, _ = _get_node_names(edge.source_node_id, node_name_map)
        target_func, _ = _get_node_names(edge.target_node_id, node_name_map)

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
        end_func, _ = _get_node_names(end_node_id, node_name_map)
        lines.append(f'    graph.add_edge("{end_func}", END)')

    # Use start node's name for example input
    start_func, _ = _get_node_names(graph.start_node_id, node_name_map) if graph.start_node_id else ("start", "")

    lines.extend([
        "",
        "    return graph.compile()",
        "",
        "",
        'if __name__ == "__main__":',
        "    workflow = build_graph()",
        f"    # Example: provide input for the start node",
        f'    initial_state: GraphState = {{"{start_func}": {{}}}}',
        "    result = workflow.invoke(initial_state)",
        "    print(result)",
        "",
    ])

    content = "\n".join(lines)
    output_path = output_dir / "graph.py"
    output_path.write_text(content, encoding="utf-8")
    print(f"Generated: {output_path}")


def translate(
    input_file: Path,
    output_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Translate a Dify DSL file to LangGraph code.

    Args:
        input_file: Path to the Dify DSL YAML file.
        output_dir: Directory to write generated files.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    print(f"Parsing: {input_file}")

    parser = DifyDSLParser()
    graph = parser.parse_file(input_file)

    print(f"Found {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    print(f"Start node: {graph.start_node_id}")
    print(f"End nodes: {graph.end_node_ids}")

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate files
    generate_state_file(graph, output_dir, node_name_map)
    generate_nodes_directory(graph, output_dir, node_name_map)
    generate_graph_file(graph, output_dir, node_name_map)

    # Copy template files
    copy_templates(output_dir)

    print(f"\nGeneration complete. Output directory: {output_dir}")


def copy_templates(output_dir: Path) -> None:
    """Copy template files to output directory.

    Args:
        output_dir: Directory to copy templates to.
    """
    if not TEMPLATES_DIR.exists():
        return

    for template_file in TEMPLATES_DIR.glob("*.py"):
        dest = output_dir / template_file.name
        shutil.copy(template_file, dest)
        print(f"Copied: {dest}")


def main() -> int:
    """Main entry point for CLI."""
    arg_parser = argparse.ArgumentParser(
        description="Convert Dify workflow DSL to LangGraph Python code"
    )
    arg_parser.add_argument(
        "input",
        type=Path,
        help="Path to the Dify DSL YAML file",
    )
    arg_parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("outputs"),
        help="Output directory for generated files (default: outputs)",
    )
    arg_parser.add_argument(
        "--name-nodes",
        action="store_true",
        help="Use LLM to generate meaningful Python names from node titles",
    )
    arg_parser.add_argument(
        "--llm-provider",
        type=str,
        default="openai",
        help="LLM provider for node naming (default: openai)",
    )
    arg_parser.add_argument(
        "--llm-model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model for node naming (default: gpt-4o-mini)",
    )
    arg_parser.add_argument(
        "--skip-implement",
        action="store_true",
        help="Skip LLM-based node implementation generation (only generate templates)",
    )

    args = arg_parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        return 1

    # Create subdirectory based on input filename
    input_name = args.input.stem  # e.g., "simple_workflow" from "simple_workflow.yml"
    output_dir = args.output / input_name

    try:
        # Parse the workflow first to get node info
        dsl_parser = DifyDSLParser()
        graph = dsl_parser.parse_file(args.input)

        # Create engine if needed for naming or implementation
        engine = None
        if args.name_nodes or not args.skip_implement:
            from generator import CodeGenerationEngine

            engine = CodeGenerationEngine.from_config(
                args.llm_provider,
                args.llm_model,
            )

        # Generate node names if requested
        node_name_map: dict[str, tuple[str, str]] | None = None
        if args.name_nodes and engine:
            print("Generating node names using LLM...")
            nodes_info = [
                {"id": n.id, "title": n.title, "type": n.type}
                for n in graph.nodes.values()
            ]
            node_names = engine.generate_node_names(nodes_info)
            node_name_map = {
                n.node_id: (n.snake_case, n.camel_case)
                for n in node_names
            }
            print(f"Generated {len(node_name_map)} node names")

        translate(args.input, output_dir, node_name_map)

        # Generate node implementations unless skipped
        if not args.skip_implement:
            print("Generating node implementations using LLM...")
            nodes_dir = output_dir / "nodes"
            assert engine is not None
            implementations = engine.generate_all_nodes(nodes_dir)
            print(f"Generated {len(implementations)} node implementations")

        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
