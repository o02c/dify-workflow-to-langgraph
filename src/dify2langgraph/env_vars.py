"""Which DSL `environment_variables` become code, and under what names.

A dependency-free leaf module so the parser can apply the filter once, at parse
time, and every generator downstream sees the same list -- the same reason
:mod:`dify2langgraph.naming` is a leaf. Two places need this answer:
`env_generator`, which writes `env.py`, and the node generator, which decides
whether a node may reach `env.NAME`. When they disagreed the result was a package
that could not be imported at all, so they derive it from one place now.

Dify accepts any `[A-Za-z_]\\w*` as a variable name, which includes every Python
keyword, so a name cannot be pasted into generated source unchecked.
"""

import keyword
from typing import Any

from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)

SECRET_VALUE_TYPE = "secret"

# Names the generated env.py defines itself. A DSL variable that reuses one would
# either be silently overwritten or shadow a module the generated code calls --
# `os = 'x'` after `import os` compiles, then fails on the first secret read.
RESERVED_MODULE_NAMES = frozenset({
    "os",
    "TYPE_CHECKING",
    "find_dotenv",
    "load_dotenv",
    "REQUIRED_ENV_VARS",
})

# Secrets are read from the process environment under the DSL's own name, so one
# of these would resolve to the machine's value instead of the credential --
# silently, with no error anywhere. Warned about, not rejected: the name is the
# author's to choose, and a non-secret of the same name is harmless.
WELL_KNOWN_ENV_NAMES = frozenset({
    "HOME",
    "LANG",
    "PATH",
    "PWD",
    "SHELL",
    "TEMP",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "USERPROFILE",
})


def usable_variables(variables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The declared environment variables that can be emitted as Python.

    Anything rejected is logged with the reason: a malformed DSL should be
    visible, and silently dropping a variable the author declared turns into an
    unexplained missing value further downstream.

    Args:
        variables: The DSL's `environment_variables`, as parsed.

    Returns:
        The usable subset, in DSL order.
    """
    usable = []
    for var in variables:
        name = var.get("name")
        if not name or not isinstance(name, str):
            logger.warning("Skipping an environment variable with no name: %r", var)
            continue
        if not name.isidentifier() or keyword.iskeyword(name):
            logger.warning(
                "Skipping environment variable %r: not a usable Python name, so "
                "emitting it would make the generated package unimportable.",
                name,
            )
            continue
        if name in RESERVED_MODULE_NAMES:
            logger.warning(
                "Skipping environment variable %r: the generated env.py defines "
                "that name itself, so the two would collide.",
                name,
            )
            continue
        is_secret = var.get("value_type") == SECRET_VALUE_TYPE
        if not is_secret and "value" not in var:
            logger.warning(
                "Skipping environment variable %r: it declares no value and is "
                "not a secret, so there is nothing to emit.",
                name,
            )
            continue
        if is_secret and name in WELL_KNOWN_ENV_NAMES:
            logger.warning(
                "Secret %r shares its name with a standard environment variable, "
                "so it will silently resolve to the machine's value rather than "
                "the credential. Rename it in the Dify app.",
                name,
            )
        usable.append(var)
    return usable


def declared_names(variables: list[dict[str, Any]]) -> set[str]:
    """The names `env.py` exposes.

    Args:
        variables: A parsed workflow's `environment_variables`, already filtered
            by :func:`usable_variables` (the parser does this once).

    Returns:
        The set of names.
    """
    return {str(var["name"]) for var in variables}
