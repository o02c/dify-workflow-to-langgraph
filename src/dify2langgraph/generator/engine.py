"""Code generation engine using LLM providers.

This module generates node implementations from Dify DSL configurations.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from dify2langgraph.llm import LLMConfig, LLMProvider, create_provider
from dify2langgraph.logging_config import get_logger

logger = get_logger(__name__)

# Default model (cheap and capable)
DEFAULT_PROVIDER = "openai"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass
class NodeImplementation:
    """Generated node implementation."""

    node_id: str
    code: str
    imports: list[str]


@dataclass
class NodeName:
    """Generated node name."""

    node_id: str
    title: str
    snake_case: str
    camel_case: str


NODE_NAMING_PROMPT = """Generate Python-friendly names for the following workflow nodes.

## Nodes
{nodes_json}

## Requirements
1. Convert each node title to a descriptive English name
2. Generate both snake_case (for function names) and CamelCase (for class names)
3. Names should be concise but descriptive
4. For Japanese/non-English titles, translate to English first
5. Avoid generic names like "node1", "process" - be specific

## Output Format
Return a JSON array with objects containing:
- "node_id": original node ID
- "snake_case": function name (e.g., "fetch_knowledge", "classify_question")
- "camel_case": class name (e.g., "FetchKnowledge", "ClassifyQuestion")

Return ONLY valid JSON, no markdown or explanations.
"""


SYSTEM_PROMPT = """You are an expert Python developer specializing in LangGraph workflows.
Your task is to implement node functions based on Dify DSL configurations.

Guidelines:
1. Generate clean, type-safe Python code
2. Use the provided NODE_CONFIG for configuration details
3. Access input variables using state["node_id"]["field"]
4. Return a Command with the update dictionary
5. Handle errors gracefully
6. Follow the expected output structure from the TypedDict
7. Keep imports at the top of the file, after sys.path.insert if needed
8. Use modern Python SDK APIs (OpenAI v1.0+, Anthropic, etc.)
"""

NODE_IMPLEMENTATION_PROMPT = """Implement the following LangGraph node function.

## Node Configuration
```json
{node_config}
```

## Current Code Template
```python
{template}
```

## Requirements
1. Replace the TODO placeholder with actual implementation
2. Access input variables using state_access from variable_references (already uses correct state keys)
3. Return Command(update={{state_key: output}}) - use "state_key" from config, NOT "id"
4. For start nodes: read input from state[state_key] (initial state passed to workflow)
5. Keep sys.path.insert BEFORE local imports (state, etc.)

## Node Type Specific Guidelines

### LLM nodes (type: llm)
Import LLM from a shared module and use LangChain's chat model interface:
```python
from llm import get_chat_model  # Shared LLM configuration
from langchain_core.messages import HumanMessage, SystemMessage

llm = get_chat_model()  # Returns ChatOpenAI, ChatAnthropic, etc.
messages = [
    SystemMessage(content="You are a helpful assistant."),
    HumanMessage(content=query),
]
response = llm.invoke(messages)
text = response.content
usage = response.usage_metadata or {{}}
```

### knowledge-retrieval nodes
Import retriever from a shared module:
```python
from retriever import get_retriever
retriever = get_retriever()
docs = retriever.invoke(query)
result = [{{"content": doc.page_content, "metadata": doc.metadata}} for doc in docs]
```

### code nodes
Execute the embedded code safely using exec() with limited globals.

### tool nodes
Import and call the tool from a shared module.

