"""Base state classes for LangGraph node outputs.

This module provides the foundational TypedDict classes used for
type-safe state management in generated LangGraph workflows.
"""

from typing import Any, TypedDict


class NodeOutput(TypedDict, total=False):
    """Base class for node output data.

    All node outputs inherit from this class to ensure consistent
    structure and enable type checking for field access.

    Attributes:
        text: Common output field for text-based results.
        data: Generic data payload for complex outputs.
        error: Error message if node execution failed.
    """

    text: str
    data: Any
    error: str | None


class LLMOutput(NodeOutput):
    """Output structure for LLM nodes.

    Attributes:
        text: Generated text response from the LLM.
        usage: Token usage statistics.
    """

    usage: dict[str, int]


class KnowledgeRetrievalOutput(NodeOutput):
    """Output structure for knowledge retrieval nodes.

    Attributes:
        records: List of retrieved document records.
        query: The query used for retrieval.
    """

    records: list[dict[str, Any]]
    query: str


class CodeOutput(NodeOutput):
    """Output structure for code execution nodes.

    Attributes:
        result: Execution result value.
        stdout: Standard output from execution.
        stderr: Standard error from execution.
    """

    result: Any
    stdout: str
    stderr: str


class ConditionOutput(NodeOutput):
    """Output structure for conditional branch nodes.

    Attributes:
        selected_branch: The ID of the selected branch.
    """

    selected_branch: str


class VariableAggregatorOutput(NodeOutput):
    """Output structure for variable aggregator nodes.

    Attributes:
        aggregated: The aggregated variable value.
    """

    aggregated: Any


class StartOutput(NodeOutput):
    """Output structure for start nodes.

    Attributes:
        inputs: User-provided input variables.
    """

    inputs: dict[str, Any]


class EndOutput(NodeOutput):
    """Output structure for end nodes.

    Attributes:
        outputs: Final workflow outputs.
    """

    outputs: dict[str, Any]
