"""land_registry's own self-contained Dagster Definitions.

This bundles everything THIS service owns — its assets, its monthly schedule,
and its resources — into one object. The root `definitions.py` picks this up
(alongside epc's, later) so Dagster can see them all together.

Nothing here touches epc or any other service; land_registry is independent.
"""

from __future__ import annotations

import dagster as dg

from . import assets, schedules

defs = dg.Definitions(
    assets=[
        assets.ppd_raw_csv,
        assets.ppd_clean_parquet,
        assets.ppd_loaded_to_postgres,
    ],
    schedules=[schedules.ppd_monthly_schedule],
    # resources={"r2": R2Resource(...), "postgres": PostgresResource(...)},
    # ^ wire these in from env/config when you add real credentials.
)
