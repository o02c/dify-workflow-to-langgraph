"""Dify's variable-type vocabulary, translated to Python annotations.

A dependency-free leaf module, for the same reason :mod:`dify2langgraph.naming` and
:mod:`dify2langgraph.env_vars` are: several places need this answer and must agree.
Before it existed, each place carried its own two-branch guess -- Start variables
were `"float" if number else "str"`, so a `file-list` input was annotated `str` --
and each guess was fitted to whichever types the fixtures happened to contain.

Dify uses one vocabulary in several dialects, and this module accepts all of them:

- node output declarations (`code`'s `data.outputs[*].type`): ``string``,
  ``number``, ``object``, ``boolean``, ``array[string|number|object|boolean]``
- End output / selector declarations (`value_type`): the same, plus ``array[file]``
- Start variable declarations (`data.variables[*].type`): ``text-input``,
  ``paragraph``, ``select``, ``number``, ``file``, ``file-list``
- environment variables (`value_type`): ``string``, ``integer``, ``float``,
  ``secret`` and the above

An unrecognised or absent type resolves to ``Any``. That case is not exotic: real
exports contain Start variables with no ``type`` key at all, and Dify adds node
types faster than any table can track. Guessing ``str`` would annotate a list as a
string and put ``"example"`` where a caller must pass a list.
"""

from typing import Any

# Dify type string -> Python annotation. Kept flat and explicit rather than parsed,
# so an unknown spelling falls through to Any instead of being half-understood.
_ANNOTATIONS = {
    # scalars, in the spellings Dify actually writes
    "string": "str",
    "text-input": "str",
    "paragraph": "str",
    "select": "str",
    "secret": "str",
    "number": "float",
    "integer": "int",
    "float": "float",
    "boolean": "bool",
    "object": "dict[str, Any]",
    # `file` is a Dify File object. The generated package is detached from Dify, so
    # there is no such type to import: the caller passes whatever their own code
    # uses. Any says that honestly; `str` would not.
    "file": "Any",
    "file-list": "list[Any]",
    # arrays
    "array": "list[Any]",
    "array[string]": "list[str]",
    "array[number]": "list[float]",
    "array[boolean]": "list[bool]",
    "array[object]": "list[dict[str, Any]]",
    "array[file]": "list[Any]",
}


def annotation(dify_type: Any) -> str:
    """The Python annotation for a Dify type string.

    Args:
        dify_type: A type string from the DSL, or None/absent.

    Returns:
        A Python type annotation. ``Any`` when the type is absent or not one this
        module knows -- deliberately, rather than defaulting to a scalar.

    Examples:
        >>> annotation("array[object]")
        'list[dict[str, Any]]'
        >>> annotation("file-list")
        'list[Any]'
        >>> annotation(None)
        'Any'
    """
    if not isinstance(dify_type, str):
        return "Any"
    return _ANNOTATIONS.get(dify_type.strip(), "Any")


def is_known(dify_type: Any) -> bool:
    """Whether this module recognises the type string.

    Lets a caller warn about a vocabulary Dify has extended, instead of silently
    treating it as unknown.

    Args:
        dify_type: A type string from the DSL, or None/absent.

    Returns:
        True when the type maps to something more specific than ``Any``.
    """
    return isinstance(dify_type, str) and dify_type.strip() in _ANNOTATIONS
