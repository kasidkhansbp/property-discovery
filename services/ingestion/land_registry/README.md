# land_registry ingestion

Downloads UK Land Registry **Price Paid Data (PPD)**, cleans it, and loads it
into Postgres. Self-contained Dagster service: owns its own assets, jobs +
monthly schedule, and writes to its own table (`land_registry_sales`).

Two chains, both `download CSV → DuckDB clean to Parquet → upsert to Postgres`:

| Chain | File | Trigger | Purpose |
|-------|------|---------|---------|
| **complete** | `pp-complete.csv` (~5GB, all history) | **manual** (`land_registry_ppd_backfill_job`) | one-off backfill to seed the table |
| **monthly**  | `pp-monthly-update-new-version.csv` (delta, A/C/D flags) | **scheduled** (`land_registry_ppd_monthly_job`) | keeps the table current |

Run the backfill **once** by hand, then let the monthly schedule maintain it.
The load is idempotent (upsert on the PPD transaction id); the monthly delta
also applies deletes.

## Files
| File | Role |
|------|------|
| `assets.py`     | Both chains + shared download/clean/load helpers |
| `schedules.py`  | Backfill job (manual), monthly job + schedule (`0 3 23 * *`) |
| `resources.py`  | R2 (boto3 + DuckDB httpfs) + Postgres (psycopg) connections |
| `__init__.py`   | Bundles this service's own `Definitions` (resources from env vars) |

The root `../../../definitions.py` collects this service's `defs` (and epc's,
later) into the single entry point Dagster loads. **Data stays in separate
tables** — land_registry and epc are reconciled later in dbt on address/postcode.

Nothing touches the local filesystem: the raw file streams from HMLR straight
into R2, DuckDB reads/writes R2 over httpfs, and Postgres is loaded via DuckDB's
postgres extension.

## Credentials (from the environment — never the repo)
```
R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, POSTGRES_DSN
```

## Run it (from the repo root)
```bash
pip install -r requirements.txt
dagster dev            # opens the UI; you'll see both jobs + the monthly schedule
# then: launch land_registry_ppd_backfill_job once, and turn on the schedule.
```
