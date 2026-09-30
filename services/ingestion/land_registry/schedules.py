"""Jobs and schedule for the Land Registry PPD pipeline.

Two jobs, matching the two asset chains in assets.py:

  * ppd_backfill_job — the one-off ~5GB complete-file load. NO schedule; launch
    it by hand from the Dagster UI (or CLI) once, to seed the table.
  * ppd_monthly_job  — the small monthly delta. Runs on a schedule to keep the
    table current after the backfill.
"""

from __future__ import annotations

import dagster as dg

from . import assets

# One-off backfill: the full history. Manually triggered — no schedule attached.
ppd_backfill_job = dg.define_asset_job(
    name="land_registry_ppd_backfill_job",
    selection=dg.AssetSelection.assets(
        assets.ppd_complete_raw_csv,
        assets.ppd_complete_clean_parquet,
        assets.ppd_complete_loaded_to_postgres,
    ),
)

# Monthly delta: download -> clean -> apply the update.
ppd_monthly_job = dg.define_asset_job(
    name="land_registry_ppd_monthly_job",
    selection=dg.AssetSelection.assets(
        assets.ppd_monthly_raw_csv,
        assets.ppd_monthly_clean_parquet,
        assets.ppd_monthly_loaded_to_postgres,
    ),
)

# PPD's monthly update is published around the 20th; run a few days after to be
# safe. Adjust the cron if HMLR's cadence shifts.
#   ┌ minute  ┌ hour  ┌ day-of-month  ┌ month  ┌ day-of-week
#   0         3       23              *        *
ppd_monthly_schedule = dg.ScheduleDefinition(
    name="land_registry_monthly",
    job=ppd_monthly_job,
    cron_schedule="0 3 23 * *",
    default_status=dg.DefaultScheduleStatus.STOPPED,  # flip to RUNNING when ready
)
