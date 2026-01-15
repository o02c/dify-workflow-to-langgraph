"""YAML parser for Dify DSL workflows.

This module extracts node IDs and variable references from Dify
workflow DSL files, building a dependency graph for code generation.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# Pattern to match Dify variable references: {{#node_id.field#}} or {{#node_id.field.subfield#}}
VARIABLE_REFERENCE_PATTERN = re.compile(r"\{\{#([^#]+)#\}\}")


@dataclass
class VariableReference:
    """Represents a variable reference in Dify DSL.

    Attributes:
        raw: The original reference string (e.g., "node_id.field").
        node_id: The source node ID.
        field_path: List of field names forming the access path.
    """

    raw: str
    node_id: str
    field_path: list[str]

    @classmethod
    def parse(cls, reference: str) -> "VariableReference":
        """Parse a variable reference string.

        Args:
            reference: The reference string without {{ }} markers.

        Returns:
            A VariableReference instance.

        Examples:
            >>> ref = VariableReference.parse("llm_node.text")
            >>> ref.node_id
            'llm_node'
            >>> ref.field_path
            ['text']
        """
        parts = reference.split(".")
        return cls(raw=reference, node_id=parts[0], field_path=parts[1:])

    def to_state_access(self) -> str:
        """Convert to Python state dictionary access.

        Returns:
            Python code string for accessing the state.

        Examples:
            >>> ref = VariableReference.parse("llm_node.text")
            >>> ref.to_state_access()
            'state["llm_node"]["text"]'
        """
        access = f'state["{self.node_id}"]'
        for part in self.field_path:
            access += f'["{part}"]'
        return access


@dataclass
class NodeInfo:
    """Information about a single workflow node.

    Attributes:
        id: Unique node identifier.
        type: Node type (e.g., "llm", "code", "if-else").
        title: Human-readable node title.
        data: Raw node data from YAML.
        references: Variable references found in this node.
        dependencies: Set of node IDs this node depends on.
    """

    id: str
    type: str
    title: str
    data: dict[str, Any]
    references: list[VariableReference] = field(default_factory=list)
    dependencies: set[str] = field(default_factory=set)


@dataclass
class EdgeInfo:
    """Information about an edge between nodes.

    Attributes:
        source_node_id: The ID of the source node.
        target_node_id: The ID of the target node.
        source_handle: Optional handle identifier on source node.
        target_handle: Optional handle identifier on target node.
    """

    source_node_id: str
    target_node_id: str
    source_handle: str | None = None
    target_handle: str | None = None


@dataclass
class WorkflowGraph:
    """Represents the complete parsed workflow.

    Attributes:
        nodes: Dictionary mapping node IDs to NodeInfo.
        edges: List of edges connecting nodes.
        start_node_id: ID of the entry point node.
        end_node_ids: IDs of terminal nodes.
    """

    nodes: dict[str, NodeInfo]
    edges: list[EdgeInfo]
    start_node_id: str | None = None
    end_node_ids: list[str] = field(default_factory=list)


class DifyDSLParser:
    """Parser for Dify workflow DSL files."""

    def __init__(self):
        """Initialize the parser."""
        self._variable_pattern = VARIABLE_REFERENCE_PATTERN

    def parse_file(self, filepath: str | Path) -> WorkflowGraph:
        """Parse a Dify DSL YAML file.

        Args:
            filepath: Path to the YAML file.

        Returns:
            A WorkflowGraph instance.
        """
        filepath = Path(filepath)
        with filepath.open(encoding="utf-8") as f:
            dsl_data = yaml.safe_load(f)
        return self.parse(dsl_data)

    def parse(self, dsl_data: dict[str, Any]) -> WorkflowGraph:
        """Parse Dify DSL data.

        Args:
            dsl_data: Parsed YAML data as a dictionary.

        Returns:
            A WorkflowGraph instance.
        """
        # Extract workflow graph from DSL
        graph_data = dsl_data.get("workflow", dsl_data).get("graph", {})
        nodes_data = graph_data.get("nodes", [])
        edges_data = graph_data.get("edges", [])

        # Parse nodes
        nodes = {}
        start_node_id = None
        end_node_ids = []

        for node_data in nodes_data:
            node_info = self._parse_node(node_data)
            nodes[node_info.id] = node_info

            if node_info.type == "start":
                start_node_id = node_info.id
            elif node_info.type == "end":
                end_node_ids.append(node_info.id)

        # Parse edges
        edges = [self._parse_edge(edge_data) for edge_data in edges_data]

        return WorkflowGraph(
            nodes=nodes,
            edges=edges,
            start_node_id=start_node_id,
            end_node_ids=end_node_ids,
        )

    def _parse_node(self, node_data: dict[str, Any]) -> NodeInfo:
        """Parse a single node from YAML data.

        Args:
            node_data: Node dictionary from YAML.

        Returns:
            A NodeInfo instance.
        """
        node_id = node_data.get("id", "")
        node_type = node_data.get("data", {}).get("type", "unknown")
        node_title = node_data.get("data", {}).get("title", node_id)
        data = node_data.get("data", {})

        # Extract variable references from the entire node data
        references = self._extract_references(node_data)

        # Build dependencies from references
        dependencies = {ref.node_id for ref in references}

        return NodeInfo(
            id=node_id,
            type=node_type,
            title=node_title,
            data=data,
            references=references,
            dependencies=dependencies,
        )

    def _parse_edge(self, edge_data: dict[str, Any]) -> EdgeInfo:
        """Parse an edge from YAML data.

        Args:
            edge_data: Edge dictionary from YAML.

        Returns:
            An EdgeInfo instance.
        """
        return EdgeInfo(
            source_node_id=edge_data.get("source", ""),
            target_node_id=edge_data.get("target", ""),
            source_handle=edge_data.get("sourceHandle"),
            target_handle=edge_data.get("targetHandle"),
        )

    def _extract_references(self, data: Any) -> list[VariableReference]:
        """Recursively extract variable references from data.

        Handles two reference formats:
        1. Template format: {{#node_id.field#}}
        2. Selector format: value_selector: [node_id, field, ...]
           or variable_selector: [node_id, field, ...]

        Args:
            data: Any data structure (dict, list, or string).

        Returns:
            List of VariableReference found in the data.
        """
        references = []

        if isinstance(data, str):
            matches = self._variable_pattern.findall(data)
            for match in matches:
                references.append(VariableReference.parse(match))
        elif isinstance(data, dict):
            # Check for value_selector or variable_selector format
            for key, value in data.items():
                if key in ("value_selector", "variable_selector", "query_variable_selector"):
                    if isinstance(value, list) and len(value) >= 1:
                        # First element is node_id, rest is field path
                        node_id = str(value[0])
                        field_path = [str(f) for f in value[1:]]
                        raw = ".".join([node_id] + field_path)
                        references.append(VariableReference(
                            raw=raw,
                            node_id=node_id,
                            field_path=field_path,
                        ))
                else:
                    references.extend(self._extract_references(value))
        elif isinstance(data, list):
            for item in data:
                references.extend(self._extract_references(item))

        return references

    def extract_all_node_ids(self, dsl_data: dict[str, Any]) -> list[str]:
        """Extract all node IDs from DSL data.

        Args:
            dsl_data: Parsed YAML data as a dictionary.

        Returns:
            List of all node IDs.
        """
        graph_data = dsl_data.get("workflow", dsl_data).get("graph", {})
        nodes_data = graph_data.get("nodes", [])
        return [node.get("id", "") for node in nodes_data if node.get("id")]

    def get_dependency_order(self, graph: WorkflowGraph) -> list[str]:
        """Get nodes in dependency order (topological sort).

        Args:
            graph: The parsed workflow graph.

        Returns:
            List of node IDs in execution order.
        """
        # Build adjacency list from edges
        adjacency: dict[str, list[str]] = {node_id: [] for node_id in graph.nodes}
        in_degree: dict[str, int] = {node_id: 0 for node_id in graph.nodes}

        for edge in graph.edges:
            if edge.source_node_id in adjacency:
                adjacency[edge.source_node_id].append(edge.target_node_id)
            if edge.target_node_id in in_degree:
                in_degree[edge.target_node_id] += 1

        # Kahn's algorithm for topological sort
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            node_id = queue.pop(0)
            result.append(node_id)

            for neighbor in adjacency.get(node_id, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return result


def replace_variable_references(text: str) -> str:
    """Replace Dify variable references with Python state access.

    Args:
        text: Text containing {{#node_id.field#}} references.

    Returns:
        Text with references replaced by state["node_id"]["field"].

    Examples:
        >>> replace_variable_references("Hello {{#user.name#}}!")
        'Hello {state["user"]["name"]}!'
    """

    def replacer(match: re.Match) -> str:
        ref = VariableReference.parse(match.group(1))
        return "{" + ref.to_state_access() + "}"

    return VARIABLE_REFERENCE_PATTERN.sub(replacer, text)
