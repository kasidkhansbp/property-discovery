"""Tables for the data-quality companions.

Four per-source ``<table>_quality`` tables (one row per source column, keyed by
``column_name``) share one shape; ``key_duplication_quality`` is a single flat
table (one row per check, keyed by ``source_table`` + ``key_column``). All are
Core ``Table``s attached to the shared metadata so Alembic manages them.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Integer, Numeric, Table, Text

from ..base import Base

# The four served tables that get a ``<table>_quality`` companion, in order.
QUALITY_SOURCE_TABLES: tuple[str, ...] = (
    "land_registry_sales",
    "epc_domestic_certificates",
    "os_open_uprn",
    "property_uprn_mapping",
)


def _quality_columns() -> list[Column]:
    """Fresh Column objects for one quality table (can't share across tables)."""
    return [
        Column("column_name", Text, primary_key=True, info={"pg_type": "text"}),
        Column("data_type", Text, info={"pg_type": "text"}),
        Column("column_position", Integer, info={"pg_type": "integer"}),
        Column("total_rows", BigInteger, info={"pg_type": "bigint"}),
        Column("populated_count", BigInteger, info={"pg_type": "bigint"}),
        Column("null_count", BigInteger, info={"pg_type": "bigint"}),
        Column("empty_string_count", BigInteger, info={"pg_type": "bigint"}),
        Column("coverage_pct", Numeric, info={"pg_type": "numeric"}),
        Column("checked_at", DateTime(timezone=True), info={"pg_type": "timestamptz"}),
    ]


# {source_table: its <source>_quality Table}
quality_tables: dict[str, Table] = {
    src: Table(f"{src}_quality", Base.metadata, *_quality_columns())
    for src in QUALITY_SOURCE_TABLES
}

key_duplication_quality = Table(
    "key_duplication_quality",
    Base.metadata,
    Column("source_table", Text, primary_key=True, info={"pg_type": "text"}),
    Column("key_column", Text, primary_key=True, info={"pg_type": "text"}),
    Column("total_rows", BigInteger, info={"pg_type": "bigint"}),
    Column("non_null_keys", BigInteger, info={"pg_type": "bigint"}),
    Column("distinct_keys", BigInteger, info={"pg_type": "bigint"}),
    Column("keys_with_duplicates", BigInteger, info={"pg_type": "bigint"}),
    Column("duplicate_rows", BigInteger, info={"pg_type": "bigint"}),
    Column("max_rows_per_key", BigInteger, info={"pg_type": "bigint"}),
    Column("avg_rows_per_key", Numeric, info={"pg_type": "numeric"}),
    Column("checked_at", DateTime(timezone=True), info={"pg_type": "timestamptz"}),
)
