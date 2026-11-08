"""A job + monthly schedule per data-quality asset.

Each served table's quality snapshot is its own job (as asked: one job per
table), so any single table's coverage can be rebuilt on its own, and a monthly
schedule refreshes it. The schedules run on the 24th at 09:00 — after the
monthly Land Registry load (23rd), the reconciliation refresh (24th 06:00), and
the coverage mart (24th 08:00) — so each quality snapshot reflects the freshly
loaded data. EPC and OS Open UPRN refresh on their own slower cadences, but
reprofiling them monthly is cheap and simply re-reports their current state.

All schedules default to STOPPED; flip them to RUNNING in the Dagster UI when
you want the monthly refresh to fire.
"""

from __future__ import annotations

import dagster as dg

from . import assets

# One job per table.
land_registry_sales_quality_job = dg.define_asset_job(
    name="land_registry_sales_quality_job",
    selection=dg.AssetSelection.assets(assets.land_registry_sales_quality),
)
epc_domestic_certificates_quality_job = dg.define_asset_job(
    name="epc_domestic_certificates_quality_job",
    selection=dg.AssetSelection.assets(assets.epc_domestic_certificates_quality),
)
os_open_uprn_quality_job = dg.define_asset_job(
    name="os_open_uprn_quality_job",
    selection=dg.AssetSelection.assets(assets.os_open_uprn_quality),
)
property_uprn_mapping_quality_job = dg.define_asset_job(
    name="property_uprn_mapping_quality_job",
    selection=dg.AssetSelection.assets(assets.property_uprn_mapping_quality),
)
key_duplication_quality_job = dg.define_asset_job(
    name="key_duplication_quality_job",
    selection=dg.AssetSelection.assets(assets.key_duplication_quality),
)

# Monthly refresh for each, on the 24th at 09:00 (after the loads + the mart).
#   ┌ minute  ┌ hour  ┌ day-of-month  ┌ month  ┌ day-of-week
#   0         9       24              *        *
_MONTHLY_CRON = "0 9 24 * *"

land_registry_sales_quality_schedule = dg.ScheduleDefinition(
    name="land_registry_sales_quality_monthly",
    job=land_registry_sales_quality_job,
    cron_schedule=_MONTHLY_CRON,
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
epc_domestic_certificates_quality_schedule = dg.ScheduleDefinition(
    name="epc_domestic_certificates_quality_monthly",
    job=epc_domestic_certificates_quality_job,
    cron_schedule=_MONTHLY_CRON,
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
os_open_uprn_quality_schedule = dg.ScheduleDefinition(
    name="os_open_uprn_quality_monthly",
    job=os_open_uprn_quality_job,
    cron_schedule=_MONTHLY_CRON,
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
property_uprn_mapping_quality_schedule = dg.ScheduleDefinition(
    name="property_uprn_mapping_quality_monthly",
    job=property_uprn_mapping_quality_job,
    cron_schedule=_MONTHLY_CRON,
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
key_duplication_quality_schedule = dg.ScheduleDefinition(
    name="key_duplication_quality_monthly",
    job=key_duplication_quality_job,
    cron_schedule=_MONTHLY_CRON,
    default_status=dg.DefaultScheduleStatus.STOPPED,
)
