"""Draft reference/securities.csv from a folder of dataset files (run once, then review by hand).

    uv run python scripts/build_securities.py data/source > reference/securities.csv.draft

Former tickers below were confirmed from prices: the 2012 file's last close for each old code
equals the first "Previous" for the new code in 2013.
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

from nsefc.ingest.reader import is_price_file, is_sector_file, read_price_file, read_sector_file
from nsefc.ingest.securities import REFERENCE_COLUMNS, infer_instrument_type

FORMER = {
    "ABSA": ["BBK"],
    "CRWN": ["BERG"],
    "CGEN": ["C&G"],
    "SBIC": ["CFC"],
    "CTUM": ["ICDC"],
    "NCBA": ["NIC"],
    "SMER": ["FIRE"],
    "SLAM": ["PAFR"],
    "LBTY": ["CFCI"],
}
TYPES = {"GLD": "etf", "SMWF": "etf", "FAHR": "reit", "LAPR": "reit"}


def main(folder: Path) -> None:
    former_of = {old: new for new, olds in FORMER.items() for old in olds}
    names: dict[str, Counter[str]] = defaultdict(Counter)
    last_name: dict[str, tuple[object, str]] = {}
    sectors: dict[str, str] = {}
    for path in sorted(folder.rglob("*.csv")):
        if is_price_file(path.name):
            rows = read_price_file(path, sha256="", relative_name=path.name).rows
            for code, day, name in zip(
                rows["code"], rows["session_date"], rows["name"], strict=True
            ):
                if code.startswith("^"):
                    continue
                ticker = former_of.get(code, code)
                names[ticker][name] += 0  # register the ticker even when its name is blank
                if name:
                    names[ticker][name] += 1
                    if ticker not in last_name or day >= last_name[ticker][0]:
                        last_name[ticker] = (day, name)
        elif is_sector_file(path.name):
            for code, sector in zip(
                *(read_sector_file(path)[c] for c in ("code", "sector")), strict=True
            ):
                sectors[former_of.get(code, code)] = sector
    writer = csv.DictWriter(sys.stdout, fieldnames=REFERENCE_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for ticker in sorted(names):
        name = last_name.get(ticker, (None, ticker))[1]
        kind = TYPES.get(ticker) or infer_instrument_type(ticker, name).value
        writer.writerow(
            {
                "ticker": ticker,
                "name": name,
                "sector": sectors.get(ticker, ""),
                "instrument_type": kind,
                "former_tickers": "|".join(FORMER.get(ticker, [])),
                "former_names": "|".join(sorted(set(names[ticker]) - {name, ""})),
                "notes": "",
            }
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
