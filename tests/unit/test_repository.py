"""Repository rules that CI enforces (ENGINEERING.md 26, 28.2)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def workflows(repo_root: Path) -> list[Path]:
    return sorted((repo_root / ".github" / "workflows").glob("*.y*ml"))


def uses(node: Any) -> Iterator[str]:
    """Every `uses:` value, whatever the YAML style (block or flow)."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses" and isinstance(value, str):
                yield value
            else:
                yield from uses(value)
    elif isinstance(node, list):
        for item in node:
            yield from uses(item)


def triggers(document: dict[Any, Any]) -> dict[str, Any]:
    on = document.get("on", document.get(True))  # YAML 1.1 reads a bare `on` key as True
    return on if isinstance(on, dict) else {}


def test_there_are_workflows(repo_root: Path) -> None:
    assert {p.name for p in workflows(repo_root)} >= {"ci.yml", "source-spike.yml"}


def test_actions_are_pinned_to_commit_shas(repo_root: Path) -> None:
    unpinned = [
        f"{path.name}: {ref}"
        for path in workflows(repo_root)
        for ref in uses(yaml.safe_load(path.read_text(encoding="utf-8")))
        if not ref.startswith("./") and not PINNED.match(ref)
    ]
    assert unpinned == []


def test_the_pin_check_sees_flow_style(tmp_path: Path) -> None:
    flow = yaml.safe_load("steps: [{uses: actions/checkout@v4}, {run: echo}]")
    assert list(uses(flow)) == ["actions/checkout@v4"]


@pytest.mark.parametrize("name", ["ci.yml", "source-spike.yml"])
def test_workflows_grant_read_only_contents(repo_root: Path, name: str) -> None:
    document = yaml.safe_load((repo_root / ".github" / "workflows" / name).read_text())
    assert document["permissions"] == {"contents": "read"}


def test_schedules_run_in_nairobi_time(repo_root: Path) -> None:
    for path in workflows(repo_root):
        for entry in triggers(yaml.safe_load(path.read_text(encoding="utf-8"))).get("schedule", []):
            assert entry.get("timezone") == "Africa/Nairobi", path.name
