"""epc's own self-contained Dagster Definitions.

This bundles everything THIS service owns — its assets, its jobs + monthly
schedule, and its resources — into one object. The root `definitions.py` picks
this up (alongside land_registry's) so Dagster can see them all together.

Nothing here touches land_registry or any other service; epc is independent.

Credentials come from the environment (never the repo). Set these before
running: R2_BUCKET, R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
POSTGRES_DSN, and EPC_API_TOKEN.
"""

from __future__ import annotations

import dagster as dg

from . import assets, schedules
from .resources import EpcResource, PostgresResource, R2Resource

defs = dg.Definitions(
    assets=[
        # complete backfill chain (manual)
        assets.epc_complete_raw_zip,
        assets.epc_complete_clean_parquet,
        assets.epc_complete_loaded_to_postgres,
        # monthly refresh chain (scheduled)
        assets.epc_monthly_raw_zip,
        assets.epc_monthly_clean_parquet,
        assets.epc_monthly_loaded_to_postgres,
    ],
    jobs=[schedules.epc_backfill_job, schedules.epc_monthly_job],
    schedules=[schedules.epc_monthly_schedule],
    resources={
        "r2": R2Resource(
            bucket=dg.EnvVar("R2_BUCKET"),
            endpoint_url=dg.EnvVar("R2_ENDPOINT_URL"),
            access_key_id=dg.EnvVar("R2_ACCESS_KEY_ID"),
            secret_access_key=dg.EnvVar("R2_SECRET_ACCESS_KEY"),
        ),
        "postgres": PostgresResource(dsn=dg.EnvVar("POSTGRES_DSN")),
        "epc": EpcResource(auth_token=dg.EnvVar("EPC_API_TOKEN")),
    },
)
