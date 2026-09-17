#!/usr/bin/env python3
"""Move `[tool.uv] exclude-newer` in pyproject.toml to three days ago.

The converter is shipped to customer sites, so dependency versions are only
adopted once they have been public long enough for a yank or a compromised
release to be noticed. uv's `exclude-newer` takes a fixed timestamp rather than a
rolling window, so this script rewrites it; `make lock` runs it before `uv lock`.

Keeping the value in pyproject.toml rather than passing `--exclude-newer` on the
command line means *every* uv resolution obeys it -- `uv lock`, `uv add`, a plain
`uv sync` -- not just the one Makefile target.
"""

import datetime
import pathlib
import re
import sys

QUARANTINE_DAYS = 3
PATTERN = re.compile(r'^exclude-newer = ".*"$', re.MULTILINE)


def main() -> int:
    """Rewrite the exclude-newer timestamp in place."""
    path = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    content = path.read_text(encoding="utf-8")

    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=QUARANTINE_DAYS)
    replacement = f'exclude-newer = "{cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")}"'

    updated, count = PATTERN.subn(replacement, content, count=1)
    if count != 1:
        print(
            "error: no `exclude-newer = \"...\"` line found in pyproject.toml; "
            "the dependency quarantine is not configured",
            file=sys.stderr,
        )
        return 1

    path.write_text(updated, encoding="utf-8")
    print(replacement)
    return 0


if __name__ == "__main__":
    sys.exit(main())
