"""Generators for what the generated package needs in order to run.

The package is plain Python, meant to be dropped into whatever environment the
recipient already has. That left one thing unsaid: *which* third-party packages it
needs. On a clean machine `python -m <pkg>` failed with
``ModuleNotFoundError: No module named 'langgraph'`` and nothing in the output said
what to install.

Two files close that. ``requirements.txt`` names the dependencies, and a
``Dockerfile`` builds an image that runs the package as-is, for a recipient who would
rather not touch their own Python installation at all.

The dependency list is short because the generated code keeps it short: provider
SDKs are imported inside the function that needs them (see templates/llm.py), so a
workflow that never calls a model never needs one, and the Retriever uses only the
standard library.
"""

from pathlib import Path

from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import WorkflowGraph

logger = get_logger(__name__)

# Imported at module level by the generated package, so always required. Measured by
# running a generated package in an empty virtualenv: these three, and nothing else,
# are enough for it to build the graph and run to completion.
BASE_REQUIREMENTS = (
    "langgraph",
    "langchain-core",
    "python-dotenv",
)

# One per provider the generated llm.py can reach, keyed by the value of the
# LLM_PROVIDER environment variable that selects it. Listed as comments rather than
# requirements: each is imported lazily, so only the provider actually used is needed,
# and installing four SDKs to run one workflow would be absurd.
PROVIDER_REQUIREMENTS = {
    "openai": "langchain-openai",
    "anthropic": "langchain-anthropic",
    "google": "langchain-google-genai",
    "bedrock": "langchain-aws",
}

# No version pins, deliberately. The generated package is normally dropped into an
# environment that already has its own versions of these, and a pin would fight that
# for no benefit -- the generated code uses only long-stable API (StateGraph, Command,
# BaseChatModel).
_DOCKER_PYTHON_IMAGE = "python:3.13-slim"


def generate_requirements_file(graph: WorkflowGraph, output_dir: Path) -> None:
    """Write ``requirements.txt`` for the generated package.

    Args:
        graph: Parsed workflow graph, to tell whether any node may call a model.
        output_dir: The generated package's directory.
    """
    uses_model = any(node.type in {"llm", "agent"} for node in graph.nodes.values())

    lines = [
        "# Dependencies of this generated workflow package.",
        "#",
        "#     pip install -r requirements.txt",
        "#",
        "# Unpinned on purpose: this package is normally dropped into an environment",
        "# that already has its own versions, and it uses only long-stable API.",
        "",
        *BASE_REQUIREMENTS,
    ]

    if uses_model:
        lines += [
            "",
            "# This workflow has nodes that call a language model. Add the one line",
            "# matching the provider you use -- they are imported only when called, so",
            "# you need exactly one. Select it at run time with LLM_PROVIDER.",
        ]
        lines += [
            f"# {package}    # LLM_PROVIDER={provider}"
            for provider, package in sorted(PROVIDER_REQUIREMENTS.items())
        ]

    content = "\n".join(lines).rstrip("\n") + "\n"
    output_path = output_dir / "requirements.txt"
    # newline="\n": see state_generator for why every generated write pins it.
    output_path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Generated: %s", output_path)


def generate_dockerfile(package_name: str, output_dir: Path) -> None:
    """Write a ``Dockerfile`` that runs the generated package.

    The build context is the package directory itself, so the whole thing is one
    self-contained folder: `docker build` inside it needs nothing from outside.

    Args:
        package_name: The package's directory name, which is also its import name.
        output_dir: The generated package's directory.
    """
    lines = [
        "# Run this generated workflow as a container. Build from inside this folder:",
        "#",
        f"#     docker build -t {package_name} .",
        f"#     docker run --rm {package_name}",
        "#",
        "# Pass inputs and credentials with an .env file or -e:",
        "#",
        f"#     docker run --rm --env-file .env {package_name}",
        "#",
        "# Nodes whose body is still a TODO return placeholder values, so a fresh",
        "# conversion runs end to end but does not do the real work yet.",
        "",
        f"FROM {_DOCKER_PYTHON_IMAGE}",
        "",
        "# Keep the image quiet and tidy: no .pyc files written into the layer, and",
        "# output not buffered so logs appear as the workflow runs.",
        "ENV PYTHONDONTWRITEBYTECODE=1 \\",
        "    PYTHONUNBUFFERED=1 \\",
        "    PYTHONUTF8=1",
        "",
        "WORKDIR /app",
        "",
        "# Dependencies first, so editing node bodies does not re-install them.",
        f"COPY requirements.txt /app/{package_name}/requirements.txt",
        f"RUN pip install --no-cache-dir -r /app/{package_name}/requirements.txt",
        "",
        f"COPY . /app/{package_name}/",
        "",
        "# Not root: nothing here needs it.",
        "RUN useradd --create-home --uid 1000 app && chown -R app:app /app",
        "USER app",
        "",
        "# The package is imported by name from its parent directory, which is why",
        "# WORKDIR is /app rather than the package itself.",
        f'CMD ["python", "-m", "{package_name}"]',
    ]

    content = "\n".join(lines).rstrip("\n") + "\n"
    output_path = output_dir / "Dockerfile"
    output_path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Generated: %s", output_path)
