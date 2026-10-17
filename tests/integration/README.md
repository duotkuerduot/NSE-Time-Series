# Integration tests

* `test_pipeline_sample.py`: the whole pipeline on the synthetic sample through the CLI
  (published files validate, every forecast-universe stock has a forecast or a reason,
  repeat runs are cached and byte-identical, G-PLAUS and contract failures give exit codes 30
  and 40).
* `test_real_dataset.py`: acquire and ingest of the committed `NSE Data/` folder reproduce
  the documented counts and corrections.
