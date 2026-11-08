"""Pipeline projections of the Land Registry PPD schema.

The schema itself — columns, Postgres types, primary key, and the DuckDB read /
cleaning metadata — lives on the SQLAlchemy model ``LandRegistrySales`` in
``shared/db/models`` (the single source of truth that Alembic also migrates).
This module reads that model back as ``PPD_SCHEMA`` and projects it into the
exact strings the SQL steps consume, so the DuckDB read, the table DDL, and the
upsert can never drift from the model — adding or reordering a column is a
one-line change on the model.
"""

from __future__ import annotations

from shared.db.columns import ColumnSpec, column_specs
from shared.db.models.land_registry_sales import LandRegistrySales

# The clean column set, in raw-CSV order, as the pipeline sees it. Each entry
# carries name / csv_type / pg_type / is_pk / nullif_empty (see ColumnSpec).
PPD_SCHEMA: list[ColumnSpec] = column_specs(LandRegistrySales)


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# PPD_SCHEMA so they can never disagree with the model.                        #
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
