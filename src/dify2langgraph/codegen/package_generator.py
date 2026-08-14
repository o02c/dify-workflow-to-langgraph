"""Package-file generator for the generated LangGraph workflow.

Emits ``__init__.py`` and ``__main__.py`` so the generated output is a
self-contained Python package that uses relative imports (no ``sys.path`` hacks).
Run it with ``python -m <package>`` from the parent directory.
"""

from pathlib import Path

from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import WorkflowGraph

logger = get_logger(__name__)


def generate_package_files(
    graph: WorkflowGraph,
    output_dir: Path,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> None:
    """Generate ``__init__.py`` and ``__main__.py`` for the output package.

    Args:
        graph: Parsed workflow graph.
        output_dir: Directory to write the generated files (the package root).
        node_name_map: Optional mapping of node_id -> (snake_case, CamelCase).
    """
    init_content = "\n".join([
        '"""Generated LangGraph workflow package.',
        "",
        "This package is auto-generated. Run it with `python -m <package>`.",
        '"""',
        "",
        "from .graph import build_graph",
        "",
        '__all__ = ["build_graph"]',
        "",
    ])
    (output_dir / "__init__.py").write_text(init_content, encoding="utf-8")

    # Entry point: build the graph and invoke it with an example initial state.
    if graph.start_node_id:
        start_func, _ = get_node_names(graph.start_node_id, node_name_map)
    else:
        start_func = "start"

    main_content = "\n".join([
        '"""Entry point: `python -m <package>` builds and runs the workflow."""',
        "",
        "from .graph import build_graph",
        "from .state import GraphState",
        "",
        "workflow = build_graph()",
        "# Example: provide input for the start node.",
        f'initial_state: GraphState = {{"{start_func}": {{}}}}',
        "result = workflow.invoke(initial_state)",
        "print(result)",
        "",
    ])
    (output_dir / "__main__.py").write_text(main_content, encoding="utf-8")

    logger.info("Generated: %s/__init__.py, __main__.py", output_dir)
