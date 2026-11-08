"""Jobs and schedule for the EPC pipeline.

Two jobs, matching the two asset chains in assets.py:

  * epc_backfill_job — the one-off full-file load. NO schedule; launch it by hand
    from the Dagster UI (or CLI) once, to seed the table.
  * epc_monthly_job  — the monthly refresh. Runs on a schedule to keep the table
    current after the backfill.
"""

from __future__ import annotations

import dagster as dg

from . import assets

# One-off backfill: the full bulk file. Manually triggered — no schedule attached.
epc_backfill_job = dg.define_asset_job(
    name="epc_backfill_job",
    selection=dg.AssetSelection.assets(
        assets.epc_complete_raw_zip,
        assets.epc_complete_clean_parquet,
        assets.epc_complete_loaded_to_postgres,
    ),
)

# Monthly refresh: download -> clean -> upsert the bulk file again.
epc_monthly_job = dg.define_asset_job(
    name="epc_monthly_job",
    selection=dg.AssetSelection.assets(
        assets.epc_monthly_raw_zip,
        assets.epc_monthly_clean_parquet,
        assets.epc_monthly_loaded_to_postgres,
    ),
)

# EPC's bulk file is refreshed periodically; run early each month to pick up
# newly-lodged certificates. Adjust the cron if the publish cadence shifts.
#   ┌ minute  ┌ hour  ┌ day-of-month  ┌ month  ┌ day-of-week
#   0         4       5               *        *
epc_monthly_schedule = dg.ScheduleDefinition(
    name="epc_monthly",
    job=epc_monthly_job,
    cron_schedule="0 4 5 * *",
    default_status=dg.DefaultScheduleStatus.STOPPED,  # flip to RUNNING when ready
)
