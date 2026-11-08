"""The one connection the quality assets need: Postgres.

Like reconciliation, this service defines no resource of its own — it only reads
served tables already in Postgres and writes small companion tables back. The
``PostgresResource`` class is imported straight from land_registry and
re-exported, so the root ``definitions.py`` hands this service the very same
``postgres`` instance it binds for the others. There is no R2 / object-storage
or DuckDB round-trip here, so no R2 resource is needed.
"""

from __future__ import annotations

from services.jobs.ingestion.land_registry.resources import PostgresResource

__all__ = ["PostgresResource"]
