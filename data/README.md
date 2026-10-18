# data/

Everything NSE Forecast reads and writes lives in this folder. Only this file,
[source/README.md](source/README.md) and `.gitkeep` are in the repository. The dataset files
and everything a run computes stay on your machine and are git-ignored.

## The dataset

NSE Forecast uses the daily end-of-day prices of every security quoted on the Nairobi
Securities Exchange (NSE) from 2 January 2007 to 30 June 2026. Barack Wanjawa publishes them
on Mendeley Data as a series of collections, one per period. NSE Forecast cites the data as:

> Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026",
> Mendeley Data, V1, doi: [10.17632/hvmhnp7f9r.1](https://doi.org/10.17632/hvmhnp7f9r.1)

The citation is kept in [`reference/mendeley.yaml`](../reference/mendeley.yaml), and the run
summary, the app and the README all show it. That file records no licence, so NSE Forecast
treats the data as for personal research use. The prices are the NSE's own end-of-day data.

## Getting the files

The dataset is not in the repository. The results published here were computed from the
Mendeley files, downloaded and placed in `data/source/`. To run NSE Forecast on the real data,
download the same files and place them there:

1. On [Mendeley Data](https://data.mendeley.com/), find the seven collections in the table
   below. Search for "Nairobi Securities Exchange All Stocks Prices" and the period. The 2026
   collection is [doi: 10.17632/hvmhnp7f9r.1](https://doi.org/10.17632/hvmhnp7f9r.1).
2. Put each collection in `data/source/`, either as the downloaded `.zip` file or unzipped,
   but not both. Any folder layout works: NSE Forecast reads every `.csv` and `.zip` file
   under `data/source/` and uses the files named `NSE_data_all_stocks_*.csv` and
   `NSE_data_stock_market_sectors_*.csv`.
3. Run `uv run nsefc run`.

Without the files, `uv run nsefc run` stops with exit code 10 and explains where they go.
`uv run nsefc run --sample` runs the whole tool on a generated synthetic dataset instead, and
`uv run nsefc run --source-dir PATH` reads the files from another folder.

| Collection (folder name used here) | Period | Price files | Sector files |
| --- | --- | --- | --- |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2007-2012 | 2007 to 2012 | 6 | 0 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2013-2020 | 2013 to 30 June 2020 | 8 | 2 |
| Nairobi Securities Exchange (NSE) All Stock Prices 2021 | 2021 | 1 | 1 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2022 | 2022 | 1 | 1 |
| Nairobi Securities Exchange (NSE) All Stocks 2023-2024 | 2023 and 2024 | 2 | 1 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2025 | 2 January to 31 October 2025 | 1 | 1 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2026 | 2 January to 30 June 2026 | 1 | 1 |

### Checking your copy

The corrections in [`reference/corrections.yaml`](../reference/corrections.yaml) are keyed to
each file's SHA-256, so they apply only to the exact files listed below. With these files the
run summary reports 4 corrections applied. If a file differs (a newer version of a collection,
say), its correction does not apply and ingest stops with exit code 20 on the defect the
correction fixes. After `uv run nsefc acquire`, `data/raw/mendeley/hvmhnp7f9r/v1/manifest.json`
lists the full SHA-256 of every file it copied.

| File | Bytes | Rows | First date | Last date | Codes | SHA-256 (first 12) |
| --- | --- | --- | --- | --- | --- | --- |
| `NSE_data_all_stocks_2007.csv` | 843,961 | 10,608 | 2007-01-02 | 2007-12-24 | 54 | `9cf31c14768d` |
| `NSE_data_all_stocks_2008.csv` | 849,672 | 10,583 | 2008-01-02 | 2008-12-31 | 54 | `c68a4142f79f` |
| `NSE_data_all_stocks_2009.csv` | 1,083,066 | 14,386 | 2009-01-02 | 2009-12-31 | 57 | `ac9bdb30a7f7` |
| `NSE_data_all_stocks_2010.csv` | 1,148,209 | 14,952 | 2010-01-04 | 2010-12-31 | 61 | `191a350bf9d8` |
| `NSE_data_all_stocks_2011.csv` | 1,137,773 | 14,931 | 2011-01-03 | 2011-12-30 | 59 | `f5e5a63d036b` |
| `NSE_data_all_stocks_2012.csv` | 1,218,332 | 16,044 | 2012-01-03 | 2012-12-31 | 67 | `ca2c76e96a64` |
| `NSE_data_all_stocks_2013.csv` | 1,221,420 | 14,889 | 2013-01-02 | 2013-12-31 | 58 | `30d0bedbae47` |
| `NSE_data_all_stocks_2014.csv` | 1,302,426 | 15,695 | 2014-01-02 | 2014-12-31 | 61 | `91ad2135c8f3` |
| `NSE_data_all_stocks_2015.csv` | 1,358,547 | 16,386 | 2015-01-02 | 2015-12-31 | 62 | `e3e821e6caa0` |
| `NSE_data_all_stocks_2016.csv` | 1,385,250 | 16,800 | 2016-01-04 | 2016-12-30 | 64 | `2c718a417822` |
| `NSE_data_all_stocks_2017.csv` | 1,396,341 | 16,981 | 2015-05-09 \* | 2017-12-29 | 65 | `1f4f1f6adceb` |
| `NSE_data_all_stocks_2018.csv` | 1,460,278 | 17,650 | 2018-01-02 | 2018-12-31 | 66 | `87def7e669e4` |
| `NSE_data_all_stocks_2019.csv` | 1,514,466 | 18,147 | 2019-01-02 | 2019-12-31 | 66 | `78f51d653bb2` |
| `NSE_data_all_stocks_2020_to_jun30.csv` | 729,602 | 8,733 | 2020-01-02 | 2020-06-30 | 64 | `68138c29405a` |
| `NSE_data_all_stocks_2021_upto_31dec2021.csv` | 1,550,258 | 17,746 | 2021-01-04 | 2021-12-31 | 64 | `d0a451fc3e64` |
| `NSE_data_all_stocks_2022.csv` | 1,390,082 | 16,806 | 2022-01-03 | 2022-12-30 | 66 | `c6b58ea83c8f` |
| `NSE_data_all_stocks_2023.csv` | 1,474,887 | 17,274 | 2023-01-03 | 2023-12-29 | 66 | `9050850c15cc` |
| `NSE_data_all_stocks_2024.csv` | 1,560,791 | 18,119 | 2024-01-02 | 2024-12-31 | 67 | `16c34c7b4fe8` |
| `NSE_data_all_stocks_2025_jan_to_oct.csv` | 1,247,718 | 15,114 | 2025-01-02 | 2025-10-31 | 67 | `7241047984db` |
| `NSE_data_all_stocks_2026_upto_jun.csv` | 773,923 | 9,280 | 2026-01-02 | 2026-06-30 | 71 | `bfc83a381e11` |
| `NSE_data_stock_market_sectors_2013.csv` | 2,702 | 62 | | | | `f8e5c67b562a` |
| `NSE_data_stock_market_sectors_2020.csv` | 3,138 | 71 | | | | `1cf3eb3c01f7` |
| `NSE_data_stock_market_sectors_as_at_31dec2021.csv` | 3,135 | 71 | | | | `f0210b82359a` |
| `NSE_data_stock_market_sectors_2022.csv` | 3,178 | 71 | | | | `50ed8fd9b74a` |
| `NSE_data_stock_market_sectors_2023_2024.csv` | 3,275 | 73 | | | | `263ceb2ed194` |
| `NSE_data_stock_market_sectors_2025.csv` | 3,359 | 75 | | | | `c00c41cdacc3` |
| `NSE_data_stock_market_sectors_2026.csv` | 3,505 | 77 | | | | `8f29403ca3a3` |

\* A misdated block; see [Defects](#defects-and-how-each-is-handled). Rows exclude the
header and blank lines and include index rows; codes count equities only. Sizes and hashes
are for the files with LF line endings. Downloaded copies can have Windows (CRLF) line
endings, which `acquire` converts before hashing and copying, so a checksum tool run on such
a file shows a different value.

## Format

| Column (header case varies) | Canonical column | Notes |
| --- | --- | --- |
| `Date` / `DATE` | `session_date` | Three formats: `02-Jan-25` (2013 on), `1/2/2007` month first (2007 to 2012) |
| `Code` / `CODE` | `ticker` | After alias mapping; codes starting with `^` are index levels |
| `Name` / `NAME` | securities table | Company names change over time; the latest is shown |
| `Day Price` | `close` | The official price: the session's volume-weighted average price (NSE Equity Trading Rules 7.6.1 and 7.6.6) |
| `Previous` | `prev_close_reported` | Missing in 22 rows, four of them the first days of 2026 listings |
| `Day Low`, `Day High` | `low`, `high` | Set to null when the security did not trade |
| (none) | `open` | Not published, so always null |
| `Volume` | `volume` | `-` means no trades (0); thousands separators |
| (none) | `turnover` | Not published, so always null; liquidity rules use volume × close |
| `12m Low`, `12m High`, `Change`, `Change%` | not used | `Change%` has no sign in older files |
| `Adjust` / `Adjusted Price` | not used | Back-adjusted prices for about 13% of rows; NSE Forecast does not back-adjust |

The price files also carry index levels: `^NASI` (from 25 February 2008), `^N20I`, `^N25I`
(from October 2015), `^N10I` (from September 2023), `^FNK15`, `^FNK25` (2013 to 2021),
`^ZKEQTK`, `^ZKEQTU` (from July 2018), `^NBDI` and `^NBSI`. The market features use NASI.
Sector files map codes to sectors, with two header spellings (`SECTOR, CODE, NAME` and
`Sector, Stock_code, Stock_name`).

## Defects and how each is handled

| Finding | Handling | Count |
| --- | --- | --- |
| Three blocks in the 2009 file dated 29 January, 2 April and 8 October sit where 21 January, 4 February and 10 August belong (two are day-month swaps) | `redate` rules R2009-01 to R2009-03 in `reference/corrections.yaml`; the prices chain exactly through each block | 158 rows |
| The 2017 file has a block dated Saturday 9 May 2015 that belongs to 9 May 2017 | `redate` rule R2017-01 | 70 rows |
| Identical duplicate rows | Dropped; after the redates every remaining duplicate is identical | 64 rows |
| Blank lines (`,,,,`) at the end of the 2014 and 2018 files | Skipped and counted | 2 |
| A row without a price (MSC, 16 October 2019) | Check SCH-02: excluded | 1 |
| Moves beyond ±10.5% (splits, bonus and rights issues, listings, errors, moves across a data gap) | Check PRC-01: events, excluded from labels and feature windows | 416 |
| No data from 1 July to 31 December 2020 | Missing sessions, never filled; the gap guard excludes nearby rows | 129 sessions |
| No data from 3 November to 31 December 2025: the 2025 file ends on 31 October and the 2026 file starts on 2 January | Missing sessions, handled the same way | 40 sessions |
| 26 other scheduled weekdays with no data | Missing sessions | 26 |
| 3 and 4 January 2008 quote only 8 and 27 securities | Check MKT-01: market features are null for those sessions | 2 |
| 27 December 2010 and 27 December 2011 traded in full | Held sessions in the trading calendar | 2 |
| The 2007 to 2012 files use old tickers (BBK, BERG, C&G, CFC, ICDC, NIC, FIRE, PAFR, CFCI) | `former_tickers` in `reference/securities.csv`, confirmed from prices: the last 2012 close equals the first 2013 "Previous" | 9 tickers |
| Rights lines (`-R`), preference shares (`-P4`, `-P7`), ETFs (GLD, SMWF) and REITs (FAHR, LAPR, ALP) | `instrument_type` in `reference/securities.csv` (inferred from the sector file for ALP): shown in the app, never in the forecast universe | 17 lines |
| Four securities first quoted in 2026: KPC (10 March), ALP (11 March), FMLY (23 June) and TRFC (29 June); the source cuts off the names of ALP and TRFC | Shown as the source names them; none has the 500 sessions of history the forecast universe needs | 4 securities |

The 2026 file has no duplicate, misdated or weekend rows, and its 122 sessions match the
trading calendar exactly, which confirms the 2026 Idd-ul-Fitr (20 March) and Idd-ul-Azha
(27 May) closures.

After the corrections, the canonical panel has 92 securities (75 ordinary shares), 4,682 held
sessions from 2 January 2007 to 30 June 2026, and 293,848 bars, of which 12,661 are carried
forward. Every run regenerates these numbers in `data/reports/data-audit.md`.

## Layout

```text
data/
├── README.md                     this file (in git)
├── .gitkeep                      keeps the folder in git
├── source/                       the dataset files you download (see above)
│   └── README.md                 in git
├── raw/                          copies of the source files, never modified
│   ├── mendeley/hvmhnp7f9r/v1/   the copy of data/source/ and its manifest.json
│   ├── local/<hash>/             a copy of a --source-dir folder
│   ├── sample/v1/                the generated synthetic sample
│   ├── imports/                  files added with `nsefc import`, and their manifest.json
│   └── active.json               which manifests the next ingest reads
├── canonical/
│   ├── bars.parquet              one row per security and session
│   ├── indices.parquet           index levels (NASI and others)
│   ├── securities.parquet        ticker, name, sector and instrument type
│   ├── sessions.parquet          every scheduled session: held, missing or closed
│   └── ingest_report.json        counts, corrections and quality-check results
├── features/<hash>/table.parquet the modelling table, named by a fingerprint of its inputs
├── models/<run_id>/              fitted models (.joblib), each with a .json sidecar holding
│                                 its SHA-256, and evaluation.json
├── predictions/<run_id>/         walkforward.parquet (every out-of-sample prediction),
│                                 forecast.parquet, forecast_unavailable.parquet, forecast.json
├── reports/                      data-audit.md, evaluation.md and evaluation.json, and
│                                 tuning.json after `nsefc dev tune`
├── api/v1/                       status.json and r/<release_id>/: the JSON files the app reads
├── stamps/                       one file per stage: the fingerprint of its inputs and outputs
└── runs/<run_id>/                log.jsonl and run.json for every run; runs/latest.json names
                                  the latest
```

A `<run_id>` is the run's start time in UTC, such as `20261017T004256Z`. Every manifest
records, for each file, its name, its original path, its size and its SHA-256, so every
canonical row traces back to an exact source file.

`uv run nsefc status` summarises what is in this folder. `uv run nsefc clean` deletes
everything a run computed and keeps `raw/` and `source/`; `uv run nsefc clean --all` deletes
`raw/` as well, never `source/`. To keep this folder somewhere else, set `NSEFC_DATA_DIR`; the
dataset is then read from `source/` inside that folder, unless `paths.source_dir` in
`config/default.yaml` points elsewhere.
