# data/

Everything here is produced by `uv run nsefc run` on your machine and is never committed
(only this file and `.gitkeep` are). The dataset itself ships in `NSE Data/`; see
`docs/data/mendeley-dataset.md`.

```text
data/
├── raw/                 copies of the dataset files (or the sample, or your imports), with
│                        manifest.json files recording each file's SHA-256; never modified
├── canonical/           bars, indices, securities and sessions (Parquet) and ingest_report.json
├── features/            the modelling table, cached by a fingerprint of its inputs
├── models/<run_id>/     model artifacts (.joblib with a .json sidecar holding their SHA-256)
├── predictions/<run_id>/ walk-forward predictions and the forward forecast
├── reports/             data-audit.md, evaluation.md and evaluation.json
├── api/v1/              the JSON files the web app reads
├── stamps/              one file per stage: the fingerprint of its inputs, for caching
└── runs/<run_id>/       log.jsonl and run.json for every run; latest.json names the last one
```

`uv run nsefc clean` deletes everything except `raw/`; `uv run nsefc clean --all` deletes
`raw/` too. Set `NSEFC_DATA_DIR` to keep this folder somewhere else.
