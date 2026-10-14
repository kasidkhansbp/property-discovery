"""Jobs and schedule for the UPRN reconciliation pipeline.

Two jobs, matching the two asset chains in assets.py:

  * reconciliation_full_job    — the one-off rebuild of the whole bridge table.
    NO schedule; launch it by hand from the Dagster UI (or CLI) once, after the
    land_registry and epc backfills have populated their tables.
  * reconciliation_monthly_job — the incremental refresh. Runs on a schedule to
    reconcile the new transactions after the monthly Land Registry delta loads.
"""

from __future__ import annotations

import dagster as dg

from . import assets

# One-off full rebuild. Manually triggered — no schedule attached.
reconciliation_full_job = dg.define_asset_job(
    name="reconciliation_full_job",
    selection=dg.AssetSelection.assets(
        assets.reconciliation_full_normalized,
        assets.reconciliation_full_master_parquet,
        assets.reconciliation_full_loaded_to_postgres,
    ),
)

# Incremental refresh: normalize -> match the new transactions -> load.
reconciliation_monthly_job = dg.define_asset_job(
    name="reconciliation_monthly_job",
    selection=dg.AssetSelection.assets(
        assets.reconciliation_incremental_normalized,
        assets.reconciliation_incremental_master_parquet,
        assets.reconciliation_incremental_loaded_to_postgres,
    ),
)

# The bridge is refreshed right after the Land Registry monthly delta (published
# around the 20th, loaded on the 23rd). Run a day later so the new sales are in
# place before reconciling. Adjust the cron if the upstream cadence shifts.
#   ┌ minute  ┌ hour  ┌ day-of-month  ┌ month  ┌ day-of-week
#   0         6       24              *        *
reconciliation_monthly_schedule = dg.ScheduleDefinition(
    name="reconciliation_monthly",
    job=reconciliation_monthly_job,
    cron_schedule="0 6 24 * *",
    default_status=dg.DefaultScheduleStatus.STOPPED,  # flip to RUNNING when ready
)
