"""Monthly schedule for the Land Registry PPD pipeline.

PPD is published monthly, so we run the whole asset chain on the 1st of each
month. Dagster fires the job; the assets do the download -> clean -> load work.
"""

from __future__ import annotations

import dagster as dg

from . import assets

# A job that materializes every land_registry asset (the full download -> load chain).
ppd_job = dg.define_asset_job(
    name="land_registry_ppd_job",
    selection=dg.AssetSelection.assets(
        assets.ppd_raw_csv,
        assets.ppd_clean_parquet,
        assets.ppd_loaded_to_postgres,
    ),
)

# Run at 03:00 on the 1st of every month.
#   ┌ minute  ┌ hour  ┌ day-of-month  ┌ month  ┌ day-of-week
#   0         3       1               *        *
ppd_monthly_schedule = dg.ScheduleDefinition(
    name="land_registry_monthly",
    job=ppd_job,
    cron_schedule="0 3 1 * *",
    default_status=dg.DefaultScheduleStatus.STOPPED,  # flip to RUNNING when ready
)
