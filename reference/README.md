# Reference data

Reviewed by pull request; read on every ingest (ENGINEERING.md §6.4, §6.5).

| File | What it holds |
| --- | --- |
| `mendeley.yaml` | The dataset's citation, DOI, URL and licence (the data itself is in `NSE Data/`, decision D-10) |
| `corrections.yaml` | Documented fixes to source files, each keyed to the SHA-256 of the file it fixes |
| `securities.csv` | Current ticker, name, sector, instrument type, former tickers and former names |

`securities.csv` was drafted with `scripts/build_securities.py` from the dataset and then
checked by hand. Former tickers were confirmed from prices: the last 2012 close under the old
code equals the first 2013 "Previous" under the new one. Only `ordinary` securities can enter
the forecast universe; rights, preference shares, ETFs and REITs are display-only.
