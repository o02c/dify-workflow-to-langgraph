"""Naming utilities: canonical Python names for Dify node IDs.

This is a dependency-free leaf module so both the parser and the code generators
can share one definition of the canonical state key (``state["node_<id>"]``)
without an import cycle.
"""

import keyword

from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)


def sanitize_function_name(node_id: str) -> str:
    """Convert node ID to valid Python function name (the canonical state key).

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



def usable_node_names(
    raw: dict[str, tuple[str, str]],
    known_node_ids: set[str] | None = None,
) -> dict[str, tuple[str, str]]:
    """Keep only the supplied node names that can actually be emitted.

    `--name-nodes` asks a model for the names, so they arrive unvalidated. An empty
    or non-identifier name is not a cosmetic problem: it produced a node file called
    literally `.py`, a `graph.add_node("", )` line, and an `__init__.py` that does not
    parse -- the whole generated package broken, with nothing said at conversion time.

    Anything rejected is logged and falls back to the canonical `node_<id>` name, so
    the run still produces a working package.

    Args:
        raw: node id -> (snake_case, CamelCase), as supplied.
        known_node_ids: The workflow's node ids, when available, so a name for a node
            that is not in the graph can be reported rather than silently ignored.

    Returns:
        The usable subset.
    """
    usable: dict[str, tuple[str, str]] = {}
    for node_id, names in raw.items():
        if known_node_ids is not None and node_id not in known_node_ids:
            logger.warning(
                "Ignoring a generated name for %r, which is not a node in this "
                "workflow.",
                node_id,
            )
            continue
        if not isinstance(names, tuple | list) or len(names) != 2:
            logger.warning("Ignoring a malformed generated name for %r: %r", node_id, names)
            continue
        snake, camel = names
        bad = [
            label
            for label, value in (("snake_case", snake), ("CamelCase", camel))
            if not isinstance(value, str)
            or not value.isidentifier()
            or keyword.iskeyword(value)
        ]
        if bad:
            logger.warning(
                "Ignoring the generated name for %r: %s is not a usable Python name "
                "(%r / %r). Falling back to node_%s.",
                node_id,
                " and ".join(bad),
                snake,
                camel,
                node_id,
            )
            continue
        usable[node_id] = (snake, camel)
    return usable
