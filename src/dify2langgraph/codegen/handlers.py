"""Node Handler registry.

Each Dify Node type maps to one :class:`NodeHandler` that owns the type-specific
knowledge the generators need:

- ``output_fields(node)`` -- the Node Output ``TypedDict`` fields
- ``stub_output(node, graph)`` -- the placeholder Node Body values (the Stub)
- ``is_branching`` / ``decision_field`` -- routing shape for a Branching Node

The state / node / graph generators are thin orchestrators that look a handler up
by type via :func:`get_handler`; an unknown type falls back to the base
:class:`NodeHandler`, which emits a generic typed Stub so the generated code still
compiles. Adding support for a Node type is adding one handler here.

Structural (type-agnostic) routing helpers -- deriving the branch map from the
DSL ``sourceHandle`` -- live in :mod:`dify2langgraph.codegen.routing`.
"""

import json
from typing import Any

from dify2langgraph.codegen.env_vars import declared_names
from dify2langgraph.codegen.naming import get_node_names
from dify2langgraph.codegen.routing import default_branch_key
from dify2langgraph.logging_config import get_logger
from dify2langgraph.parser.dsl_parser import NodeInfo, WorkflowGraph

logger = get_logger(__name__)


def placeholder_literal(field_type: str) -> str:
    """Python literal used as a Stub's placeholder for a given type annotation."""
    if field_type == "str":
        return '"placeholder"'
    if field_type == "float":
        return "0.0"
    if field_type == "int":
        return "0"
    if field_type == "bool":
        return "False"
    if field_type.startswith("list"):
        return "[]"
    if field_type.startswith("dict"):
        return "{}"
    # "Any" and anything unknown
    return "None"


