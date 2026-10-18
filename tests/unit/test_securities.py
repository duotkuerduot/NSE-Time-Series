"""Securities and aliases."""

from __future__ import annotations

from pathlib import Path

import pytest

from nsefc.domain import InstrumentType
from nsefc.ingest.securities import alias_map, infer_instrument_type, load_reference


@pytest.mark.parametrize(
    ("code", "name", "kind"),
    [
        ("SCOM", "Safaricom Plc", InstrumentType.ORDINARY),
        ("KCB-R", "KCB Group (Rights)", InstrumentType.RIGHTS),
        ("KPLC-P7", "Kenya Power 7% Pref", InstrumentType.PREFERENCE),
        ("GLD", "ABSA NewGold ETF", InstrumentType.ETF),
        ("FAHR", "ILAM Fahari I-REIT", InstrumentType.REIT),
        ("^NASI", "NSE All Share Index", InstrumentType.INDEX),
    ],
)
def test_instrument_types(code: str, name: str, kind: InstrumentType) -> None:
    assert infer_instrument_type(code, name) is kind


def test_the_sector_identifies_funds_and_trusts_with_truncated_names() -> None:
    # A 2026 listing whose name the source cuts off before "REIT".
    name = "Africa Logistics Properties Industria..."
    assert infer_instrument_type("ALP", name) is InstrumentType.ORDINARY
    assert (
        infer_instrument_type("ALP", name, "Real Estate Investment Trusts") is InstrumentType.REIT
    )
    assert (
        infer_instrument_type("XYZ", "Some Feeder", "Exchange Traded Funds") is InstrumentType.ETF
    )
    assert infer_instrument_type("KPC", "Kenya Pipeline", "Energy and Petroleum") is (
        InstrumentType.ORDINARY
    )


def test_reference_aliases(repo_root: Path) -> None:
    reference = load_reference(repo_root / "reference" / "securities.csv")
    aliases = alias_map(reference)
    assert aliases["BBK"] == "ABSA" and aliases["NIC"] == "NCBA" and aliases["CFC"] == "SBIC"
    assert (
        "Barclays Bank of Kenya" in " ".join(reference["ABSA"].former_names)
        or reference["ABSA"].former_tickers
    )
    kinds = {t: r.instrument_type for t, r in reference.items()}
    assert kinds["KPLC-P7"] is InstrumentType.PREFERENCE and kinds["GLD"] is InstrumentType.ETF
    assert sum(1 for k in kinds.values() if k is InstrumentType.ORDINARY) >= 60


def test_a_ticker_cannot_be_current_and_former(tmp_path: Path) -> None:
    path = tmp_path / "securities.csv"
    path.write_text(
        "ticker,name,sector,instrument_type,former_tickers,former_names,notes\n"
        "AAA,A,,ordinary,BBB,,\nBBB,B,,ordinary,,,\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="current and as a former"):
        alias_map(load_reference(path))


def test_a_reference_file_saved_by_excel_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "securities.csv"
    path.write_bytes(
        b"\xef\xbb\xbfticker,name,sector,instrument_type,former_tickers,former_names,notes\n"
        b"ABSA,Absa Bank Kenya PLC,Banking,ordinary,BBK,Barclays Bank of Kenya,\n"
    )
    assert alias_map(load_reference(path)) == {"BBK": "ABSA"}
