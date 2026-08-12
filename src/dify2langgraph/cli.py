"""CLI entry point for Dify DSL to LangGraph converter.

This module provides the command-line interface for the converter.
"""

import argparse
import shutil
import sys
from pathlib import Path

from dify2langgraph.codegen import (
    generate_graph_file,
    generate_nodes_directory,
    generate_package_files,
    generate_state_file,
)
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser import DifyDSLParser

logger = get_logger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"


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
    logger.info("Parsing: %s", input_file)

    parser = DifyDSLParser()
    graph = parser.parse_file(input_file)

    logger.info("Found %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    logger.info("Start node: %s", graph.start_node_id)
    logger.info("End nodes: %s", graph.end_node_ids)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate files
    generate_state_file(graph, output_dir, node_name_map)
    generate_nodes_directory(graph, output_dir, node_name_map)
    generate_graph_file(graph, output_dir, node_name_map)
    generate_package_files(graph, output_dir, node_name_map)

    # Copy template files
    copy_templates(output_dir)

    logger.info("Generation complete. Output directory: %s", output_dir)


def copy_templates(output_dir: Path) -> None:
    """Copy template files to output directory.

    Args:
        output_dir: Directory to copy templates to.
    """
    if not TEMPLATES_DIR.exists():
        return

    for template_file in TEMPLATES_DIR.glob("*.py"):
        # Skip dunder files (e.g. the templates package's own __init__.py) so we
        # don't clobber the generated package's __init__.py.
        if template_file.name.startswith("__"):
            continue
        dest = output_dir / template_file.name
        shutil.copy(template_file, dest)
        logger.info("Copied: %s", dest)


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
    arg_parser.add_argument(
        "--lint",
        action="store_true",
        help="Run linters (ruff, ty) on generated code",
    )
    arg_parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Use coding agent to automatically fix lint errors",
    )

    args = arg_parser.parse_args()

    if not args.input.exists():
        logger.error("Input file not found: %s", args.input)
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
            from dify2langgraph.generator import CodeGenerationEngine

            engine = CodeGenerationEngine.from_config(
                args.llm_provider,
                args.llm_model,
            )

        # Generate node names if requested
        node_name_map: dict[str, tuple[str, str]] | None = None
        if args.name_nodes and engine:
            logger.info("Generating node names using LLM...")
            nodes_info = [
                {"id": n.id, "title": n.title, "type": n.type}
                for n in graph.nodes.values()
            ]
            node_names = engine.generate_node_names(nodes_info)
            node_name_map = {
                n.node_id: (n.snake_case, n.camel_case)
                for n in node_names
            }
            logger.info("Generated %d node names", len(node_name_map))

        translate(args.input, output_dir, node_name_map)

        # Generate node implementations unless skipped
        if not args.skip_implement:
            logger.info("Generating node implementations using LLM...")
            nodes_dir = output_dir / "nodes"
            assert engine is not None
            implementations = engine.generate_all_nodes(nodes_dir)
            logger.info("Generated %d node implementations", len(implementations))

        # Run linters if requested
        if args.lint or args.auto_fix:
            from dify2langgraph.agents import lint_directory, print_lint_summary

            # First pass: run ruff with --fix for auto-fixable issues
            if args.auto_fix:
                logger.info("Running ruff --fix...")
                lint_directory(output_dir, tools=["ruff"], fix=True)

            logger.info("Running linters...")
            lint_results = lint_directory(output_dir, tools=["ruff"])
            all_passed = print_lint_summary(lint_results)

            # Use coding agent for remaining complex issues
            if args.auto_fix and not all_passed:
                from dify2langgraph.agents import fix_directory
                from dify2langgraph.templates.llm import get_chat_model

                logger.info("Running coding agent to fix remaining errors...")
                llm = get_chat_model(args.llm_provider, args.llm_model)
                fix_directory(output_dir, llm, max_iterations=3)

                # Re-run lint to verify fixes
                logger.info("Verifying fixes...")
                lint_results = lint_directory(output_dir, tools=["ruff"])
                print_lint_summary(lint_results)

        return 0
    except Exception as e:
        logger.error("Error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
