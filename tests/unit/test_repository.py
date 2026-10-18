"""Repository rules: one test-only CI workflow, pinned actions, and no data in git."""

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


def git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=False
    )
    if result.returncode == 128:
        pytest.skip("not a git checkout")
    return result


def tracked(repo_root: Path, *pathspec: str) -> list[str]:
    """Files git tracks, leaving out those already deleted from the working tree."""
    listed = git(repo_root, "ls-files", "-z", "--", *pathspec).stdout.split("\0")
    deleted = set(git(repo_root, "ls-files", "-z", "--deleted", "--", *pathspec).stdout.split("\0"))
    return [name for name in listed if name and name not in deleted]


def test_gitignore_keeps_data_out(repo_root: Path) -> None:
    lines = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/*" in lines and "!data/.gitkeep" in lines and "!data/README.md" in lines
    assert "data/source/*" in lines and "!data/source/README.md" in lines
    for kept in ("data/.gitkeep", "data/README.md", "data/source/README.md"):
        assert (repo_root / kept).is_file(), kept


def test_nothing_under_data_is_tracked(repo_root: Path) -> None:
    assert set(tracked(repo_root, "data")) <= {
        "data/.gitkeep",
        "data/README.md",
        "data/source/README.md",
    }


def test_dataset_files_are_ignored(repo_root: Path) -> None:
    for probe in (
        "data/source/NSE_data_all_stocks_2026_upto_jun.csv",
        "data/source/Collection 2026/NSE_data_stock_market_sectors_2026.csv",
        "data/source/hvmhnp7f9r-1.zip",
    ):
        assert git(repo_root, "check-ignore", "-q", "--no-index", probe).returncode == 0, probe


def test_no_dataset_file_is_tracked(repo_root: Path) -> None:
    """Only the small synthetic fixture: the Mendeley files are downloaded, not committed."""
    assert tracked(repo_root, "*NSE_data_*") == [
        "tests/fixtures/historical/NSE_data_all_stocks_2099_sample.csv"
    ]


def test_the_citation_is_shown_where_the_data_is_described(repo_root: Path) -> None:
    citation = "Wanjawa, Barack (2026)"
    for path in ("README.md", "reference/mendeley.yaml", "data/README.md"):
        assert citation in (repo_root / path).read_text(encoding="utf-8"), path


def test_readme_has_the_results_markers_and_a_licence(repo_root: Path) -> None:
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "<!-- results:start -->" in readme and "<!-- results:end -->" in readme
    assert "uv run nsefc run" in readme
    assert (repo_root / "LICENSE").is_file()


def test_the_package_version_matches_pyproject(repo_root: Path) -> None:
    import tomllib

    from nsefc import __version__

    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["project"]["version"] == __version__
