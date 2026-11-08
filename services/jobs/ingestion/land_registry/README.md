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
| `assets.py`     | Both chains, built from one asset factory (`_build_ppd_assets`) |
| `utils.py`      | Shared download / clean / load step logic |
| `schema.py`     | Single source of truth for the PPD column schema + derived SQL |
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

## TODO: load progress / observability

The backfill upsert is a single `INSERT ... ON CONFLICT` over ~31.6M rows, so it
runs for several minutes with **no sub-step progress** anywhere: the Dagster UI
shows only the step clock ticking, and Postgres has no progress view for DML
(`pg_stat_progress_copy` covers the staging COPY, but nothing reports an upsert's
`%`). To make a long load observable:

- **Chunked upsert + per-batch logging** → in `load_to_postgres` (`utils.py`),
  loop the upsert in row-count batches and `context.log.info(...)` each batch, so
  one opaque statement becomes many progress lines.
- **Row-count metadata in the UI** → have `load_to_postgres` *return* its
  `(upserted, deleted)` counts, and surface them from the `loaded_to_postgres`
  asset (`assets.py`) via `dg.MaterializeResult(metadata={...})`.

Keep the split: load logic lives in `utils.py`; Dagster metadata emission lives in
the asset wrapper in `assets.py`. Ad-hoc admin queries (`pg_stat_activity`,
`pg_stat_progress_copy`) are ops tooling — a separate script, not these modules.

## TODO: full end-to-end backfill test via Dagster

So far the **complete** chain has only been validated piecemeal: the 5.5GB
download, the clean, and the ~31.6M-row load were each run on their own (the
clean+load reusing a pre-downloaded R2 object). The orchestration itself is
covered indirectly — both chains come from the same `_build_ppd_assets` factory,
and the **monthly** chain was run end-to-end through Dagster — but the complete
chain has not been run as one job.

Still to do: run `land_registry_ppd_backfill_job` through Dagster (`dagster dev`
or `dagster asset materialize`) so download → clean → load all execute via the
real asset chain on the full file, in one run. Note it re-downloads the full
~5.5GB (the raw asset always fetches a fresh date-stamped key) and takes ~35-40
min end to end.

## TODO: UPRN enrichment (official lookup + coordinates)

HM Land Registry now releases official **PPD → UPRN lookup** tables, and **OS
Open UPRN** provides geographic coordinates (Latitude/Longitude + British
National Grid easting/northing) for every UPRN in Great Britain. Together these
let us attach a stable property identifier and a location to each sale without
fuzzy address matching:

- **PPD → UPRN** → join the HMLR lookup on the PPD transaction id to stamp each
  `land_registry_sales` row with its UPRN.
- **UPRN → coordinates** → join OS Open UPRN on the UPRN to add lat/long + BNG,
  enabling spatial queries and map rendering.

Likely shape: two more `download → DuckDB clean → upsert` chains (reusing the
same step logic in `utils.py`), landing in their own lookup tables, with the
join into `land_registry_sales` done downstream in dbt — keeping ingestion
sources in separate tables, consistent with the land_registry/epc split.
