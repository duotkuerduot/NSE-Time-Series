"""Securities, aliases and instrument types.

``reference/securities.csv`` is reviewed by hand. It maps former tickers to current ones (the
2007-2012 files use old codes such as BBK for what is now ABSA) and records instrument types.
Securities it does not list (new listings, the synthetic sample) get a type inferred from
their code, name and sector.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from nsefc.domain import InstrumentType

RIGHTS = re.compile(r"-R$")
PREFERENCE = re.compile(r"-P\d+$")
REFERENCE_COLUMNS = [
    "ticker",
    "name",
    "sector",
    "instrument_type",
    "former_tickers",
    "former_names",
    "notes",
]


@dataclass(frozen=True, slots=True)
class ReferenceSecurity:
    ticker: str
    name: str
    sector: str
    instrument_type: InstrumentType
    former_tickers: tuple[str, ...]
    former_names: tuple[str, ...]
    notes: str


def infer_instrument_type(code: str, name: str, sector: str = "") -> InstrumentType:
    upper, group = name.upper(), sector.upper()
    if code.startswith("^"):
        return InstrumentType.INDEX
    if RIGHTS.search(code) or "(RIGHTS)" in upper:
        return InstrumentType.RIGHTS
    if PREFERENCE.search(code) or re.search(r"\b\d+(\.\d+)?%", name):
        return InstrumentType.PREFERENCE
    # The sector files group funds and trusts, whose names the source sometimes truncates
    # (2026: "Africa Logistics Properties Industria...").
    if re.search(r"\bETF\b", upper) or "EXCHANGE TRADED FUND" in group:
        return InstrumentType.ETF
    if "REIT" in upper or "REAL ESTATE INVESTMENT TRUST" in group:
        return InstrumentType.REIT
    return InstrumentType.ORDINARY


def load_reference(path: Path) -> dict[str, ReferenceSecurity]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:  # Excel adds a BOM
        rows = list(csv.DictReader(handle))
    out = {}
    for row in rows:
        ticker = row["ticker"].strip()
        if not ticker:
            continue
        out[ticker] = ReferenceSecurity(
            ticker=ticker,
            name=row.get("name", "").strip(),
            sector=row.get("sector", "").strip(),
            instrument_type=InstrumentType(
                row.get("instrument_type", "ordinary").strip() or "ordinary"
            ),
            former_tickers=tuple(t for t in row.get("former_tickers", "").split("|") if t.strip()),
            former_names=tuple(n for n in row.get("former_names", "").split("|") if n.strip()),
            notes=row.get("notes", "").strip(),
        )
    return out


def alias_map(reference: dict[str, ReferenceSecurity]) -> dict[str, str]:
    """Former ticker -> current ticker. A ticker may not be both current and former."""
    mapping: dict[str, str] = {}
    for security in reference.values():
        for former in security.former_tickers:
            if former in reference:
                raise ValueError(
                    f"{former} is listed as current and as a former ticker of {security.ticker}"
                )
            if former in mapping and mapping[former] != security.ticker:
                raise ValueError(f"{former} maps to both {mapping[former]} and {security.ticker}")
            mapping[former] = security.ticker
    return mapping


def build_securities(
    bars: pd.DataFrame,
    names: pd.DataFrame,
    sectors: pd.DataFrame,
    reference: dict[str, ReferenceSecurity],
    active_from: pd.Timestamp,
) -> pd.DataFrame:
    """One row per ticker: name, sector, type, first and last session, former names.

    ``names`` holds (ticker, session_date, name) from the source rows; the latest wins.
    ``sectors`` holds (ticker, sector, file_order); the most recent sector file wins.
    """
    observed = bars[~bars["is_carried_forward"]]
    spans = observed.groupby("ticker")["session_date"].agg(["min", "max"])
    latest_names = (
        names.sort_values(["ticker", "session_date"])
        .groupby("ticker")["name"]
        .agg(lambda s: next((n for n in reversed(s.tolist()) if n), ""))
    )
    seen_names = names.groupby("ticker")["name"].agg(lambda s: sorted({n for n in s if n}))
    sector_of = (
        sectors.sort_values("file_order").groupby("ticker")["sector"].last()
        if not sectors.empty
        else pd.Series(dtype=str)
    )
    records = []
    for ticker, (first, last) in spans.iterrows():
        ref = reference.get(str(ticker))
        name = (
            (ref.name if ref and ref.name else "")
            or str(latest_names.get(ticker, ""))
            or str(ticker)
        )
        sector = (ref.sector if ref and ref.sector else "") or str(sector_of.get(ticker, "") or "")
        kind = ref.instrument_type if ref else infer_instrument_type(str(ticker), name, sector)
        former = sorted(
            set(ref.former_names if ref else ()) | set(seen_names.get(ticker, [])) - {name}
        )
        records.append(
            {
                "ticker": str(ticker),
                "name": name,
                "sector": sector or None,
                "instrument_type": kind.value,
                "first_session": first,
                "last_session": last,
                # Quoted on the dataset's last session or later: active. Imports that cover
                # only some securities do not make the others look delisted.
                "status": "active" if last >= active_from else "delisted",
                "former_tickers": "|".join(ref.former_tickers) if ref else "",
                "former_names": "|".join(former),
            }
        )
    frame = pd.DataFrame.from_records(records)
    return frame.sort_values("ticker").reset_index(drop=True)
