"""Single source of truth for the EPC domestic certificate schema.

EPC's bulk CSV *does* carry a header (unlike PPD's positional file), and it has
~90 columns. Rather than drag all of them into the serving table, we project the
useful subset described once in `EPC_SCHEMA` below. Describing each column once —
its source CSV header, its clean cast type, its Postgres DDL type, whether it's
the primary key, and whether empty strings clean to NULL — keeps the DuckDB read,
the table DDL, and the upsert from ever drifting out of sync. The derived helpers
at the bottom project that one list into the exact strings the SQL steps need, so
adding or reordering a column is a one-line change here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnDef:
    """One EPC column, described once for every consumer of the schema."""

    name: str  # our clean, snake_case column name
    csv_name: str  # the source header in the EPC certificates.csv
    csv_type: str  # cast target for the clean SELECT ("VARCHAR" = leave as text)
    pg_type: str  # Postgres DDL type for the served table
    is_pk: bool = False  # the natural primary key (EPC certificate hash)
    nullif_empty: bool = False  # clean empty strings to NULL during cleaning


# The clean column set, projected from the EPC domestic certificates CSV. The
# CSV is read `all_varchar`, so `csv_type` is the type each value is CAST to in
# the cleaning SELECT ("VARCHAR" means keep it as text). `nullif_empty` marks the
# text columns whose empty strings should become NULL.
#
# NOTE: the MHCLG "Get energy performance of buildings data" full-load CSV uses
# lowercase_snake_case headers (the retired Open Data Communities export used
# UPPER_SNAKE), and the per-certificate identity column is `certificate_number`
# (the report reference number) — there is no `LMK_KEY`. A couple of legacy
# columns are gone (`building_reference_number`, `county`); the new file carries
# `posttown` / `region` / `country` / `uprn_source` instead.
EPC_SCHEMA: list[ColumnDef] = [
    # "certificate_number" — the unique certificate reference number; natural PK.
    ColumnDef(
        "certificate_number",
        "certificate_number",
        "VARCHAR",
        "text PRIMARY KEY",
        is_pk=True,
    ),
    ColumnDef("uprn", "uprn", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("uprn_source", "uprn_source", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("address1", "address1", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("address2", "address2", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("address3", "address3", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("posttown", "posttown", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("postcode", "postcode", "VARCHAR", "text", nullif_empty=True),
    ColumnDef(
        "local_authority", "local_authority", "VARCHAR", "text", nullif_empty=True
    ),
    ColumnDef(
        "local_authority_label",
        "local_authority_label",
        "VARCHAR",
        "text",
        nullif_empty=True,
    ),
    ColumnDef("constituency", "constituency", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("region", "region", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("country", "country", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("property_type", "property_type", "VARCHAR", "text", nullif_empty=True),
    ColumnDef("built_form", "built_form", "VARCHAR", "text", nullif_empty=True),
    ColumnDef(
        "construction_age_band",
        "construction_age_band",
        "VARCHAR",
        "text",
        nullif_empty=True,
    ),
    ColumnDef("tenure", "tenure", "VARCHAR", "text", nullif_empty=True),
    ColumnDef(
        "transaction_type", "transaction_type", "VARCHAR", "text", nullif_empty=True
    ),
    ColumnDef("total_floor_area", "total_floor_area", "DOUBLE", "double precision"),
    ColumnDef(
        "current_energy_rating", "current_energy_rating", "VARCHAR", "text",
        nullif_empty=True,
    ),
    ColumnDef(
        "potential_energy_rating", "potential_energy_rating", "VARCHAR", "text",
        nullif_empty=True,
    ),
    ColumnDef(
        "current_energy_efficiency", "current_energy_efficiency", "INTEGER", "integer"
    ),
    ColumnDef(
        "potential_energy_efficiency",
        "potential_energy_efficiency",
        "INTEGER",
        "integer",
    ),
    ColumnDef(
        "co2_emissions_current", "co2_emissions_current", "DOUBLE", "double precision"
    ),
    ColumnDef(
        "co2_emissions_potential",
        "co2_emissions_potential",
        "DOUBLE",
        "double precision",
    ),
    ColumnDef("inspection_date", "inspection_date", "DATE", "date"),
    ColumnDef("lodgement_date", "lodgement_date", "DATE", "date"),
]


# --------------------------------------------------------------------------- #
# Derived projections — the exact strings the SQL steps consume. Built from    #
# EPC_SCHEMA so they can never disagree with it.                               #
# --------------------------------------------------------------------------- #

# Column names, in order: `certificate_number, uprn, ...`.
COLUMNS: list[str] = [c.name for c in EPC_SCHEMA]

# The natural primary key column name, used by the upsert's ON CONFLICT target.
PK_COLUMN: str = next(c.name for c in EPC_SCHEMA if c.is_pk)

# Postgres CREATE TABLE column list: `lmk_key text PRIMARY KEY,\n    ...`.
PG_DDL_COLS: str = ",\n    ".join(f"{c.name} {c.pg_type}" for c in EPC_SCHEMA)

# ON CONFLICT ... DO UPDATE SET body — every column except the PK.
UPDATE_SET: str = ", ".join(
    f"{c.name} = EXCLUDED.{c.name}" for c in EPC_SCHEMA if not c.is_pk
)
