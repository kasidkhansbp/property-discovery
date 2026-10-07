# Tests

Unit tests for the ingestion services. The layout mirrors the package under
`services/`, so a test for `services/ingestion/land_registry/schema.py` lives at
`tests/ingestion/land_registry/test_schema.py`.

## What's covered

These tests exercise the **pure, deterministic logic** that needs no external
systems — they never hit the network, Cloudflare R2, DuckDB, or Postgres:

- `test_schema.py` — the single-source-of-truth PPD schema and the SQL strings
  derived from it (DuckDB read spec, Postgres DDL, upsert `SET` clause).
- `test_assets.py` — the `_build_ppd_assets` factory: asset keys, the
  raw→clean→load dependency wiring, per-chain URLs and delete handling.
- `test_schedules.py` — the backfill/monthly jobs, the monthly schedule's cron
  and stopped-by-default status, and that the service `Definitions` build.

The I/O-bound steps in `utils.py` (`download_to_r2`, `clean_to_parquet`,
`load_to_postgres`) are **not** covered here; they need R2/DuckDB/Postgres and
belong in integration tests against the local Postgres (see the project setup
notes) or fakes.

## Running

```bash
# From the repo root. Install the dev dependencies once:
python -m pip install -r requirements-dev.txt

# Run everything:
python -m pytest

# Run one module:
python -m pytest tests/ingestion/land_registry/test_schema.py
```

Run from the repo root so the `services.ingestion.*` imports resolve, the same
way `dagster dev` resolves them via `workspace.yaml`.
