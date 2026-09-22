#!/usr/bin/env python3
"""Stable digest of a generated package, for comparing runs across platforms.

The converter is deterministic (ADR-0001): the same Workflow DSL must produce the
same bytes whether it ran natively on macOS, natively on Windows, or inside the
container. Comparing directory trees by hand across machines is awkward, so this
reduces a generated package to a single hex digest that is trivial to compare.

The digest covers every file's relative path *and* contents, so a renamed file, a
reordered directory, or a one-byte change all move it. Paths are normalised to
POSIX separators so Windows and macOS agree.

Two modes:

    # generate a reference package from a DSL, then digest it
    python scripts/output_digest.py tests/fixtures/guardduty_handler.yml

    # digest a package that already exists (stdlib only -- no install needed)
    python scripts/output_digest.py --dir path/to/generated/package

``scripts/verify-windows.ps1`` calls the second form, so both platforms share this
one implementation and the algorithms cannot drift apart.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path


def digest_dir(root: Path) -> str:
    """Return a hex digest covering every file under ``root``.

    Args:
        root: Directory to digest.

    Returns:
        Hex-encoded SHA-256 over each file's POSIX-relative path and bytes,
        visited in sorted path order.

    Raises:
        SystemExit: If ``root`` is not a directory or holds no files.
    """
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    # Skip bytecode: importing or py_compile-ing a generated package drops
    # __pycache__ into it, which would otherwise change the digest depending on
    # whether the package had been run yet.
    files = sorted(
        (
            p
            for p in root.rglob("*")
            if p.is_file()
            and p.suffix != ".pyc"
            and "__pycache__" not in p.relative_to(root).parts
        ),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    if not files:
        raise SystemExit(f"no files under: {root}")

    h = hashlib.sha256()
    for path in files:
        h.update(path.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def generate_and_digest(dsl: Path) -> str:
    """Convert ``dsl`` into a temporary directory and digest the result.

    Uses the deterministic path only (no LLM post-processing), so the digest is
    reproducible and the call needs no credentials or network access.

    Args:
        dsl: Path to a Dify Workflow DSL file.

    Returns:
        Hex digest of the generated package.
    """
    # Quieten the converter's progress logging so stdout is just the digest and
    # the value can be piped or eyeballed. configure_logging() reads LOG_LEVEL at
    # import time, so this has to be set before the import below.
    os.environ.setdefault("LOG_LEVEL", "ERROR")

    from dify2langgraph.cli import translate

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / dsl.stem
        translate(dsl, out)
        return digest_dir(out)


def main() -> int:
    """Entry point.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("dsl", nargs="?", type=Path, help="Workflow DSL to convert and digest")
    group.add_argument("--dir", type=Path, help="Digest an already-generated package")
    args = parser.parse_args()

    print(digest_dir(args.dir) if args.dir else generate_and_digest(args.dsl))
    return 0


if __name__ == "__main__":
    sys.exit(main())
