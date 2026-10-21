"""reconciliation's own self-contained Dagster Definitions.

This service is the *bridge*: it maps HM Land Registry transactions
(``transaction_id``) to EPC UPRNs, producing the ``property_uprn_mapping``
master table described in data-platform-structure.md. Unlike land_registry and
epc, it ingests nothing from the outside world — it reads the two core tables
those services already loaded into Postgres and reconciles them.

As with the other services, this bundles everything THIS service owns — its
assets, its jobs + monthly schedule, and its resources — into one object. The
root ``definitions.py`` folds it in alongside land_registry's and epc's.

The R2 / Postgres connections are literally *reused* from land_registry (see
resources.py), so the same ``r2`` / ``postgres`` resource instances the root
binds for the other services serve this one too.

Credentials come from the environment (never the repo). Set these before
running: R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
and POSTGRES_DSN.
"""

from __future__ import annotations

import dagster as dg

from . import assets, schedules
from .resources import PostgresResource, R2Resource

defs = dg.Definitions(
    assets=[
        # full rebuild chain (manual — run once after the LR/EPC backfills)
        assets.reconciliation_full_normalized,
        assets.reconciliation_full_master_parquet,
        assets.reconciliation_full_loaded_to_postgres,
        # incremental chain (scheduled — keeps the bridge current, protecting
        # transaction_ids already decided on earlier runs)
        assets.reconciliation_incremental_normalized,
        assets.reconciliation_incremental_master_parquet,
        assets.reconciliation_incremental_loaded_to_postgres,
        # downstream mart — pre-aggregated coverage metrics, rebuilt after
        # either load chain
        assets.mart_uprn_coverage_metrics,
    ],
    jobs=[
        schedules.reconciliation_full_job,
        schedules.reconciliation_monthly_job,
        # standalone mart build — rebuilds mart_uprn_coverage_metrics on its own
        schedules.mart_coverage_metrics_job,
    ],
    schedules=[
        schedules.reconciliation_monthly_schedule,
        schedules.mart_coverage_metrics_schedule,
    ],
    resources={
        "r2": R2Resource(
            bucket=dg.EnvVar("R2_BUCKET"),
            endpoint_url=dg.EnvVar("R2_ENDPOINT_URL"),
            access_key_id=dg.EnvVar("R2_ACCESS_KEY_ID"),
            secret_access_key=dg.EnvVar("R2_SECRET_ACCESS_KEY"),
        ),
        "postgres": PostgresResource(dsn=dg.EnvVar("POSTGRES_DSN")),
    },
)
