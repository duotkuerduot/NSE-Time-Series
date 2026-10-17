"""Maintainer tools: the web build hash (§15.4) and the README results block (§18)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from nsefc.devtools import committed_web_hash, results_block, update_readme, web_source_hash


def test_the_committed_web_build_matches_its_sources(repo_root: Path) -> None:
    """Fails when web/ changed without `pnpm -C web build`: rebuild and commit web_dist."""
    assert committed_web_hash(repo_root) == web_source_hash(repo_root)
    assert (repo_root / "src" / "nsefc" / "web_dist" / "index.html").is_file()


def test_web_hash_ignores_line_endings_and_sees_edits(tmp_path: Path, repo_root: Path) -> None:
    for name in ("index.html", "package.json", "vite.config.ts"):
        (tmp_path / "web").mkdir(exist_ok=True)
        shutil.copy(repo_root / "web" / name, tmp_path / "web" / name)
    shutil.copytree(repo_root / "web" / "src" / "lib", tmp_path / "web" / "src" / "lib")
    before = web_source_hash(tmp_path)
    target = tmp_path / "web" / "src" / "lib" / "format.ts"
    target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
    assert web_source_hash(tmp_path) == before
    target.write_text(target.read_text(encoding="utf-8") + "// edit\n", encoding="utf-8")
    assert web_source_hash(tmp_path) != before


EVALUATION = {
    "periods": {"selection": ["2018-01-01", "2022-12-31"], "holdout": ["2023-01-01", "2025-10-30"]},
    "champion": {
        "model_id": "B0",
        "label": "No-change guess",
        "reason": "No model beat the no-change guess",
    },
    "models": [
        {
            "model_id": "B0",
            "label": "No-change guess",
            "gates": [],
            "selection": {"skill": 0.0, "dm_p": 1.0, "coverage": 0.8},
            "holdout": {"skill": 0.0},
        },
        {
            "model_id": "lightgbm",
            "label": "LightGBM",
            "gates": [{"id": "G-SKILL", "passed": False}, {"id": "G-INT", "passed": True}],
            "selection": {"skill": 0.0014, "dm_p": 0.069, "coverage": 0.8},
            "holdout": {"skill": 0.0046},
        },
    ],
}
INGEST = {
    "first_session": "2007-01-02",
    "last_session": "2025-10-31",
    "dataset": {"title": "NSE prices"},
}


def test_results_block_never_says_accuracy_of_price() -> None:
    block = results_block(EVALUATION, INGEST)
    assert "**Champion: the no-change guess.**" in block
    assert "The strongest machine-learning model, LightGBM" in block
    assert "| LightGBM | +0.14% | 0.069 | +0.46% | 80.0% | failed G-SKILL |" in block
    assert 'never an "accuracy" percentage' in block


def test_update_readme_between_markers(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# T\n<!-- results:start -->\nold\n<!-- results:end -->\nafter\n", encoding="utf-8"
    )
    assert update_readme(readme, "new")
    assert (
        readme.read_text(encoding="utf-8")
        == "# T\n<!-- results:start -->\nnew\n<!-- results:end -->\nafter\n"
    )
    assert not update_readme(readme, "new")
    readme.write_text("no markers", encoding="utf-8")
    with pytest.raises(ValueError, match="markers"):
        update_readme(readme, "x")
