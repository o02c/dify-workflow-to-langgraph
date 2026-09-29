"""Dify variable-type vocabulary, for code generation.

The canonical implementation lives in the dependency-free leaf module
:mod:`dify2langgraph.var_types` so the parser can share it without an import cycle.
This module re-exports it for code that imports from ``codegen``.
"""

from dify2langgraph.var_types import annotation, is_known

__all__ = [
    "annotation",
    "is_known",
]