class NodeHandler:
    """Fallback handler: a generic typed Stub wired as a single successor.

    Subclasses override :meth:`output_fields` (and, for Branching Nodes, set
    ``is_branching`` / ``decision_field``). The base implementation is what an
    unknown Node type gets.
    """

    node_type: str = "*"
    is_branching: bool = False
    decision_field: str | None = None
    # False when the handler emits a real deterministic body (not a TODO Stub).
    emits_stub_body: bool = True

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        """Field name -> type annotation for this node's Node Output."""
        return {"output": "Any"}

    def body_imports(self, node: NodeInfo) -> list[str]:
        """Extra import lines the generated node body needs (e.g. the Retriever)."""
        return []

    def body_prelude(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> list[str]:
        """Lines emitted inside the node body before the output dict.

        Most node types need nothing here. The Start node uses it to pull the
        caller's workflow inputs out of state and reject missing required ones.

        Args:
            node: The Node being generated.
            graph: The parsed workflow, for resolving references.
            node_name_map: Optional node_id -> (snake_case, CamelCase) mapping.

        Returns:
            Source lines, already indented to the function body.
        """
        return []

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        """Field name -> Python expression for the node body's output dict.

        The base implementation emits placeholder literals (a Stub). Handlers may
        override to emit real expressions (e.g. the End node forwards upstream
        values via normalized state accesses).
        """
        return {
            name: placeholder_literal(ftype)
            for name, ftype in self.output_fields(node).items()
        }


# ADR-0004 reserves a `sys` key in GraphState for Dify's workflow-level runtime
# inputs. *Which* ones exist is mode-dependent -- `sys.query` is chatflow-only,
# while `sys.app_id` / `sys.user_id` appear in workflow mode -- so the generator
# declares exactly the fields the DSL references rather than a fixed set. Both
# reference syntaxes arrive here already normalised by the parser into
# VariableReference(node_id="sys", ...).
SYS_NAMESPACE = "sys"
# ADR-0004 puts env *outside* state: the DSL's environment_variables are
# constants, emitted into a generated env.py module (see env_generator).
ENV_NAMESPACE = "env"

# Each field's *type*, by contrast, is fixed by Dify and not carried in the DSL
# (a chatflow Start declares `variables: []`), so a name table is the only
# source for it. Dify's own system-variable set (SystemVariableKey), not just
# the fields our fixtures happen to use: `dialogue_count` and `timestamp` are
# numbers, and defaulting them to `str` put `"dialogue_count": "example"` in
# the generated entry point. RAG-pipeline-only keys are left out; they reach
# `Any`, which is honest about not knowing rather than wrong.
_SYS_FIELD_TYPES = {
    "app_id": "str",
    "conversation_id": "str",
    "dialogue_count": "int",
    "files": "list[Any]",
    "query": "str",
    "timestamp": "int",
    "user_id": "str",
    "workflow_id": "str",
    "workflow_run_id": "str",
}

# Example values for `python -m <package>`, keyed by the annotation above.
_SYS_EXAMPLE_BY_TYPE = {"int": "0", "list[Any]": "[]", "str": '"example"'}


def sys_field_type(field: str) -> str:
    """Type annotation for a `sys` field.

    Args:
        field: The field name, e.g. "query" or "files".

    Returns:
        A Python type annotation. `Any` for a field outside Dify's known set --
        guessing `str` would annotate it wrongly and, worse, put a string in the
        generated example for something that is not one.
    """
    return _SYS_FIELD_TYPES.get(field, "Any")


def sys_field_example(field: str) -> str:
    """A placeholder literal for a `sys` field, for the generated entry point.

    Args:
        field: The field name.

    Returns:
        A Python literal matching the field's type.
    """
    return _SYS_EXAMPLE_BY_TYPE.get(sys_field_type(field), "None")


def referenced_sys_fields(graph: WorkflowGraph) -> dict[str, str]:
    """`sys` fields the workflow actually references, with their types.

    Args:
        graph: The parsed workflow.

    Returns:
        Field name -> type annotation, in first-seen order. Empty when the
        workflow never reads `sys`, in which case nothing is emitted for it.
    """
    fields: dict[str, str] = {}
    for node in graph.nodes.values():
        for ref in node.references:
            if ref.node_id == SYS_NAMESPACE and ref.field_path:
                name = ref.field_path[0]
                fields.setdefault(name, sys_field_type(name))
    return fields


def sys_prelude(fields: list[str]) -> list[str]:
    """Lines that reject a missing `sys` input by name.

    The caller supplies `sys.*` at invoke time, the same as the workflow inputs a
    Start Node validates -- but without this the omission surfaced as a bare
    `KeyError: 'sys'` from inside whichever body happened to read it first, which
    names neither the field nor who was supposed to provide it.

    Args:
        fields: The `sys` field names this node's body reads.

    Returns:
        Prelude lines, or empty when the body reads none.
    """
    if not fields:
        return []
    names = ", ".join(json.dumps(name) for name in sorted(fields))
    return [
        "    # Dify's sys.* values are supplied by the caller at invoke time,",
        "    # alongside the workflow inputs:",
        '    #     build_graph().invoke({..., "sys": {...}})',
        '    supplied_sys = state.get("sys", {})',
        f"    missing_sys = [name for name in ({names},) if name not in supplied_sys]",
        "    if missing_sys:",
        "        raise ValueError(",
        '            "missing required sys input(s): " + ", ".join(missing_sys)',
        "        )",
    ]


def referenced_sys_fields_for(node: NodeInfo) -> list[str]:
    """The `sys` field names one node reads, in first-seen order.

    Args:
        node: The Node being generated.

    Returns:
        The field names, without duplicates.
    """
    seen: dict[str, None] = {}
    for ref in node.references:
        if ref.node_id == SYS_NAMESPACE and ref.field_path:
            seen.setdefault(ref.field_path[0], None)
    return list(seen)


def resolve_selector(
    selector: list[Any],
    graph: WorkflowGraph,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> str | None:
    """A Dify value_selector as a canonical state access, or None.

    Args:
        selector: A `[<source>, <field>, ...]` selector from the DSL.
        graph: The parsed workflow, for recognising Node ids.
        node_name_map: Optional node_id -> (snake_case, CamelCase) mapping.

    Returns:
        An expression such as ``state["llm_node"]["text"]``, or None when the
        selector names an unknown node, or an `env` variable the DSL does not
        declare (there is no constant for the generated code to reach).
    """
    if len(selector) < 2:
        return None

    source = selector[0]
    if source in graph.nodes:
        key, _ = get_node_names(str(source), node_name_map)
    elif source == SYS_NAMESPACE:
        # ADR-0004: sys lives in state under its own reserved key.
        key = SYS_NAMESPACE
    elif source == ENV_NAMESPACE:
        # Constants live in the generated env.py, reached as `env.NAME` after
        # `from .. import env` -- not through state (ADR-0004). The module form is
        # used rather than `from ..env import NAME` so a DSL variable named e.g.
        # `state` or `output` cannot shadow a local.
        #
        # Only for a name env.py will actually define. Dify does not scrub stale
        # selectors, so an export can reference a variable the author deleted;
        # emitting `env.GONE` as executable code turns that into an AttributeError
        # at run time, where the placeholder fallback is merely a placeholder.
        if str(selector[1]) not in declared_names(graph.environment_variables):
            return None
        return ".".join([ENV_NAMESPACE, *(str(part) for part in selector[1:])])
    else:
        return None

    access = f"state[{json.dumps(key)}]"
    for part in selector[1:]:
        access += f"[{json.dumps(str(part))}]"
    return access


def reference_access(
    ref: Any,
    node_name_map: dict[str, tuple[str, str]] | None = None,
) -> str:
    """How a parsed VariableReference is written in generated code.

    The parser normalises every syntax into `state[...]`, which is right for Node
    outputs and for `sys`, but wrong for `env`: those are module constants, and
    `GraphState` has no `env` key. The generated comments and NODE_CONFIG block
    feed the LLM body-generation pass, so an address that cannot resolve there
    teaches the model to write code that fails.

    Args:
        ref: A :class:`~dify2langgraph.parser.dsl_parser.VariableReference`.
        node_name_map: Optional node_id -> (snake_case, CamelCase) mapping.

    Returns:
        A Python expression.
    """
    if ref.node_id == ENV_NAMESPACE:
        return ".".join([ENV_NAMESPACE, *ref.field_path])
    return ref.to_state_access(node_name_map)


def resolvable_env_references(node: NodeInfo, graph: WorkflowGraph) -> list[Any]:
    """The node's `env.*` references that the generated `env.py` can satisfy.

    A reference is only resolvable if the DSL declares the variable: `env.py` is
    generated from `environment_variables` and is not written at all when that
    list is empty, so a reference to an undeclared name has nothing to reach.
    Callers use this to decide whether `from .. import env` belongs in a node
    module -- importing on the strength of an unfiltered reference emits an
    import of a module that may not exist, which breaks the whole package
    (reported as a spurious "circular import") rather than the one reference.

    Args:
        node: The Node being generated.
        graph: Parsed workflow graph, for the DSL's declared variables.

    Returns:
        The matching references, in DSL order; empty when there are none.
    """
    declared = declared_names(graph.environment_variables)
    resolvable = []
    for ref in node.references:
        if ref.node_id != ENV_NAMESPACE:
            continue
        if ref.field_path and ref.field_path[0] in declared:
            resolvable.append(ref)
        else:
            logger.warning(
                "Node %r references %r, which the DSL does not declare in "
                "environment_variables; it will stay a comment rather than code.",
                node.id,
                ref.raw,
            )
    return resolvable


def declared_default(var: dict[str, Any]) -> str | None:
    """A Start variable's declared default as a Python literal, or None.

    Dify writes ``default: ''`` for a field where the author set no default, so an
    empty string means absence -- which is also how Dify reads it, discarding an
    empty string for an unsupplied optional variable.

    A ``number`` default arrives as a string (``'3'``). Dify converts it with
    ``int()`` when it has no decimal point and ``float()`` when it does, so ``'3'``
    is ``3`` rather than ``3.0``; coercing everything to float would put "3.0"
    into any prompt that interpolates it.

    Args:
        var: One entry of the Start Node's ``variables``.

    Returns:
        A Python literal, or None when the variable has no usable default.

    Examples:
        >>> declared_default({"type": "number", "default": "3"})
        '3'
        >>> declared_default({"type": "number", "default": "2.5"})
        '2.5'
    """
    raw = var.get("default")
    if raw is None or raw == "":
        return None
    if var.get("type") == "number":
        try:
            return repr(float(raw) if "." in str(raw) else int(raw))
        except (TypeError, ValueError):
            return None
    return repr(raw)


def start_variables(node: NodeInfo) -> list[dict[str, Any]]:
    """Declared workflow input variables of a Start Node, in DSL order.

    Args:
        node: The Start Node.

    Returns:
        The variable declarations that have a name.
    """
    return [v for v in node.data.get("variables", []) if v.get("variable")]


def start_input_example(node: NodeInfo) -> str:
    """Python literal for an example workflow input dict.

    The Start Node rejects missing required inputs, so the generated
    ``__main__.py`` has to pass something for ``python -m <package>`` to remain a
    working demonstration rather than an immediate ValueError.

    Args:
        node: The Start Node.

    Returns:
        A dict literal such as ``{"query": "example"}``.
    """
    variables = start_variables(node)
    if not variables:
        return "{}"
    pairs = []
    for var in variables:
        value = declared_default(var)
        if value is None:
            value = "0.0" if var.get("type") == "number" else '"example"'
        pairs.append(f"{json.dumps(var['variable'])}: {value}")
    return "{" + ", ".join(pairs) + "}"


class StartHandler(NodeHandler):
    node_type = "start"
    # Deterministic: surfaces the caller's workflow inputs. It used to emit a
    # Stub that returned {"query": "placeholder"}, which *overwrote* whatever the
    # caller passed -- so a generated workflow could not be given inputs at all.
    emits_stub_body = False

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for var in start_variables(node):
            fields[var["variable"]] = "float" if var.get("type") == "number" else "str"
        return fields or {"inputs": "dict[str, Any]"}

    def body_prelude(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> list[str]:
        key, _ = get_node_names(node.id, node_name_map)
        # `required` alone decides, not whether a default exists. Dify's own
        # `_validate_inputs` raises "<var> is required in input form" for an absent
        # required variable and only reads `default` on the non-required branch --
        # so accepting a required variable because it declares a default would run
        # a workflow Dify itself would have rejected.
        required = [v["variable"] for v in start_variables(node) if v.get("required")]

        lines = [
            "    # Workflow inputs are supplied by the caller in this node's own",
            "    # state slot (ADR-0009):",
            f'    #     build_graph().invoke({{{json.dumps(key)}: {{...}}}})',
            f"    supplied = state.get({json.dumps(key)}, {{}})",
        ]
        if required:
            names = ", ".join(json.dumps(name) for name in required)
            lines += [
                "",
                f"    missing = [name for name in ({names},) if name not in supplied]",
                "    if missing:",
                "        raise ValueError(",
                f'            "{key} is missing required workflow input(s): "',
                '            + ", ".join(missing)',
                "        )",
            ]
        return lines

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        variables = start_variables(node)
        if not variables:
            return {"inputs": 'supplied.get("inputs", {})'}

        result: dict[str, str] = {}
        for var in variables:
            name = var["variable"]
            literal = json.dumps(name)
            declared = declared_default(var)
            if var.get("required"):
                # Validated by the prelude above; indexed rather than defaulted
                # because Dify ignores `default` for a required variable.
                result[name] = f"supplied[{literal}]"
            elif declared is not None:
                # The workflow author set this in Dify; honouring it is what makes
                # the generated package behave like the original workflow.
                result[name] = f"supplied.get({literal}, {declared})"
            else:
                fallback = "0.0" if var.get("type") == "number" else '""'
                result[name] = f"supplied.get({literal}, {fallback})"
        return result


# JSON Schema type -> the annotation used in generated TypedDicts.
_JSON_SCHEMA_TYPES = {
    "string": "str",
    "number": "float",
    "integer": "int",
    "boolean": "bool",
    "array": "list[Any]",
    "object": "dict[str, Any]",
}


def json_schema_placeholder(schema: dict[str, Any]) -> str:
    """A placeholder literal shaped like a JSON Schema, nesting included.

    A flat pass was not enough: a selector one level deeper -- the same
    `[<node>, structured_output, person, name]` shape Dify emits for a nested
    object -- still raised `KeyError` because the outer object was emitted as a
    bare `{}`. The nested `properties` are in the DSL, so recurse into them.

    Args:
        schema: A JSON Schema fragment from the DSL.

    Returns:
        A Python literal. `None` for a fragment whose type cannot be read
        (`$ref`, `anyOf`, no `type` at all): a wrong shape would be read through
        and fail confusingly, while None is visibly a placeholder.
    """
    schema_type = schema.get("type")
    if schema_type == "object":
        properties = schema.get("properties") or {}
        pairs = ", ".join(
            f"{json.dumps(name)}: {json_schema_placeholder(spec or {})}"
            for name, spec in properties.items()
        )
        return "{" + pairs + "}"
    if schema_type == "array":
        items = schema.get("items") or {}
        # One element, so a downstream read of `[0]` resolves. An empty list
        # would raise IndexError the first time anything indexed it.
        element = json_schema_placeholder(items) if items.get("type") else None
        return f"[{element}]" if element else "[]"
    if schema_type in _JSON_SCHEMA_TYPES:
        return placeholder_literal(_JSON_SCHEMA_TYPES[schema_type])
    return "None"


class LlmHandler(NodeHandler):
    node_type = "llm"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        # Dify's LLM node outputs text, reasoning_content and usage. Declaring all
        # three costs one placeholder key each and removes the KeyError a selector
        # into reasoning_content would otherwise hit -- the same failure
        # structured_output had. usage carries floats and a currency string, not
        # only ints.
        fields = {
            "text": "str",
            "reasoning_content": "str",
            "usage": "dict[str, Any]",
        }
        # With structured output enabled, downstream nodes read through it --
        # `[<llm id>, "structured_output", "<field>"]`. Without declaring it the
        # generated End body raised KeyError: 'structured_output' at run time.
        if node.data.get("structured_output_enabled"):
            fields["structured_output"] = "dict[str, Any]"
        return fields

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        result = super().stub_output(node, graph, node_name_map)
        if "structured_output" not in result:
            return result

        # The DSL carries the schema, so the Stub can honour its shape instead of
        # emitting {} -- otherwise a downstream read of any declared field raises.
        schema = node.data.get("structured_output", {}).get("schema", {})
        literal = json_schema_placeholder(schema)
        if literal != "{}":
            result["structured_output"] = literal
        return result


class KnowledgeRetrievalHandler(NodeHandler):
    node_type = "knowledge-retrieval"
    emits_stub_body = False  # deterministic: calls the Retriever port

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"result": "list[dict[str, Any]]"}

    def body_imports(self, node: NodeInfo) -> list[str]:
        return ["from ..retriever import get_retriever"]

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        # Retrieve through the Retriever port: the query comes from the node's
        # query_variable_selector (normalized to a canonical state access) and the
        # dataset_ids from the Dify config.
        selector = node.data.get("query_variable_selector") or []
        dataset_ids = node.data.get("dataset_ids") or []
        resolved = resolve_selector(selector, graph, node_name_map)
        if resolved:
            query = resolved
        else:
            query = '""'
        call = f"get_retriever().retrieve(query={query}, dataset_ids={dataset_ids!r}"
        retrieval_model = self._retrieval_model(node)
        if retrieval_model:
            call += f", retrieval_model={retrieval_model!r}"
        call += ")"
        return {"result": call}

    @staticmethod
    def _retrieval_model(node: NodeInfo) -> dict[str, object]:
        """Project the Node's multiple_retrieval_config into a retrieval_model.

        Only the DSL-carried fields (top_k, score_threshold); search_method and the
        rest are defaulted by the Retriever adapter (a dataset/deploy concern). The
        adapter also fills the API's other required fields. Reranking passthrough is
        not handled (it needs a rerank provider/model config).
        """
        config = node.data.get("multiple_retrieval_config") or {}
        model: dict[str, object] = {}
        if config.get("top_k") is not None:
            model["top_k"] = config["top_k"]
        threshold = config.get("score_threshold")
        if threshold is not None:
            model["score_threshold_enabled"] = True
            model["score_threshold"] = threshold
        return model


class CodeHandler(NodeHandler):
    node_type = "code"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"result": "Any", "stdout": "str", "stderr": "str"}


class ToolHandler(NodeHandler):
    node_type = "tool"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "files": "list[dict[str, Any]]"}


