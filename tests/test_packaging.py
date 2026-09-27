"""Tests for packaging metadata that only bites outside the locked environment.

`uv sync` installs exactly what `uv.lock` pins, so a wrong floor in
pyproject.toml is invisible during development. USAGE.md section 2 documents
`pip install .` as the primary install route, and that ignores the lock entirely
-- a floor below what the code actually needs lets a customer resolve a version
nobody has ever run.
"""

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ">=" floors are the ones that make a promise about what the code tolerates.
_FLOOR = re.compile(r"^([A-Za-z0-9_.\-]+)\s*>=\s*([0-9][0-9.]*)$")


def _version_tuple(text: str) -> tuple[int, ...]:
    """Parse a dotted version into a comparable tuple.

    Args:
        text: A version such as "1.6.3".

    Returns:
        Its numeric components.
    """
    return tuple(int(part) for part in text.split("."))


def _locked_versions() -> dict[str, str]:
    """Package name -> version, as pinned by uv.lock.

    Returns:
        Lowercased, hyphenated names mapped to their locked versions.
    """
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    pairs = re.findall(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', lock)
    return {name.lower().replace("_", "-"): version for name, version in pairs}


def _declared_floors() -> dict[str, str]:
    """Package name -> declared ">=" floor, across dependencies and groups.

    Returns:
        Lowercased, hyphenated names mapped to their declared floors.
    """
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = list(project["project"]["dependencies"])
    for group in project.get("dependency-groups", {}).values():
        requirements += [item for item in group if isinstance(item, str)]

    floors = {}
    for requirement in requirements:
        match = _FLOOR.match(requirement.strip())
        if match:
            floors[match.group(1).lower().replace("_", "-")] = match.group(2)
    return floors


class TestDependencyFloors:
    """A declared floor is a claim that the code works on that version."""

    def test_no_floor_is_below_the_locked_version(self):
        """Nothing older than the lock has ever been exercised.

        Floors used to sit a whole major release low -- `langchain-core>=0.3.0`
        against a locked 1.6.3 -- so `pip install .` could resolve an API the code
        was never written against.
        """
        locked = _locked_versions()
        stale = []
        for name, floor in _declared_floors().items():
            if name not in locked:
                continue
            if _version_tuple(floor) < _version_tuple(locked[name]):
                stale.append(f"{name}>={floor} but uv.lock pins {locked[name]}")

        assert not stale, "floors below the lock: " + "; ".join(stale)

    def test_every_dependency_declares_a_floor(self):
        """An unpinned dependency resolves to anything at all."""
        project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        unbounded = [
            requirement
            for requirement in project["project"]["dependencies"]
            if not any(op in requirement for op in (">=", "==", "~="))
        ]

        assert unbounded == []
