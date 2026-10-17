# End-to-end tests (§16.5)

* `tests/integration/test_pipeline_sample.py` runs `nsefc run --sample --no-serve` through the
  CLI and checks the published files, caching, idempotency and exit codes.
* `web/e2e/sample.spec.ts` drives a real browser (Playwright, with axe accessibility checks)
  against `nsefc serve` on the sample results. CI's `browser` job runs it:

  ```bash
  uv run nsefc run --sample --no-serve
  uv run nsefc serve --no-browser --port 8765 &
  NSEFC_E2E_URL=http://127.0.0.1:8765 pnpm -C web e2e
  ```

* `web/e2e/smoke.spec.ts` runs the same checks against the contract fixtures (`pnpm -C web e2e`).
