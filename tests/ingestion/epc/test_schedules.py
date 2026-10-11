"""Tests for the EPC jobs, schedule, and the service's Definitions.

Checks that the two jobs select the right asset chains, that the monthly
schedule ships stopped (so it never fires until someone deliberately enables
it), and that the whole `epc.defs` object resolves. Dagster `EnvVar`s are
resolved lazily, so building the Definitions needs no real credentials.
"""

from __future__ import annotations

import dagster as dg

from services.ingestion import epc
from services.ingestion.epc import schedules


def _selected_keys(job_name: str) -> set[str]:
    # Resolve against the real service Definitions so the r2/postgres/epc
    # resources the ops require are already wired in.
    job = epc.defs.resolve_job_def(job_name)
    return {k.to_user_string() for k in job.asset_layer.executable_asset_keys}


def test_backfill_job_selects_the_complete_chain_only():
    assert _selected_keys("epc_backfill_job") == {
        "epc_complete_raw_zip",
        "epc_complete_clean_parquet",
        "epc_complete_loaded_to_postgres",
    }


def test_monthly_job_selects_the_monthly_chain_only():
    assert _selected_keys("epc_monthly_job") == {
        "epc_monthly_raw_zip",
        "epc_monthly_clean_parquet",
        "epc_monthly_loaded_to_postgres",
    }


def test_monthly_schedule_targets_the_monthly_job_and_ships_stopped():
    sched = schedules.epc_monthly_schedule
    assert sched.job.name == "epc_monthly_job"
    assert sched.cron_schedule == "0 4 5 * *"
    # Must not auto-run on deploy; it's flipped to RUNNING by hand when ready.
    assert sched.default_status == dg.DefaultScheduleStatus.STOPPED


def test_service_definitions_expose_both_jobs():
    assert epc.defs.resolve_job_def("epc_backfill_job")
    assert epc.defs.resolve_job_def("epc_monthly_job")
