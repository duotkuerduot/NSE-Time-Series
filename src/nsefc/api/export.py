"""JSON Schema export and release-path validation for the v1 contract."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ValidationError

from nsefc.api.v1 import (
    RESOURCES,
    MarketOverview,
    PriceHistory,
    Status,
    StockDetail,
    StockPrediction,
    StocksIndex,
)

SCHEMA_BASE_ID = "https://nsefc.local/contracts/api/v1/"

_RELEASE = r"r/(?P<release>\d{4}-\d{2}-\d{2}\.[0-9a-f]{7,64})"
_TICKER = r"(?P<ticker>[A-Z0-9&.\-]{2,12})"
_PATHS: list[tuple[re.Pattern[str], type[BaseModel]]] = [
    (re.compile(r"^status\.json$"), Status),
    (re.compile(rf"^{_RELEASE}/stocks\.json$"), StocksIndex),
    (re.compile(rf"^{_RELEASE}/stocks/{_TICKER}\.json$"), StockDetail),
    (re.compile(rf"^{_RELEASE}/stocks/{_TICKER}/history\.(1y|max)\.json$"), PriceHistory),
    (re.compile(rf"^{_RELEASE}/stocks/{_TICKER}/prediction\.json$"), StockPrediction),
    (re.compile(rf"^{_RELEASE}/market/overview\.json$"), MarketOverview),
]


def schema_documents() -> dict[str, dict[str, Any]]:
    """One JSON Schema per published resource, keyed by file stem."""
    documents: dict[str, dict[str, Any]] = {}
    for name, model in RESOURCES.items():
        schema = model.model_json_schema(mode="serialization")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"{SCHEMA_BASE_ID}{name}.schema.json"
        documents[name] = schema
    return documents


def _render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def write_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, document in schema_documents().items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(_render(document), encoding="utf-8")
        written.append(path)
    return written


def stale_schemas(out_dir: Path) -> list[str]:
    """Names of schema files that are missing or differ from the models (CI check)."""
    stale = []
    for name, document in schema_documents().items():
        path = out_dir / f"{name}.schema.json"
        if not path.exists() or path.read_text(encoding="utf-8") != _render(document):
            stale.append(path.name)
    return stale


def resource_for(relative_path: str) -> type[BaseModel] | None:
    """The contract model for a file path inside the api/v1 root, or None if unknown."""
    posix = str(PurePosixPath(relative_path))
    for pattern, model in _PATHS:
        if pattern.match(posix):
            return model
    return None


def validate_tree(root: Path) -> list[str]:
    """Validate every JSON file under an api/v1 root. Returns human-readable problems."""
    problems: list[str] = []
    files = sorted(p for p in root.rglob("*.json"))
    if not files:
        return [f"no JSON files under {root}"]
    status_release: str | None = None
    for path in files:
        relative = path.relative_to(root).as_posix()
        model = resource_for(relative)
        if model is None:
            problems.append(f"{relative}: not a known v1 resource path")
            continue
        try:
            parsed = model.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problems.append(f"{relative}: {exc.error_count()} error(s)\n{exc}")
            continue
        if isinstance(parsed, Status):
            status_release = parsed.release_id
        if isinstance(parsed, PriceHistory):
            named = re.search(r"history\.(1y|max)\.json$", relative)
            if named and named.group(1) != parsed.range:
                problems.append(f"{relative}: body range {parsed.range!r} does not match the name")
        ticker = re.search(r"/stocks/([^/]+?)(?:\.json|/)", relative)
        declared = getattr(parsed, "ticker", None)
        if ticker and declared is not None and ticker.group(1) != declared:
            problems.append(f"{relative}: path ticker {ticker.group(1)} != body ticker {declared}")
    if status_release is not None and not (root / "r" / status_release).is_dir():
        problems.append(f"status.json points at release {status_release}, which is not present")
    return problems
