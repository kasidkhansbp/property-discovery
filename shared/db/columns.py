"""Bridge between the SQLAlchemy models and the pipeline's SQL-building code.

The ingestion pipeline describes each column three ways at once — its DuckDB read
type (``csv_type``), its Postgres DDL type (``pg_type``), and its cleaning rule
(``nullif_empty``) — and projects those into the exact SQL strings its load steps
use. SQLAlchemy models can't express the DuckDB/cleaning facts natively, so each
model column stashes them in its ``info`` dict, and ``column_specs()`` reads them
back out in table order. A service's ``schema.py`` can then build its familiar
``*_SCHEMA`` list from the model, keeping the model the single source of truth
while every downstream derivation (and its tests) stays byte-for-byte unchanged.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import BigInteger, Date, DateTime, Double, Integer, Numeric, Text
from sqlalchemy.orm import mapped_column

# Postgres DDL base type -> SQLAlchemy type, so the ORM column Alembic sees
# matches the exact DDL string the pipeline emits.
_TYPE_MAP = {
    "text": Text,
    "bigint": BigInteger,
    "integer": Integer,
    "double precision": Double,
    "numeric": Numeric,
    "date": Date,
}


class ColumnSpec(NamedTuple):
    """One column as the pipeline sees it — the shape of the old ``ColumnDef``."""

    name: str
    pg_type: str  # exact Postgres DDL type string, e.g. "text PRIMARY KEY"
    csv_type: str | None  # DuckDB read/cast type ("VARCHAR", "BIGINT", ...)
    csv_name: str | None  # source CSV header (falls back to the column name)
    nullif_empty: bool  # clean empty strings to NULL
    is_pk: bool


def pg_column(
    pg_type: str,
    *,
    csv_type: str | None = None,
    csv_name: str | None = None,
    nullif_empty: bool = False,
    **kw,
):
    """A ``mapped_column`` whose SQLAlchemy type matches the DDL string ``pg_type``.

    The pipeline's read/clean metadata is stashed in ``info`` so ``column_specs``
    can recover it. ``pg_type`` may carry a trailing ``PRIMARY KEY``.
    """
    base = pg_type
    is_pk = False
    if base.endswith(" PRIMARY KEY"):
        is_pk = True
        base = base[: -len(" PRIMARY KEY")].strip()

    sa_type = DateTime(timezone=True) if base == "timestamptz" else _TYPE_MAP[base]()

    info = {"pg_type": pg_type, "nullif_empty": nullif_empty}
    if csv_type is not None:
        info["csv_type"] = csv_type
    if csv_name is not None:
        info["csv_name"] = csv_name

    return mapped_column(sa_type, primary_key=is_pk, info=info, **kw)


def column_specs(model_or_table) -> list[ColumnSpec]:
    """Columns of an ORM model or Core ``Table`` as ``ColumnSpec``s, in order."""
    table = getattr(model_or_table, "__table__", model_or_table)
    specs: list[ColumnSpec] = []
    for col in table.columns:
        info = col.info or {}
        specs.append(
            ColumnSpec(
                name=col.name,
                pg_type=info.get("pg_type", str(col.type)),
                csv_type=info.get("csv_type"),
                csv_name=info.get("csv_name", col.name),
                nullif_empty=bool(info.get("nullif_empty", False)),
                is_pk=bool(col.primary_key),
            )
        )
    return specs
