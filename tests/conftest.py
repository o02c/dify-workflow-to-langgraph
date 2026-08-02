"""Shared pytest fixtures for dify2langgraph tests.

This module provides common fixtures used across test modules.
"""

import tempfile
from pathlib import Path

import pytest

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def simple_workflow_path(fixtures_dir: Path) -> Path:
    """Return the path to the simple workflow fixture."""
    return fixtures_dir / "simple_workflow.yml"


@pytest.fixture
def guardduty_workflow_path(fixtures_dir: Path) -> Path:
    """Return the path to the guardduty workflow fixture."""
    return fixtures_dir / "guardduty_handler.yml"


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory for tests.

    Yields:
        Path to temporary directory that is cleaned up after the test.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def parsed_simple_workflow(simple_workflow_path: Path):
    """Parse and return the simple workflow fixture.

    Returns:
        WorkflowGraph from the simple workflow.
    """
    from dify2langgraph.parser import DifyDSLParser

    parser = DifyDSLParser()
    return parser.parse_file(simple_workflow_path)


@pytest.fixture
def parsed_guardduty_workflow(guardduty_workflow_path: Path):
    """Parse and return the guardduty workflow fixture.

    Returns:
        WorkflowGraph from the guardduty workflow.
    """
    from dify2langgraph.parser import DifyDSLParser

    parser = DifyDSLParser()
    return parser.parse_file(guardduty_workflow_path)
