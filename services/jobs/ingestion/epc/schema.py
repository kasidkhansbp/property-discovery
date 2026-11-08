"""Pipeline projections of the EPC domestic-certificate schema.

The schema itself — the projected columns, their Postgres types, the primary key,
and the DuckDB read / cleaning metadata (source header, cast type, NULL rule) —
lives on the SQLAlchemy model ``EpcDomesticCertificates`` in ``shared/db/models``
(the single source of truth that Alembic migrates). This module reads that model
back as ``EPC_SCHEMA`` and projects it into the exact strings the SQL steps need,
so the DuckDB read, the table DDL, and the upsert can never drift from the model.
"""

from __future__ import annotations

from shared.db.columns import ColumnSpec, column_specs
from shared.db.models.epc_domestic_certificates import EpcDomesticCertificates

# The clean column set, in table order. Each entry carries name / csv_name /
# csv_type / pg_type / is_pk / nullif_empty (see ColumnSpec).
EPC_SCHEMA: list[ColumnSpec] = column_specs(EpcDomesticCertificates)


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# EPC_SCHEMA so they can never disagree with the model.                        #
# --------------------------------------------------------------------------- #

# Column names, in order: `certificate_number, uprn, ...`.
COLUMNS: list[str] = [c.name for c in EPC_SCHEMA]

# The natural primary key column name, used by the upsert's ON CONFLICT target.
PK_COLUMN: str = next(c.name for c in EPC_SCHEMA if c.is_pk)

# Postgres CREATE TABLE column list: `certificate_number text PRIMARY KEY,\n ...`.
PG_DDL_COLS: str = ",\n    ".join(f"{c.name} {c.pg_type}" for c in EPC_SCHEMA)

# ON CONFLICT ... DO UPDATE SET body — every column except the PK.
UPDATE_SET: str = ", ".join(
    f"{c.name} = EXCLUDED.{c.name}" for c in EPC_SCHEMA if not c.is_pk
)
