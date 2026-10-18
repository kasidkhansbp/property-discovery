# os_open_uprn ingestion

Loads Ordnance Survey **OS Open UPRN** — the master reference table mapping every
UPRN in Great Britain to its authoritative coordinates — into Postgres.
Self-contained Dagster service: owns its own assets + (manual) job, and writes to
its own table (`os_open_uprn`).

One chain, `download → clean → diff-merge to Postgres`:

| Step | What it does |
|------|--------------|
| **download** | Ask the OS Downloads API for the current CSV release and stream its ZIP into R2 — **unless** the release md5 matches the one already loaded, in which case the whole run is skipped before any transfer |
| **clean**    | Extract the data CSV from the ZIP, cast the 5 columns, write clean Parquet |
| **load**     | Diff-merge the clean Parquet into `os_open_uprn`: **INSERT** new UPRNs, **UPDATE** only rows whose coordinates moved, **DELETE** UPRNs that dropped out of the release |

### Source: the OS Downloads API (no key)

OS Open UPRN is a free **OpenData** product, published every ~6 weeks as one
zipped CSV for the whole of GB (no per-record API, no delta feed). We fetch it
from the OS Data Hub Downloads API, which needs **no API key**:

```
GET https://api.os.uk/downloads/v1/products/OpenUPRN/downloads
```

That returns a list of downloads; we pick the `format: CSV`, `area: GB` entry and
stream its (redirecting) `url` into R2. The entry also carries an `md5`, which is
the release fingerprint used to skip unchanged runs. The CSV inside the ZIP has a
header and five columns — `UPRN, X_COORDINATE, Y_COORDINATE, LATITUDE, LONGITUDE`
— matched to the schema **by header name** (so OS reordering columns is harmless;
a rename fails loudly).

### Why diff-merge (not truncate+reload or blanket upsert)

The table is ~40M rows but only a small fraction changes each release (new UPRNs,
the odd coordinate correction, rare retirements). Truncate+reload and blanket
upsert both rewrite *every* row (dead tuples, index churn, bloat); the diff-merge
writes **only what genuinely changed**. The INSERT/UPDATE/DELETE run in one
transaction, so a mid-load failure rolls back and the live table is untouched.

Two layers avoid redundant work: the **API md5** skips the whole run (including
the ~600MB download) when the release is unchanged, and the **diff-merge** never
rewrites the unchanged rows between two different releases. The last-loaded md5
is recorded in `os_open_uprn_load_state`.

## Files
| File | Role |
|------|------|
| `assets.py`     | The download → clean → load chain + the Downloads API URL |
| `utils.py`      | API fetch (with md5 skip), ZIP extract + clean, staging/diff-merge load |
| `schema.py`     | Single source of truth for the 5-column schema + derived SQL |
| `schedules.py`  | The manual `os_open_uprn_load_job` (no schedule) |
| `resources.py`  | R2 (boto3 + DuckDB httpfs) + Postgres (psycopg) connections |
| `__init__.py`   | Bundles this service's own `Definitions` (resources from env vars) |

The root `../../../definitions.py` folds this service's `defs` in alongside the
others. **Data stays in its own table** — it's joined to sales/EPC downstream on
UPRN (see the reconciliation service).

Only the ZIP extraction touches local disk (transiently); the raw download and
the Postgres load stream, and DuckDB reads/writes Parquet over httpfs.

## Credentials (from the environment — never the repo)
```
R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, POSTGRES_DSN
```
(No OS credential — the OpenData download is unauthenticated.)

## Run it (from the repo root)
```bash
pip install -r requirements.txt
dagster dev            # opens the UI; launch os_open_uprn_load_job
# or headless:
dagster job launch -j os_open_uprn_load_job
```
