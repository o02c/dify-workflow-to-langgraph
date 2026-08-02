# dify-workflow-to-langgraph

Converts a Dify Workflow DSL into runnable, type-safe LangGraph Python code. The conversion is deterministic at its core; LLM assistance is opt-in post-processing (see docs/adr/0001).

## Language

**Workflow DSL**:
The exported Dify workflow file (YAML) that is the tool's input. Contains `nodes`, `edges`, and variable references.
_Avoid_: config, spec, yaml (when referring to the whole input)

**Node**:
A single step in a Workflow DSL (e.g. `start`, `llm`, `end`, `question-classifier`). Each Dify Node maps to one LangGraph node.
_Avoid_: step, stage

**Edge**:
A connection between two Nodes in the Workflow DSL. May be a plain successor or, for branching Nodes, a conditional branch.

**Variable Reference**:
An expression that reads another Node's output, in either syntax — a value_selector array `['<id>','field']` in structured config, or a `{{#<id>.field#}}` template string in prompt text. Both normalize to `state["node_<id>"]["field"]` (see docs/adr/0004). The source of the inter-Node dependency graph.
_Avoid_: placeholder, template var

**System Inputs (`sys`)**:
Workflow-level runtime inputs (`sys.query`, `sys.files`, `sys.user_id`), held under the reserved `sys` key of GraphState. Distinct from `env` (DSL constants, generated as module constants) and from Node outputs.

**Structure**:
The graph-shape layer of the generated output: state keys, node registration, and edge wiring (including conditional branches). Produced deterministically for every Node type.
_Avoid_: skeleton, scaffold (when precise; those are fine informally)

**Node Body**:
The implementation inside a generated node function — what the Node actually computes (LLM call, RAG lookup, code logic). Handled per Node type; unsupported types are emitted as a Stub.
_Avoid_: node logic, handler

**Stub**:
A generated Node Body left as a typed `# TODO` placeholder so the output still compiles and its Structure is correct, to be filled later (by hand or opt-in LLM).
_Avoid_: mock, dummy

**GraphState**:
The generated `TypedDict(total=False)` holding every Node's output, one key per Node. The canonical key is `node_<dify_node_id>` (see docs/adr/0002); a Node reads another's output via `state["node_<id>"]["field"]`.
_Avoid_: context, blackboard, variable pool

**Node Output**:
The typed dict a Node writes into its own GraphState slot; its fields are inferred deterministically from the Node type (and, for `start`/`end`, from declared variables).

**Branching Node**:
A Node with more than one outgoing branch selected at runtime (`question-classifier`, `if-else`). Its Edges carry a non-`source` `sourceHandle` identifying the branch. Compiles to `add_conditional_edges` + a Router (see docs/adr/0003).
_Avoid_: decision node, switch

**Router**:
A generated `route_<node>(state)` function that reads a Branching Node's output and returns the branch key mapped (deterministically, from `sourceHandle`) to the next Node.

**Node Handler**:
The unit of Node-type support. One handler per Dify Node type, exposing `output_fields()`, `generate_body()`, and `routing()`; unknown types use a fallback handler that emits a Stub. Adding Node-type coverage means adding a handler (see docs/adr/0005).
_Avoid_: plugin, adapter, converter (reserve "adapter" for Retriever backends)

**Retriever**:
The port (protocol) in generated `retriever.py` that a knowledge-retrieval Node calls for RAG. The default adapter is `DifyApiRetriever` (Dify's public Retrieval API); the backend is swappable (see docs/adr/0006).
_Avoid_: db_retriever, vector store (those are specific backends)
