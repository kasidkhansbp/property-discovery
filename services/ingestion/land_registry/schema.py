"""Single source of truth for the Land Registry Price Paid Data (PPD) schema.

PPD's raw CSV has no header; its 16 positional columns map 1:1, in order, to the
`PPD_SCHEMA` list below. Describing each column once — its DuckDB read type, its
Postgres DDL type, whether it's the primary key, and how it's cleaned — keeps the
DuckDB read, the table DDL, and the upsert from ever drifting out of sync. The
derived helpers at the bottom project that one list into the exact strings the
SQL steps need, so adding or reordering a column is a one-line change here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDef:
    """One PPD column, described once for every consumer of the schema."""

    name: str
    csv_type: str  # DuckDB type for the raw CSV read (typed where parseable)
    pg_type: str  # Postgres DDL type for the served table
    is_pk: bool = False  # the natural primary key (PPD transaction id)
    nullif_empty: bool = False  # clean empty strings to NULL during cleaning


# The clean column set, in raw-CSV order. Typed in DuckDB where it can parse
# directly, VARCHAR where the value needs cleaning first. `nullif_empty` marks
# the text columns whose empty strings should become NULL.
PPD_SCHEMA: list[ColumnDef] = [
    # PPD "Transaction unique identifier" — the natural PK.
    ColumnDef("transaction_id", "VARCHAR", "text PRIMARY KEY", is_pk=True),
    ColumnDef("price", "BIGINT", "bigint"),
    ColumnDef("transfer_date", "TIMESTAMP", "date"),
    ColumnDef("postcode", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("property_type", "VARCHAR", "text"),
    ColumnDef("old_new", "VARCHAR", "text"),
    ColumnDef("duration", "VARCHAR", "text"),
    ColumnDef("paon", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("saon", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("street", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("locality", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("town_city", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("district", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("county", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("ppd_category", "VARCHAR", "text"),
    # A=add, C=change, D=delete (monthly); always A in complete.
    ColumnDef("record_status", "VARCHAR", "text"),
]


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# PPD_SCHEMA so they can never disagree with it.                               #
# --------------------------------------------------------------------------- #

# Column names, in order: `transaction_id, price, ...`.
COLUMNS: list[str] = [c.name for c in PPD_SCHEMA]

# DuckDB CSV `columns = {...}` spec body: `'transaction_id': 'VARCHAR', ...`.
CSV_COLUMNS_SPEC: str = ", ".join(f"'{c.name}': '{c.csv_type}'" for c in PPD_SCHEMA)

# Postgres CREATE TABLE column list: `transaction_id text PRIMARY KEY,\n    ...`.
PG_DDL_COLS: str = ",\n    ".join(f"{c.name} {c.pg_type}" for c in PPD_SCHEMA)

# ON CONFLICT ... DO UPDATE SET body — every column except the PK.
UPDATE_SET: str = ", ".join(
    f"{c.name} = EXCLUDED.{c.name}" for c in PPD_SCHEMA if not c.is_pk
)
