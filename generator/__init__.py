"""Generator modules for Dify DSL parsing and code generation.

This package provides:
- parser: Dify DSL YAML parsing
- llm: LLM provider abstraction (Bedrock, OpenAI, Anthropic)
- engine: Code generation engine using LLM
"""

from .engine import CodeGenerationEngine, NodeImplementation, NodeName
from .llm import (
    LLMConfig,
    LLMProvider,
    LLMResponse,
    Message,
    available_providers,
    create_provider,
)
from .parser import DifyDSLParser, EdgeInfo, NodeInfo, VariableReference, WorkflowGraph

__all__ = [
    # Parser
    "DifyDSLParser",
    "EdgeInfo",
    "NodeInfo",
    "VariableReference",
    "WorkflowGraph",
    # LLM
    "LLMConfig",
    "LLMProvider",
    "LLMResponse",
    "Message",
    "available_providers",
    "create_provider",
    # Engine
    "CodeGenerationEngine",
    "NodeImplementation",
    "NodeName",
]
