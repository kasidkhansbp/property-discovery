"""os_open_uprn's own self-contained Dagster Definitions.

This service ingests Ordnance Survey's **OS Open UPRN** product — the master
reference table mapping every UPRN to its authoritative spatial coordinates
(x/y in British National Grid, plus latitude/longitude) described in
data-platform-structure.md.

OS publishes OS Open UPRN as a free *bulk OpenData* product on the OS Data Hub
**Downloads API** (no key required): every ~6-week release is the whole of Great
Britain in one zipped CSV, with no delta feed. This pipeline fetches that release
from the API, extracts it, and diff-merges it into Postgres (see assets.py /
README.md).

As with the other services, this bundles everything THIS service owns — its
assets, its (manually-triggered) job, and its resources — into one object. The
root ``definitions.py`` folds it in alongside the others. The R2 / Postgres
connections are the same ones the other services use; OS Open UPRN needs no extra
credential because the OpenData download is unauthenticated.

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
        assets.os_open_uprn_raw_zip,
        assets.os_open_uprn_clean_parquet,
        assets.os_open_uprn_loaded_to_postgres,
    ],
    # One manually-triggered job: download -> clean -> load the current release.
    # No schedule — launch it when a new OS release is out (the download step
    # skips cheaply via the API md5 if nothing has changed).
    jobs=[schedules.os_open_uprn_load_job],
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