## Output Format
Return ONLY the complete Python code for the node file.
Do not include markdown code blocks or explanations.
"""


class CodeGenerationEngine:
    """Engine for generating node implementations using LLM."""

    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        """Initialize the code generation engine.

        Args:
            provider: LLM provider to use for generation.
        """
        self.provider = provider

    @classmethod
    def create_default(cls) -> "CodeGenerationEngine":
        """Create engine with default configuration (gpt-4o-mini).

        Returns:
            CodeGenerationEngine with default settings.
        """
        return cls.from_config(DEFAULT_PROVIDER, DEFAULT_MODEL)

    @classmethod
    def from_config(
        cls,
        provider_name: str | None = None,
        model: str | None = None,
        **kwargs,
    ) -> "CodeGenerationEngine":
        """Create engine from configuration.

        Args:
            provider_name: Name of the LLM provider (default: openai).
            model: Model identifier (default: gpt-4o-mini).
            **kwargs: Additional provider-specific arguments.

        Returns:
            Configured CodeGenerationEngine instance.
        """
        provider_name = provider_name or DEFAULT_PROVIDER
        model = model or DEFAULT_MODEL
        config = LLMConfig(model=model, temperature=0.0)
        provider = create_provider(provider_name, config, **kwargs)
        return cls(provider)

    def generate_node_names(
        self,
        nodes: list[dict],
    ) -> list[NodeName]:
        """Generate Python-friendly names for nodes using LLM.

        Args:
            nodes: List of node info dicts with 'id', 'title', 'type'.

        Returns:
            List of NodeName with snake_case and camel_case names.
        """
        # Prepare node info for LLM
        nodes_for_llm = [
            {"node_id": n["id"], "title": n["title"], "type": n["type"]}
            for n in nodes
        ]

        prompt = NODE_NAMING_PROMPT.format(
            nodes_json=json.dumps(nodes_for_llm, indent=2, ensure_ascii=False)
        )

        response = self.provider.generate_text(
            prompt=prompt,
            system="You are a helpful assistant that generates Python-friendly names.",
        )

        # Parse JSON response
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
        if response.endswith("```"):
            response = response.rsplit("```", 1)[0]

        try:
            names_data = json.loads(response)
        except json.JSONDecodeError:
            # Fallback: return empty list
            return []

        # Build NodeName objects
        result = []
        title_map = {n["id"]: n["title"] for n in nodes}
        for item in names_data:
            node_id = item.get("node_id", "")
            result.append(NodeName(
                node_id=node_id,
                title=title_map.get(node_id, ""),
                snake_case=item.get("snake_case", ""),
                camel_case=item.get("camel_case", ""),
            ))

        return result

    def generate_node_implementation(
        self,
        node_config: dict,
        template: str,
    ) -> str:
        """Generate implementation for a single node.

        Args:
            node_config: Node configuration from NODE_CONFIG.
            template: Current code template for the node.

        Returns:
            Generated Python code for the node.
        """
        prompt = NODE_IMPLEMENTATION_PROMPT.format(
            node_config=json.dumps(node_config, indent=2, ensure_ascii=False),
            template=template,
        )

        response = self.provider.generate_text(
            prompt=prompt,
            system=SYSTEM_PROMPT,
        )

        # Clean up response (remove markdown if present)
        code = response.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]

        return code.strip()

    def generate_all_nodes(
        self,
        nodes_dir: Path,
        dry_run: bool = False,
    ) -> list[NodeImplementation]:
        """Generate implementations for all nodes in a directory.

        Args:
            nodes_dir: Directory containing node files.
            dry_run: If True, don't write files, just return implementations.

        Returns:
            List of generated implementations.
        """
        implementations = []

        for node_file in nodes_dir.glob("*.py"):
            if node_file.name == "__init__.py":
                continue

            content = node_file.read_text(encoding="utf-8")

            # Extract NODE_CONFIG from file
            node_config = self._extract_node_config(content)
            if not node_config:
                continue

            # Skip if already implemented (no TODO marker)
            if "# TODO: Implement" not in content:
                continue

            # Generate implementation
            new_code = self.generate_node_implementation(node_config, content)

            impl = NodeImplementation(
                node_id=node_config.get("id", node_file.stem),
                code=new_code,
                imports=[],
            )
            implementations.append(impl)

            if not dry_run:
                node_file.write_text(new_code, encoding="utf-8")
                logger.info("Generated: %s", node_file)

        return implementations

    def _extract_node_config(self, content: str) -> dict | None:
        """Extract NODE_CONFIG from file content.

        Args:
            content: Python file content.

        Returns:
            Parsed NODE_CONFIG dict or None.
        """
        # Find NODE_CONFIG_JSON
        start_marker = "NODE_CONFIG_JSON = '''"
        end_marker = "'''"

        start = content.find(start_marker)
        if start == -1:
            return None

        start += len(start_marker)
        end = content.find(end_marker, start)
        if end == -1:
            return None

        json_str = content[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
