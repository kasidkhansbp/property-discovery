"""data_quality's own self-contained Dagster Definitions.

This service profiles the *coverage* of the other services' served tables. For
each of ``land_registry_sales``, ``epc_domestic_certificates``, ``os_open_uprn``
and ``property_uprn_mapping`` it builds a small ``<table>_quality`` companion
holding one row per column (populated / NULL / blank counts and a coverage
percentage), refreshed monthly by its own job.

It also builds one cross-table companion, ``key_duplication_quality`` (one row
per check), reporting key-duplication / fan-out: transaction_ids per uprn in
``property_uprn_mapping``, repeated ``transaction_id`` values in
``land_registry_sales``, and repeated ``uprn`` values in
``epc_domestic_certificates``.

Like reconciliation, it ingests nothing from the outside world — it only reads
tables already in Postgres and writes the companions back — so it reuses the
shared ``postgres`` resource and needs no R2 credentials. The root
``definitions.py`` folds this in alongside the other services.

Credentials come from the environment (never the repo): set POSTGRES_DSN.
"""

from __future__ import annotations

import dagster as dg

from . import assets, schedules
from .resources import PostgresResource

defs = dg.Definitions(
    assets=[
        assets.land_registry_sales_quality,
        assets.epc_domestic_certificates_quality,
        assets.os_open_uprn_quality,
        assets.property_uprn_mapping_quality,
        assets.key_duplication_quality,
    ],
    jobs=[
        schedules.land_registry_sales_quality_job,
        schedules.epc_domestic_certificates_quality_job,
        schedules.os_open_uprn_quality_job,
        schedules.property_uprn_mapping_quality_job,
        schedules.key_duplication_quality_job,
    ],
    schedules=[
        schedules.land_registry_sales_quality_schedule,
        schedules.epc_domestic_certificates_quality_schedule,
        schedules.os_open_uprn_quality_schedule,
        schedules.property_uprn_mapping_quality_schedule,
        schedules.key_duplication_quality_schedule,
    ],
    resources={
        "postgres": PostgresResource(dsn=dg.EnvVar("POSTGRES_DSN")),
    },
)
