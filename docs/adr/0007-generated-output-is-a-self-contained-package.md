# Generated output is a self-contained package with relative imports

The generated workflow is emitted as a **Python package**: a directory with
`__init__.py` (re-exporting `build_graph`), `__main__.py` (the run entry point),
`state.py`, `graph.py`, and a `nodes/` subpackage. Modules reference each other
with **relative imports** — `graph.py` uses `from .state import ...` /
`from .nodes import ...`, and node files use `from ..state import ...`. The
previous `sys.path.insert(...)` hack in every node file is removed.

This makes the output relocatable and importable like any package (`from wf import
build_graph`) without mutating `sys.path`, and keeps its internal wiring explicit.

## Consequences

- **Run model changes**: you run the workflow with `python -m <package>` from the
  parent directory (or import it), not `python graph.py` from inside. The
  standalone-run demo moved from `graph.py` to `__main__.py`.
- **The package directory name must be a valid Python identifier** (no hyphens,
  no leading digit) to be importable. The CLI writes to `outputs/<input_stem>`;
  a stem with hyphens would need renaming before `python -m`.
- Template files copied into the package skip dunder files so they can't clobber
  the generated `__init__.py`.
- `sys`/`env` homes (ADR-0004) and `retriever.py` (ADR-0006), when implemented,
  become additional modules in this same package.
