"""Leakage rule L2: banned constructs in nsefc/features fail CI (ENGINEERING.md 12.4, 27.2).

Negative shifts, centred windows, back-fill and interpolation can all pull future values into
a feature. The scan runs over the features package from Phase 0, so the rule holds from the
first line of feature code.
"""

from __future__ import annotations

import ast
from pathlib import Path

FEATURES = Path(__file__).resolve().parents[2] / "src" / "nsefc" / "features"
BANNED_METHODS = {"bfill", "backfill", "interpolate"}


def violations(source: str, filename: str = "<string>") -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in BANNED_METHODS:
            found.append(f"{filename}:{node.lineno} {name}() is banned")
        if name == "fillna":
            for kw in node.keywords:
                if (
                    kw.arg == "method"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value in {"bfill", "backfill"}
                ):
                    found.append(f"{filename}:{node.lineno} fillna(method={kw.value.value!r})")
        for kw in node.keywords:
            if kw.arg == "center" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                found.append(f"{filename}:{node.lineno} center=True is banned")
        if name == "shift":
            args = [*node.args, *(kw.value for kw in node.keywords if kw.arg == "periods")]
            for arg in args:
                if (isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub)) or (
                    isinstance(arg, ast.Constant) and isinstance(arg.value, int) and arg.value < 0
                ):
                    found.append(f"{filename}:{node.lineno} negative shift is banned")
    return found


def test_features_package_has_no_banned_constructs() -> None:
    problems = []
    for path in FEATURES.rglob("*.py"):
        problems += violations(path.read_text(encoding="utf-8"), str(path))
    assert problems == []


def test_scanner_catches_each_banned_construct() -> None:
    code = "\n".join(
        [
            "a = df.shift(-1)",
            "b = df.shift(periods=-2)",
            "c = df.rolling(5, center=True).mean()",
            "d = df.bfill()",
            "e = df.fillna(method='backfill')",
            "f = df.interpolate()",
            "g = df.shift(1)",
        ]
    )
    assert len(violations(code)) == 6
