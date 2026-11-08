"""Single source of truth for the OS Open UPRN schema.

OS Open UPRN ships as a single Great-Britain CSV *with a header*, carrying five
columns: UPRN, X_COORDINATE, Y_COORDINATE, LATITUDE, LONGITUDE. Describing each
column once — its CSV header spelling, its clean cast type, its Postgres DDL
type, and whether it's the primary key — keeps the DuckDB read, the table DDL,
and the diff-merge from ever drifting out of sync. The derived helpers at the
bottom project that one list into the exact strings the SQL steps need, so
adding a column is a one-line change here.

The clean read matches columns to the schema **by header name** (`csv_name`),
not by position, so a future OS release that reorders the columns still loads
correctly — and a renamed or dropped column fails loudly at the read rather than
silently mislabelling data.

`uprn` is the natural, immutable primary key. The only columns that can actually
change for an existing UPRN between releases are the four coordinates (OS
improves positional accuracy over time); that's what the diff-merge's
`CHANGED_PREDICATE` compares.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDef:
    """One OS Open UPRN column, described once for every consumer of the schema."""

    name: str  # our clean, snake_case column name
    csv_name: str  # the source header spelling in the OS Open UPRN CSV
    csv_type: str  # cast target for the clean read (the CSV is read all_varchar)
    pg_type: str  # Postgres DDL type for the served table
    is_pk: bool = False  # the natural primary key (the UPRN itself)


# The clean column set. The read matches these to the CSV BY HEADER NAME
# (`csv_name`), so column order in the file doesn't matter. OS publishes the
# headers in UPPER_SNAKE_CASE.
OS_OPEN_UPRN_SCHEMA: list[ColumnDef] = [
    # OS "UPRN" — the Unique Property Reference Number; the natural PK. Up to 12
    # digits, so it fits comfortably in a bigint.
    ColumnDef("uprn", "UPRN", "BIGINT", "bigint PRIMARY KEY", is_pk=True),
    # Eastings/northings on the British National Grid (EPSG:27700), in metres.
    ColumnDef("x_coordinate", "X_COORDINATE", "DOUBLE", "double precision"),
    ColumnDef("y_coordinate", "Y_COORDINATE", "DOUBLE", "double precision"),
    # WGS84 (EPSG:4326) latitude/longitude, in degrees.
    ColumnDef("latitude", "LATITUDE", "DOUBLE", "double precision"),
    ColumnDef("longitude", "LONGITUDE", "DOUBLE", "double precision"),
]


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# OS_OPEN_UPRN_SCHEMA so they can never disagree with it.                      #
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
PG_DDL_COLS: str = ",\n    ".join(
    f"{c.name} {c.pg_type}" for c in OS_OPEN_UPRN_SCHEMA
)

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
