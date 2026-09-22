# Development Guide

This guide covers setting up the development environment and contributing to dify2langgraph.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) package manager

The library and CLI run on Windows, macOS and Linux. The dev *tooling* in this
guide is not fully portable: `Makefile` and `scripts/build-release.sh` need
`make` and bash, so on Windows either use WSL/Git Bash for those two or call the
underlying `uv run ...` commands directly. Everything else works as written once
environment variables are set with the shell's own syntax (see
[Debugging](#enable-debug-logging)).

Set `PYTHONUTF8=1` on Windows. Fixtures and generated code carry Japanese and
Chinese text, and without UTF-8 mode the console codepage (cp932 on Japanese
locales) garbles test output and CLI logs.

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
├── src/dify2langgraph/     # Main package source
│   └── templates/          # Sources copied verbatim into generated packages
├── tests/                  # Test files
│   ├── fixtures/           # Test data files
│   ├── conftest.py         # Shared fixtures
│   └── test_*.py           # Test modules
├── docs/                   # Documentation
├── scripts/                # Release archive, dependency quarantine, cross-platform checks
├── Dockerfile              # Converter image (ADR-0008)
├── compose.yaml            # Default mounts/env for running the image
├── pyproject.toml          # Project configuration
└── README.md
```

## Cross-platform verification

The converter is deterministic (ADR-0001), which means the same DSL must produce
byte-identical output whether it ran natively on macOS, natively on Windows, or in
the container. Two helpers make that checkable rather than assumed.

```bash
# Reference digest of a generated package. Same value on any platform.
make verify-digest
```

```powershell
# On a Windows host: run the checks that cannot be made from macOS/Linux --
# console code page, PowerShell env-var syntax, path separators, --mount with a
# drive letter -- and compare output against the digest above.
.\scripts\verify-windows.ps1 -ExpectedDigest <digest from make verify-digest>
```

`verify-windows.ps1` is written for Windows PowerShell 5.1 (still the default shell
on most Windows hosts), installs nothing, and skips groups it cannot run rather
than failing them.

Its only prerequisite is **uv** -- installing uv alone is enough, because uv
downloads CPython itself and needs no administrator rights:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

The Docker group is skipped when no daemon is reachable. Worth knowing before
planning that part: Docker Desktop for Windows requires WSL2, i.e. nested
virtualization, and in Parallels Desktop nested virtualization is a Pro/Business
feature -- on the Standard edition it cannot be enabled at all. The native checks
need no Docker and cover the failure modes that prompted this work.

Generated files are written with `newline="\n"` so they are LF on every platform.
Left to Python's default, a native Windows run would emit CRLF while the container
emitted LF, and the same DSL would produce byte-different output depending on how
the converter happened to be run. `TestGeneratedOutputIsByteStableAcrossPlatforms`
guards this.

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

### Updating Dependencies

```bash
make lock    # roll the quarantine forward, then re-resolve uv.lock
```

`pyproject.toml` carries `[tool.uv] exclude-newer`, a **dependency quarantine**: no
version published within the last 3 days is ever resolved, so nothing is adopted
before a yank or a compromised release has had time to be noticed. uv takes a fixed
timestamp, so `make lock` rewrites it (`scripts/refresh-quarantine.py`) before
locking. **Commit the `pyproject.toml` change together with `uv.lock`.**

Because the cutoff lives in `pyproject.toml` rather than in a `--exclude-newer`
flag, *every* uv command honours it — `uv lock`, `uv add`, `uv sync`, even
`uv lock --upgrade`. Passing the flag on the command line instead is not durable:
a later plain `uv sync` silently re-resolves past the cutoff and rewrites the lock.

The layered breakdown of what each dependency is for lives in
[docs/tech-stack.md](./tech-stack.md).

A side effect worth knowing: if nobody has run `make lock` for a while, `uv add`
will resolve the newest version *as of the recorded cutoff*, not today's. Run
`make lock` first if you need something more recent.

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

On Windows, set the variable first -- the inline `VAR=value command` form is
bash-only:

```powershell
$env:LOG_LEVEL = "DEBUG"
uv run dify2langgraph workflow.yml
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
