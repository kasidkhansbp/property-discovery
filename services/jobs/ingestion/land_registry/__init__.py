"""land_registry's own self-contained Dagster Definitions.

This bundles everything THIS service owns — its assets, its jobs + monthly
schedule, and its resources — into one object. The root `definitions.py` picks
this up (alongside epc's, later) so Dagster can see them all together.

Nothing here touches epc or any other service; land_registry is independent.

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
        # complete backfill chain (manual)
        assets.ppd_complete_raw_csv,
        assets.ppd_complete_clean_parquet,
        assets.ppd_complete_loaded_to_postgres,
        # monthly delta chain (scheduled)
        assets.ppd_monthly_raw_csv,
        assets.ppd_monthly_clean_parquet,
        assets.ppd_monthly_loaded_to_postgres,
    ],
    jobs=[schedules.ppd_backfill_job, schedules.ppd_monthly_job],
    schedules=[schedules.ppd_monthly_schedule],
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
