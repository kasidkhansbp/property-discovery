"""Connections the land_registry assets need: R2 (object storage) and Postgres.

Kept as Dagster resources so assets don't hard-code credentials and so they can
be swapped for fakes in tests. Fill in real clients when you wire things up.
"""

from __future__ import annotations

import dagster as dg


class R2Resource(dg.ConfigurableResource):
    """Cloudflare R2 (S3-compatible) — the raw + clean object store."""

    bucket: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str

    # TODO: add get_client() returning a boto3 S3 client pointed at R2,
    # plus put_object / get_object helpers for the assets to use.


class PostgresResource(dg.ConfigurableResource):
    """Postgres + PostGIS — the serving database."""

    dsn: str  # e.g. postgresql://user:pass@host:5432/dbname

    # TODO: add a connection/engine helper (psycopg or SQLAlchemy) for loading.
