"""Pipeline projections of the OS Open UPRN schema.

The schema itself — the five columns, their Postgres types, the primary key, and
the DuckDB read metadata (source header spelling, cast type) — lives on the
SQLAlchemy model ``OsOpenUprn`` in ``shared/db/models`` (the single source of
truth that Alembic migrates). This module reads that model back as
``OS_OPEN_UPRN_SCHEMA`` and projects it into the exact strings the SQL steps need,
so the DuckDB read, the table DDL, and the diff-merge can never drift from it.

The clean read matches columns to the schema **by header name** (``csv_name``),
not by position, so a future OS release that reorders columns still loads — and a
renamed/dropped column fails loudly at the read rather than mislabelling data.
"""

from __future__ import annotations

from shared.db.columns import ColumnSpec, column_specs
from shared.db.models.os_open_uprn import OsOpenUprn

# The clean column set. Each entry carries name / csv_name / csv_type / pg_type /
# is_pk (see ColumnSpec). The read matches these to the CSV by header name.
OS_OPEN_UPRN_SCHEMA: list[ColumnSpec] = column_specs(OsOpenUprn)


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# OS_OPEN_UPRN_SCHEMA so they can never disagree with the model.              #
# --------------------------------------------------------------------------- #

# Column names, in order: `uprn, x_coordinate, ...`.
COLUMNS: list[str] = [c.name for c in OS_OPEN_UPRN_SCHEMA]

# The natural primary key column name, keyed on by the diff-merge.
PK_COLUMN: str = next(c.name for c in OS_OPEN_UPRN_SCHEMA if c.is_pk)

# The mutable columns — everything except the PK. The diff-merge only ever
# UPDATEs a row when one of these actually changed.
NON_PK_COLUMNS: list[str] = [c.name for c in OS_OPEN_UPRN_SCHEMA if not c.is_pk]

# Clean read SELECT list — projects each CSV column (referenced by its header
# name, so order doesn't matter) to our clean name with an explicit cast:
# `CAST("UPRN" AS BIGINT) AS uprn, ...`. The CSV is read all_varchar, so a
# missing/renamed header raises here rather than silently mislabelling columns.
CLEAN_SELECT: str = ", ".join(
    f'CAST("{c.csv_name}" AS {c.csv_type}) AS {c.name}' for c in OS_OPEN_UPRN_SCHEMA
)

# Postgres CREATE TABLE column list: `uprn bigint PRIMARY KEY,\n    ...`.
PG_DDL_COLS: str = ",\n    ".join(f"{c.name} {c.pg_type}" for c in OS_OPEN_UPRN_SCHEMA)

# Diff-merge UPDATE ... SET body, pulling new values from the staging alias `s`:
# `x_coordinate = s.x_coordinate, ...` (every non-PK column).
UPDATE_SET_FROM_STAGING: str = ", ".join(f"{c} = s.{c}" for c in NON_PK_COLUMNS)

# Diff-merge "did anything actually change?" predicate, comparing the target
# row `t` against the staging row `s` across every mutable column at once.
# `IS DISTINCT FROM` treats NULLs as comparable, so a NULL<->value flip counts
# as a change while NULL<->NULL does not.
CHANGED_PREDICATE: str = (
    "("
    + ", ".join(f"t.{c}" for c in NON_PK_COLUMNS)
    + ") IS DISTINCT FROM ("
    + ", ".join(f"s.{c}" for c in NON_PK_COLUMNS)
    + ")"
)
