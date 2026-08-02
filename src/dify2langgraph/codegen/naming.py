"""Naming utilities for code generation.

This module provides functions for converting Dify node IDs to valid Python names.
"""


def sanitize_function_name(node_id: str) -> str:
    """Convert node ID to valid Python function name.

    Args:
        node_id: Original node ID.

    Returns:
        Sanitized function name.

    Examples:
        >>> sanitize_function_name("llm-node")
        'llm_node'
        >>> sanitize_function_name("123-start")
        'node_123_start'
    """
    # Replace hyphens and other invalid chars with underscores
    name = node_id.replace("-", "_").replace(" ", "_")
    # Ensure it doesn't start with a number
    if name[0].isdigit():
        name = f"node_{name}"
    return name


def sanitize_class_name(node_id: str) -> str:
    """Convert node ID to valid Python class name (PascalCase).

    Args:
        node_id: Original node ID.

    Returns:
        Sanitized class name in PascalCase.

    Examples:
        >>> sanitize_class_name("llm-node")
        'LlmNode'
        >>> sanitize_class_name("123-start")
        'Node123_start'
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


def get_node_names(
    node_id: str,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, str]:
    """Get function name and class name for a node.

    Args:
        node_id: Original node ID.
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).

    Returns:
        Tuple of (function_name, class_name).

    Examples:
        >>> get_node_names("llm-node")
        ('llm_node', 'LlmNodeOutput')
        >>> get_node_names("my_node", {"my_node": ("process_data", "ProcessData")})
        ('process_data', 'ProcessDataOutput')
    """
    if node_name_map and node_id in node_name_map:
        snake, camel = node_name_map[node_id]
        return snake, f"{camel}Output"
    return sanitize_function_name(node_id), sanitize_class_name(node_id) + "Output"
