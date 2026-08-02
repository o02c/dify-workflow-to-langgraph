# Development Guide

This guide covers setting up the development environment and contributing to dify2langgraph.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

## Setup

### Clone and Install

```bash
git clone https://github.com/o02c/dify-workflow-to-langgraph.git
cd dify-workflow-to-langgraph
uv sync
```

### Verify Installation

```bash
uv run dify2langgraph --help
uv run pytest
```

## Project Structure

```
dify-workflow-to-langgraph/
├── src/dify2langgraph/    # Main package source
├── tests/                  # Test files
│   ├── fixtures/          # Test data files
│   ├── conftest.py        # Shared fixtures
│   └── test_*.py          # Test modules
├── templates/             # Output templates
├── docs/                  # Documentation
├── pyproject.toml         # Project configuration
└── README.md
```

## Development Workflow

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/dify2langgraph --cov-report=html

# Run specific test file
uv run pytest tests/test_parser.py

# Run with verbose output
uv run pytest -v
```

### Code Quality

```bash
# Run linter
uv run ruff check .

# Fix auto-fixable issues
uv run ruff check . --fix

# Run type checker
uv run ty check .
```

### Running the CLI

```bash
# Basic usage
uv run dify2langgraph workflow.yml

# With output directory
uv run dify2langgraph workflow.yml -o output/

# Skip LLM implementation
uv run dify2langgraph workflow.yml --skip-implement

# With LLM node naming
uv run dify2langgraph workflow.yml --name-nodes

# Run linters on output
uv run dify2langgraph workflow.yml --lint
```

## Writing Tests

### Test Structure

Tests are organized by module:

```python
# tests/test_module.py

import pytest
from dify2langgraph.module import function_to_test


class TestFunctionName:
    """Tests for function_name."""

    def test_basic_case(self):
        """Test with basic input."""
        result = function_to_test("input")
        assert result == "expected"

    def test_edge_case(self):
        """Test with edge case input."""
        result = function_to_test("")
        assert result is None
```

### Using Fixtures

```python
# tests/test_example.py

def test_with_fixture(temp_output_dir, parsed_simple_workflow):
    """Test using shared fixtures."""
    from dify2langgraph.codegen import generate_state_file

    generate_state_file(parsed_simple_workflow, temp_output_dir)

    state_file = temp_output_dir / "state.py"
    assert state_file.exists()
```

### Adding New Fixtures

Add fixtures to `tests/conftest.py`:

```python
@pytest.fixture
def my_fixture():
    """Description of fixture."""
    # Setup
    resource = create_resource()
    yield resource
    # Teardown
    resource.cleanup()
```

## Code Style

### Python Style

- Follow [PEP 8](https://pep8.org/) with line length of 100
- Use type hints for function signatures
- Write docstrings for all public functions

### Example

```python
def process_data(
    input_text: str,
    options: dict[str, Any] | None = None,
) -> ProcessResult:
    """Process input text and return result.

    Args:
        input_text: The text to process.
        options: Optional processing options.

    Returns:
        ProcessResult with the processed data.

    Raises:
        ValueError: If input_text is empty.

    Examples:
        >>> result = process_data("hello")
        >>> result.output
        'HELLO'
    """
    if not input_text:
        raise ValueError("input_text cannot be empty")

    # Implementation
    ...
```

### Imports

Organize imports in this order:

1. Standard library
2. Third-party packages
3. Local imports

```python
# Standard library
import json
from pathlib import Path

# Third-party
from langchain_core.messages import HumanMessage
from langgraph.types import Command

# Local
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser import DifyDSLParser
```

### Logging

Use the configured logger, not print:

```python
from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)

def my_function():
    logger.info("Processing started")
    logger.debug("Debug details: %s", details)
    logger.error("Error occurred: %s", error)
```

## Adding Features

### 1. Create a Branch

```bash
git checkout -b feature/my-feature
```

### 2. Implement Feature

- Write tests first (TDD)
- Implement the feature
- Update documentation

### 3. Run Quality Checks

```bash
uv run pytest
uv run ruff check .
uv run ty check .
```

### 4. Submit Pull Request

- Write clear commit messages
- Reference any related issues
- Request review

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG uv run dify2langgraph workflow.yml
```

### Using pdb

```python
import pdb; pdb.set_trace()  # Add breakpoint
```

### VS Code Debugging

Create `.vscode/launch.json`:

```json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Run CLI",
            "type": "debugpy",
            "request": "launch",
            "module": "dify2langgraph.cli",
            "args": ["workflow.yml", "--skip-implement"],
            "cwd": "${workspaceFolder}"
        },
        {
            "name": "Run Tests",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": ["-v"],
            "cwd": "${workspaceFolder}"
        }
    ]
}
```

## Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG (if exists)
3. Create release commit
4. Tag release
5. Push to repository

```bash
# Update version
# Edit pyproject.toml

# Commit and tag
git commit -am "Release v0.2.0"
git tag v0.2.0
git push origin main --tags
```
