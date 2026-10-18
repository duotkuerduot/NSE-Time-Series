# Reference data

Hand-checked data that every ingest reads. Changes go through a reviewed pull request and cite
their evidence.

| File | What it holds |
| --- | --- |
| `mendeley.yaml` | The dataset's identity and citation: Mendeley Data id, version, title, authors, DOI, URL and licence. The app, the README and the run summary show this citation. The dataset files themselves go in `data/source/` ([data/README.md](../data/README.md)) |
| `corrections.yaml` | Documented fixes to the source files. Each rule is keyed to the SHA-256 of the file it fixes and to a line range inside it, so it never applies to a different file |
| `securities.csv` | Every ticker's current name, sector, instrument type, former tickers and former names |

`securities.csv` was drafted with `scripts/build_securities.py` from the dataset and then
checked by hand. Former tickers were confirmed from prices: the last 2012 close under the old
code equals the first 2013 "Previous" under the new one. Only `ordinary` securities can enter
the forecast universe; rights, preference shares, ETFs and REITs are shown in the app but never
forecast.
