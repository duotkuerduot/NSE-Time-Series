"""Model artifacts (§10.3): joblib files with a JSON sidecar holding their SHA-256.

Pickle-based files are acceptable here because the tool only ever loads artifacts it produced
on the same machine, and refuses any whose hash does not match its sidecar (D-9). It never
downloads or accepts model files from anywhere else.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import joblib

from nsefc.models.estimators import Forecaster


class ArtifactError(RuntimeError):
    """An artifact is missing, or its bytes do not match the recorded SHA-256."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def save_artifact(model: Forecaster, path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Write ``path`` (.joblib) and ``path.with_suffix('.json')``; returns the sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".tmp-{path.name}")
    joblib.dump(model, tmp, compress=3)
    tmp.replace(path)
    sidecar = {
        "model_id": model.name,
        "algorithm": type(model).__name__,
        "label": model.label,
        "hyperparameters": model.params,
        "features": model.features,
        "fit_info": model.fit_info,
        **metadata,
        "sha256": _sha256(path),
    }
    path.with_suffix(".json").write_text(
        json.dumps(sidecar, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return sidecar


def load_artifact(path: Path) -> Forecaster:
    """Load an artifact, refusing it unless its SHA-256 matches the sidecar."""
    sidecar_path = path.with_suffix(".json")
    if not path.is_file() or not sidecar_path.is_file():
        raise ArtifactError(f"missing artifact or sidecar: {path}")
    expected = json.loads(sidecar_path.read_text(encoding="utf-8")).get("sha256")
    actual = _sha256(path)
    if actual != expected:
        raise ArtifactError(f"{path.name}: SHA-256 {actual[:12]} does not match its sidecar")
    model = joblib.load(path)
    if not isinstance(model, Forecaster):
        raise ArtifactError(f"{path.name} is not an nsefc model")
    return model