class TemplateTransformHandler(NodeHandler):
    node_type = "template-transform"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"output": "str"}


class VariableAggregatorHandler(NodeHandler):
    node_type = "variable-aggregator"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"output": "Any"}


class EndHandler(NodeHandler):
    node_type = "end"
    emits_stub_body = False  # deterministic: forwards upstream values

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        fields: dict[str, str] = {}
        for output in node.data.get("outputs", []):
            name = output.get("variable", "")
            if name:
                fields[name] = "Any"
        return fields or {"result": "Any"}

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        # The End node is deterministic: each declared output's value_selector
        # [node_id, field...] forwards an upstream value via a normalized canonical
        # state access. `sys` resolves to its reserved state key and `env` to the
        # generated constants module; an unknown node -- or an `env` name the DSL
        # no longer declares -- falls back to a placeholder.
        result: dict[str, str] = {}
        for output in node.data.get("outputs", []):
            name = output.get("variable", "")
            if not name:
                continue
            selector = output.get("value_selector") or []
            result[name] = resolve_selector(selector, graph, node_name_map) or "None"
        return result or {"result": "None"}


class AnswerHandler(NodeHandler):
    node_type = "answer"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"answer": "str"}


class AgentHandler(NodeHandler):
    node_type = "agent"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"text": "str", "files": "list[dict[str, Any]]"}


