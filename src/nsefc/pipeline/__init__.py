"""Runs the stages in order with caching.

acquire -> ingest -> train (and evaluate) -> predict -> publish. Each stage fingerprints its
inputs, skips itself when its stamp in ``data/stamps/`` matches, writes its outputs to a
temporary folder and swaps them into place, and logs to ``data/runs/<run_id>/log.jsonl``.
Only the CLI imports this package.
"""
