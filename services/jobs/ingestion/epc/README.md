# epc ingestion

Downloads UK **Energy Performance Certificate (EPC)** domestic certificate data
from MHCLG's [Get energy performance of buildings data](https://get-energy-performance-data.communities.gov.uk/)
service, cleans it, and loads it into Postgres. Self-contained Dagster service:
owns its own assets, jobs + monthly schedule, and writes to its own table
(`epc_domestic_certificates`).

Two chains, both `download ZIP → DuckDB clean to Parquet → upsert to Postgres`:

| Chain | File | Trigger | Purpose |
|-------|------|---------|---------|
| **complete** | domestic full-load ZIP (full) | **manual** (`epc_backfill_job`) | one-off backfill to seed the table |
| **monthly**  | the same bulk ZIP, re-processed | **scheduled** (`epc_monthly_job`) | keeps the table current |

Run the backfill **once** by hand, then let the monthly schedule maintain it.
The load is idempotent (upsert on the EPC certificate reference, `certificate_number`). EPC
publishes no delta file and certificates are immutable — a re-lodged property
gets a brand-new `certificate_number` — so the monthly chain simply re-loads the bulk file
and upserts; there are **no deletes** to apply (the one place this differs from
land_registry's monthly delta).

## Files
| File | Role |
|------|------|
| `assets.py`     | Both chains, built from one asset factory (`_build_epc_assets`) |
| `utils.py`      | Shared download / clean / load step logic |
| `schema.py`     | Single source of truth for the EPC column schema + derived SQL |
| `schedules.py`  | Backfill job (manual), monthly job + schedule (`0 4 5 * *`) |
| `resources.py`  | R2 (boto3 + DuckDB httpfs) + Postgres (psycopg) + EPC API credential |
| `__init__.py`   | Bundles this service's own `Definitions` (resources from env vars) |

The root `../../../definitions.py` collects this service's `defs` (and
land_registry's) into the single entry point Dagster loads. **Data stays in
separate tables** — epc and land_registry are reconciled later in dbt on
address/postcode (or UPRN, which EPC carries natively).

Only the clean step touches local disk, and only transiently: EPC's bulk file is
a ZIP of per-year `.csv` files, which DuckDB can't read in place over httpfs, so
the raw ZIP is pulled back from R2 to a temp dir, the CSV members are extracted,
and DuckDB reads them as a glob. The raw download and the Postgres load still
stream end-to-end.

## Schema
EPC's domestic CSV carries a header and ~90 `lowercase_snake_case` columns; we
project the useful subset (identity + address + the core energy fields) in
`schema.py`, keyed on `certificate_number` (the report reference number; there is
no `lmk_key` in this service's data). The CSV is read `all_varchar` and cast in
the cleaning SELECT, so a column that drifts type across the per-year files can't
break the read.

## Credentials (from the environment — never the repo)
```
R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, POSTGRES_DSN, EPC_API_TOKEN
```
`EPC_API_TOKEN` is the **bearer token** the bulk endpoint requires. Sign in (or
create an account) with GOV.UK One Login at
<https://get-energy-performance-data.communities.gov.uk/> and copy the token from
your "my account" page. It is sent as `Authorization: Bearer <token>`.

## Run it (from the repo root)
```bash
pip install -r requirements.txt
dagster dev            # opens the UI; you'll see both jobs + the monthly schedule
# then: launch epc_backfill_job once, and turn on the schedule.
```

## Note: source URL / service

The bulk endpoint is
`api.get-energy-performance-data.communities.gov.uk/api/files/domestic/csv`
(see `EPC_DOMESTIC_URL` in `assets.py`), MHCLG's "Get energy performance of
buildings data" service that replaced the retired Open Data Communities site.
It is gated behind a GOV.UK One Login **bearer token** (see `EpcResource` in
`resources.py`) and answers with a `302` redirect to a presigned S3 URL for a
ZIP of per-year certificate CSVs (regenerated on the 1st of each month); the
`requests` download follows that redirect transparently.

## TODO: non-domestic certificates + recommendations

This service currently ingests **domestic certificates** only. EPC also publishes
**non-domestic certificates** and a per-certificate **recommendations** file.
Likely shape: more `download → DuckDB clean → upsert` chains (reusing the step
logic in `utils.py`), each landing in its own table, consistent with the
one-source-one-table split.

## TODO: UPRN-based reconciliation with land_registry

EPC rows carry a native **UPRN**, and the land_registry TODO adds a PPD→UPRN
lookup. Once both sides carry UPRN, the epc ↔ land_registry join can be done on
UPRN downstream in dbt rather than by fuzzy address/postcode matching.