class _BranchingHandler(NodeHandler):
    """Base for Branching Nodes: default the decision field to a valid branch key.

    So the generated Router resolves to a single successor and the graph runs
    end-to-end before the body is implemented.
    """

    is_branching = True

    def stub_output(
        self,
        node: NodeInfo,
        graph: WorkflowGraph,
        node_name_map: dict[str, tuple[str, str]] | None = None,
    ) -> dict[str, str]:
        output = super().stub_output(node, graph, node_name_map)
        key = default_branch_key(graph, node.id)
        if key is not None and self.decision_field:
            output[self.decision_field] = repr(key)
        return output


class QuestionClassifierHandler(_BranchingHandler):
    node_type = "question-classifier"
    decision_field = "class_id"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"class_name": "str", "class_id": "str"}


class IfElseHandler(_BranchingHandler):
    node_type = "if-else"
    decision_field = "selected_branch"

    def output_fields(self, node: NodeInfo) -> dict[str, str]:
        return {"selected_branch": "str"}


_HANDLERS: dict[str, NodeHandler] = {
    handler.node_type: handler
    for handler in (
        StartHandler(),
        LlmHandler(),
        KnowledgeRetrievalHandler(),
        CodeHandler(),
        ToolHandler(),
        TemplateTransformHandler(),
        VariableAggregatorHandler(),
        EndHandler(),
        AnswerHandler(),
        AgentHandler(),
        QuestionClassifierHandler(),
        IfElseHandler(),
    )
}

_FALLBACK = NodeHandler()


def get_handler(node_type: str) -> NodeHandler:
    """Return the handler for a Node type, or the generic-Stub fallback."""
    return _HANDLERS.get(node_type, _FALLBACK)


def is_branching(node: NodeInfo) -> bool:
    """Whether this node routes conditionally (needs add_conditional_edges)."""
    return get_handler(node.type).is_branching


def decision_field(node: NodeInfo) -> str | None:
    """The Node Output field whose value selects the branch (None if not branching)."""
    return get_handler(node.type).decision_field
