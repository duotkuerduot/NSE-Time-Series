"""Repository rules (§4, §17, AC-04, AC-12)."""

from __future__ import annotations

import re
import shutil
import subprocess
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


def test_one_test_only_workflow(repo_root: Path) -> None:
    assert [p.name for p in workflows(repo_root)] == ["ci.yml"]
    document = yaml.safe_load(
        (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert set(document["jobs"]) == {"python", "e2e-sample", "web", "browser"}
    assert document["permissions"] == {"contents": "read"}
    assert "schedule" not in triggers(document)
    assert "secrets." not in (repo_root / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    matrix = document["jobs"]["e2e-sample"]["strategy"]["matrix"]["os"]
    assert {"ubuntu-latest", "windows-latest", "macos-latest"} <= set(matrix)


def test_actions_are_pinned_to_commit_shas(repo_root: Path) -> None:
    unpinned = [
        f"{path.name}: {ref}"
        for path in workflows(repo_root)
        for ref in uses(yaml.safe_load(path.read_text(encoding="utf-8")))
        if not ref.startswith("./") and not PINNED.match(ref)
    ]
    assert unpinned == []


def test_the_pin_check_sees_flow_style() -> None:
    flow = yaml.safe_load("steps: [{uses: actions/checkout@v4}, {run: echo}]")
    assert list(uses(flow)) == ["actions/checkout@v4"]


def test_gitignore_keeps_derived_data_out(repo_root: Path) -> None:
    lines = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/*" in lines and "!data/.gitkeep" in lines and "!data/README.md" in lines
    assert not any(line.strip().rstrip("/") == "NSE Data" for line in lines)  # D-10: committed
    assert (repo_root / "data" / ".gitkeep").is_file() and (
        repo_root / "data" / "README.md"
    ).is_file()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_nothing_under_data_is_tracked(repo_root: Path) -> None:
    result = subprocess.run(
        ["git", "ls-files", "--", "data"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = set(result.stdout.split())
    assert tracked <= {"data/.gitkeep", "data/README.md"}


def test_the_dataset_ships_with_its_citation(repo_root: Path) -> None:
    files = list((repo_root / "NSE Data").rglob("NSE_data_all_stocks_*.csv"))
    assert len(files) == 20  # 2007 to June 2026, one price file per year
    citation = "Wanjawa, Barack (2026)"
    for path in ("README.md", "reference/mendeley.yaml", "docs/data/mendeley-dataset.md"):
        assert citation in (repo_root / path).read_text(encoding="utf-8"), path


def test_draft_one_cloud_material_is_gone(repo_root: Path) -> None:
    for gone in (
        "deploy",
        "migrations",
        "research",
        ".env.example",
        "Claude outputs",
        ".github/workflows/source-spike.yml",
        "src/nsefc/storage/objectstore.py",
    ):
        assert not (repo_root / gone).exists(), gone
    assert (repo_root / "docs" / "archive" / "ENGINEERING-draft-1.0.md").is_file()
    assert (repo_root / "docs" / "adr" / "ADR-017-local-first.md").is_file()


def test_readme_has_the_results_markers_and_a_licence(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "<!-- results:start -->" in readme and "<!-- results:end -->" in readme
    assert "uv run nsefc run" in readme
    assert (repo_root / "LICENSE").is_file()
