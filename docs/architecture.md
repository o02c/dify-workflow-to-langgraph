# Architecture

This document describes the architecture of dify2langgraph.

> Terms are defined in [CONTEXT.md](../CONTEXT.md); design decisions and their rationale
> live in [docs/adr/](./adr/). Where this document and an ADR disagree, the ADR wins.

## Overview

dify2langgraph converts Dify workflow DSL files into LangGraph Python code. The conversion process follows a pipeline architecture:

```
Dify DSL YAML → Parser → Workflow Graph → Code Generator → Python Files
```

## Package Structure

```
src/dify2langgraph/
├── __init__.py           # Package entry point
├── cli.py                # Command-line interface
├── naming.py             # Canonical node-name/state-key utilities (leaf module)
├── logging_config.py     # Centralized logging configuration
├── observability.py      # LangSmith tracing integration
├── parser/               # DSL parsing module
│   ├── __init__.py
│   └── dsl_parser.py     # YAML parser and data models
├── codegen/              # Code generation module
│   ├── __init__.py
│   ├── naming.py         # Python naming utilities
│   ├── handlers.py       # Node Handler registry (per-type knowledge, ADR-0005)
│   ├── routing.py        # Structural branch-map helpers (ADR-0003)
│   ├── state_generator.py    # GraphState generation
│   ├── node_generator.py     # Node file generation
│   ├── graph_generator.py    # Graph construction code
│   └── package_generator.py  # __init__.py / __main__.py (self-contained package, ADR-0007)
├── generator/            # LLM-based code generation
│   ├── __init__.py
│   └── engine.py         # Code generation engine
├── llm/                  # LLM provider interfaces
│   ├── __init__.py
│   ├── base.py           # Base provider interface
│   ├── openai.py         # OpenAI provider
│   ├── anthropic.py      # Anthropic provider
│   └── bedrock.py        # AWS Bedrock provider
├── agents/               # LangGraph agents (opt-in post-processing, ADR-0001)
│   ├── __init__.py
│   ├── linter.py         # Linting utilities
│   └── coding_graph.py   # Auto-fix coding agent
└── templates/            # Runtime templates copied into generated output
    └── llm.py
```

## Components

### Parser Module

The parser module (`dify2langgraph.parser`) is responsible for:

1. **YAML Parsing**: Reading Dify DSL YAML files
2. **Node Extraction**: Extracting node information (ID, type, title, config)
3. **Edge Parsing**: Extracting edge connections between nodes
4. **Variable Reference Detection**: Finding `{{#node.field#}}` references
5. **Dependency Graph**: Building a dependency graph from references

Key classes:
- `DifyDSLParser`: Main parser class
- `WorkflowGraph`: Parsed workflow representation
- `NodeInfo`: Individual node information
- `EdgeInfo`: Edge connection information
- `VariableReference`: Variable reference representation

### Code Generation Module

The codegen module (`dify2langgraph.codegen`) generates Python code:

1. **Naming**: Converting node IDs to valid Python identifiers
2. **State Generation**: Creating `state.py` with TypedDict definitions
3. **Node Generation**: Creating individual node files in `nodes/`
4. **Graph Generation**: Creating `graph.py` with StateGraph construction

Key functions:
- `generate_state_file()`: Generate state.py
- `generate_nodes_directory()`: Generate nodes/ directory
- `generate_graph_file()`: Generate graph.py

### LLM Integration

The generator module uses LLM providers to:

1. **Name Generation**: Generate meaningful Python names from node titles
2. **Implementation Generation**: Generate node implementation code

Supported providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude)
- AWS Bedrock (Claude via AWS)

### Agents Module

The agents module provides LangGraph-based agents:

1. **Linter**: Run ruff and ty on generated code
2. **Coding Agent**: Automatically fix lint errors using LLM

## Data Flow

### Parsing Phase

```
YAML File
    ↓
DifyDSLParser.parse_file()
    ↓
WorkflowGraph {
    nodes: dict[str, NodeInfo]
    edges: list[EdgeInfo]
    start_node_id: str
    end_node_ids: list[str]
}
```

### Code Generation Phase

```
WorkflowGraph
    ↓
├── generate_state_file() → state.py
├── generate_nodes_directory() → nodes/*.py
├── generate_graph_file() → graph.py
└── generate_package_files() → __init__.py, __main__.py
```

The output is a self-contained package with relative imports, run via
`python -m <package>` ([ADR-0007](./adr/0007-generated-output-is-a-self-contained-package.md)).

### Optional LLM Enhancement

```
WorkflowGraph + LLM
    ↓
├── generate_node_names() → Meaningful Python names
└── generate_all_nodes() → Implemented node code
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `LOG_FORMAT` | Log format (`console` or `json`) | `console` |
| `LANGSMITH_TRACING` | Enable LangSmith tracing | `false` |
| `LANGSMITH_API_KEY` | LangSmith API key | - |
| `LANGSMITH_PROJECT` | LangSmith project name | `dify2langgraph` |

### LLM Provider Configuration

LLM providers are configured via environment variables:

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Bedrock: AWS credentials via standard AWS configuration

## Extension Points

### Adding New Node Types

Per [ADR-0005](./adr/0005-node-type-handler-registry.md), per-type knowledge lives in **one
Node Handler** in `codegen/handlers.py`. To support a new type, add a `NodeHandler` subclass
that sets `node_type` and overrides `output_fields()` (and, for a Branching Node, sets
`is_branching` / `decision_field` and overrides `stub_output()`), then register it in
`_HANDLERS`. The generators pick it up automatically via `get_handler()`; an unregistered type
falls back to the base handler's generic typed Stub. Structural branch-map derivation (from the
DSL `sourceHandle`) stays type-agnostic in `codegen/routing.py`.

### Adding New LLM Providers

1. Create provider class implementing `LLMProvider` interface
2. Register provider in `llm/__init__.py`
3. Add configuration in documentation

## Testing

Tests are organized in `tests/`:

- `conftest.py`: Shared fixtures
- `test_parser.py`: Parser module tests
- `test_handlers.py`: Node Handler registry tests (output fields, branching, stub bodies)
- `test_translator.py`: Code generation tests (source compiles / contains expected strings)
- `test_generated.py`: End-to-end tests that build and invoke the generated graph in a subprocess, including real workflow exports
- `fixtures/`: Test YAML files (see `fixtures/SOURCES.md` for provenance)
