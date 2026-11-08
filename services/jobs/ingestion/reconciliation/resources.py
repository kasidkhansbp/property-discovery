"""Connections the reconciliation assets need: R2 (object storage) and Postgres.

Per the brief, this service *reuses* the Cloudflare R2 and DuckDB/Postgres
connections rather than defining its own — so the two classes are imported
straight from land_registry and re-exported here. Keeping a single class
identity for ``R2Resource`` / ``PostgresResource`` also means the root
``definitions.py``, which binds one shared ``r2`` / ``postgres`` instance across
all services, hands this service the very same connection objects.

``R2Resource`` already carries everything reconciliation touches —
``configure_duckdb`` (httpfs), ``s3_url``, and ``object_size``; there are no raw
downloads here, so none of the download/upload streaming helpers are needed.
"""

from __future__ import annotations

from services.jobs.ingestion.land_registry.resources import PostgresResource, R2Resource

__all__ = ["PostgresResource", "R2Resource"]
