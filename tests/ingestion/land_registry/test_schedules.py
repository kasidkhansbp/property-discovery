"""Tests for the PPD jobs, schedule, and the service's Definitions.

Checks that the two jobs select the right asset chains, that the monthly
schedule ships stopped (so it never fires until someone deliberately enables
it), and that the whole `land_registry.defs` object resolves. Dagster `EnvVar`s
are resolved lazily, so building the Definitions needs no real credentials.
"""

from __future__ import annotations

import dagster as dg

from services.ingestion import land_registry
from services.ingestion.land_registry import schedules


def _selected_keys(job_name: str) -> set[str]:
    # Resolve against the real service Definitions so the r2/postgres resources
    # the ops require are already wired in.
    job = land_registry.defs.resolve_job_def(job_name)
    return {k.to_user_string() for k in job.asset_layer.executable_asset_keys}


def test_backfill_job_selects_the_complete_chain_only():
    assert _selected_keys("land_registry_ppd_backfill_job") == {
        "ppd_complete_raw_csv",
        "ppd_complete_clean_parquet",
        "ppd_complete_loaded_to_postgres",
    }


def test_monthly_job_selects_the_monthly_chain_only():
    assert _selected_keys("land_registry_ppd_monthly_job") == {
        "ppd_monthly_raw_csv",
        "ppd_monthly_clean_parquet",
        "ppd_monthly_loaded_to_postgres",
    }


def test_monthly_schedule_targets_the_monthly_job_and_ships_stopped():
    sched = schedules.ppd_monthly_schedule
    assert sched.job.name == "land_registry_ppd_monthly_job"
    assert sched.cron_schedule == "0 3 23 * *"
    # Must not auto-run on deploy; it's flipped to RUNNING by hand when ready.
    assert sched.default_status == dg.DefaultScheduleStatus.STOPPED


def test_service_definitions_expose_both_jobs():
    assert land_registry.defs.resolve_job_def("land_registry_ppd_backfill_job")
    assert land_registry.defs.resolve_job_def("land_registry_ppd_monthly_job")
