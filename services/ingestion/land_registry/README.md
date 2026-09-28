# land_registry ingestion

Downloads UK Land Registry **Price Paid Data (PPD)**, cleans it, and loads it
into Postgres. Self-contained Dagster service: owns its own assets, its own
monthly schedule, and writes to its own table (`land_registry_sales`).

## Files
| File | Role |
|------|------|
| `assets.py`     | The pipeline: download CSV → DuckDB clean to Parquet → load to Postgres |
| `schedules.py`  | Monthly job (`0 3 1 * *` — 03:00 on the 1st) |
| `resources.py`  | R2 + Postgres connections |
| `__init__.py`   | Bundles this service's own `Definitions` |

The root `../../../definitions.py` collects this service's `defs` (and epc's,
later) into the single entry point Dagster loads. **Data stays in separate
tables** — land_registry and epc are reconciled later in dbt on address/postcode.

## Run it (from the repo root)
```bash
pip install -r requirements.txt
dagster dev            # opens the UI; you'll see the land_registry assets + schedule
```
