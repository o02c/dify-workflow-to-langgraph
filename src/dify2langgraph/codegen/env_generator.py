"""Generator for the generated package's environment-constants module.

ADR-0004 gives Dify's `env.*` namespace a home *outside* state: the DSL's
`environment_variables` are constants, not per-run values, so they become module
constants rather than a `GraphState` key.

Secrets are the exception. A `value_type: secret` variable exports its **value in
plaintext**, so emitting it as a constant would write a credential into source the
customer then commits. Those are read from the process environment instead, on
first access, and a missing one raises with the variable named.
"""

from pathlib import Path

from dify2langgraph.codegen.env_vars import SECRET_VALUE_TYPE
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import WorkflowGraph

logger = get_logger(__name__)


def generate_env_file(graph: WorkflowGraph, output_dir: Path) -> bool:
    """Generate ``env.py`` when the workflow declares environment variables.

    Args:
        graph: Parsed workflow graph.
        output_dir: Directory to write the generated file (the package root).

    Returns:
        True if a file was written, False when the DSL declares none.
    """
    # Already filtered by the parser to what can be emitted (see env_vars).
    variables = graph.environment_variables
    if not variables:
        return False

    constants = [v for v in variables if v.get("value_type") != SECRET_VALUE_TYPE]
    secrets = [v for v in variables if v.get("value_type") == SECRET_VALUE_TYPE]

    lines = [
        '"""Environment variables declared in the Dify DSL.',
        "",
        "This file is auto-generated. Do not edit directly.",
        "",
        "Non-secret values are constants copied from the DSL. Secrets are not: Dify",
        "exports their value in plaintext, so writing it here would put a credential",
        "into source. They are read from the environment on first access instead",
        "(ADR-0004).",
        '"""',
        "",
    ]

    if secrets:
        lines += [
            "import os",
            "from typing import TYPE_CHECKING",
            "",
            "from dotenv import find_dotenv, load_dotenv",
            "",
        ]

    for var in constants:
        # repr covers every value_type Dify's variable factory accepts: string,
        # number, integer, float, boolean, object, array[string|number|object|
        # boolean] and `llm`. Not all of them are scalars -- an `object` or
        # `array[*]` becomes a mutable module-level constant, and an `llm`
        # variable becomes the raw {provider, name, mode, completion_params} dict
        # rather than a resolved model. Both are faithful to the DSL; neither is
        # interpreted further.
        lines.append(f"{var['name']} = {var['value']!r}  # value_type: {var.get('value_type')}")
    if constants:
        lines.append("")

    if secrets:
        names = ", ".join(repr(var["name"]) for var in secrets)
        trailing = "," if len(secrets) == 1 else ""
        lines += [
            "# Declared as `secret` in the DSL: supplied through the environment at",
            "# run time rather than baked in here. Every name listed must be set",
            "# before the workflow runs. Public on purpose -- a caller can check the",
            "# list up front instead of discovering a missing one mid-run.",
            f"REQUIRED_ENV_VARS = ({names}{trailing})",
            "",
            "# Read a .env before any secret is resolved. Without this, a secret written",
            "# to .env resolved only if llm.py -- which also calls load_dotenv -- happened",
            "# to be imported first, so the same .env worked or failed depending on import",
            "# order. Exported variables still win: load_dotenv does not override them.",
            "load_dotenv(find_dotenv())",
            "",
            "if TYPE_CHECKING:  # resolved at run time by __getattr__ below",
        ]
        lines += [f"    {var['name']}: str" for var in secrets]
        lines += [
            "",
            "",
            "def __getattr__(name: str) -> str:",
            '    """Resolve a secret from the environment when it is read (PEP 562).',
            "",
            "    Args:",
            "        name: The attribute being read.",
            "",
            "    Returns:",
            "        The environment variable's value.",
            "",
            "    Raises:",
            "        RuntimeError: If the workflow declares the secret but the",
            "            environment leaves it unset or empty. Failing here names",
            "            the variable; passing an empty credential on would surface",
            "            later as an unexplained error from whatever consumed it.",
            "        AttributeError: For any other attribute.",
            '    """',
            "    if name in REQUIRED_ENV_VARS:",
            "        value = os.environ.get(name)",
            "        if not value:",
            "            raise RuntimeError(",
            '                f"environment variable {name!r} is required by this workflow "',
            '                "(declared as a secret in the Dify DSL) but is not set"',
            "            )",
            "        return value",
            '    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")',
            "",
            "",
            "def __dir__() -> list[str]:",
            '    """List the secrets alongside the constants (PEP 562).',
            "",
            "    Returns:",
            "        Every name this module exposes. Without this, the secrets are",
            "        invisible to ``dir()`` and to interactive completion, because",
            "        they exist only inside __getattr__.",
            '    """',
            "    return sorted({*globals(), *REQUIRED_ENV_VARS})",
        ]

    content = "\n".join(lines).rstrip("\n") + "\n"
    output_path = output_dir / "env.py"
    # newline="\n": see state_generator for why every generated write pins it.
    output_path.write_text(content, encoding="utf-8", newline="\n")
    logger.info("Generated: %s (%d constants, %d secrets)", output_path, len(constants), len(secrets))
    return True
