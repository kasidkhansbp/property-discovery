"""Tests for the EPC schema and its derived SQL projections.

`schema.py` is the single source of truth: one `EPC_SCHEMA` list drives the
DuckDB clean SELECT, the Postgres DDL, and the upsert. These tests pin the
derived strings to that list so the three SQL steps can never silently drift
apart. Pure data — no network, DuckDB, or Postgres needed.
"""

from __future__ import annotations

from services.ingestion.epc.schema import (
    COLUMNS,
    EPC_SCHEMA,
    PG_DDL_COLS,
    PK_COLUMN,
    UPDATE_SET,
)


def test_schema_leads_with_certificate_number_and_is_non_empty():
    assert len(EPC_SCHEMA) > 0
    assert COLUMNS[0] == "certificate_number"


def test_exactly_one_primary_key_and_it_is_certificate_number():
    pks = [c for c in EPC_SCHEMA if c.is_pk]
    assert [c.name for c in pks] == ["certificate_number"]


def test_columns_matches_schema_order():
    assert COLUMNS == [c.name for c in EPC_SCHEMA]


def test_pk_column_is_the_single_primary_key():
    # PK_COLUMN drives the upsert's ON CONFLICT target, so it must track the PK.
    assert PK_COLUMN == "certificate_number"
    assert [c.name for c in EPC_SCHEMA if c.is_pk] == [PK_COLUMN]


def test_every_column_maps_to_a_source_header():
    # Each clean column is projected from a named EPC CSV header. The MHCLG
    # full-load CSV uses lowercase_snake_case headers.
    for col in EPC_SCHEMA:
        assert col.csv_name
        assert col.csv_name == col.csv_name.lower()  # EPC headers are lowercase_snake


def test_clean_column_names_are_unique():
    assert len(COLUMNS) == len(set(COLUMNS))


def test_pg_ddl_lists_every_column_with_its_postgres_type():
    lines = [line.strip() for line in PG_DDL_COLS.split(",\n")]
    assert len(lines) == len(EPC_SCHEMA)
    for line, col in zip(lines, EPC_SCHEMA):
        assert line == f"{col.name} {col.pg_type}"
    # The PK declaration rides along on the certificate_number column.
    assert "certificate_number text PRIMARY KEY" in PG_DDL_COLS


def test_update_set_covers_every_column_except_the_primary_key():
    assignments = [part.strip() for part in UPDATE_SET.split(",")]
    non_pk = [c.name for c in EPC_SCHEMA if not c.is_pk]
    assert len(assignments) == len(non_pk)
    for name in non_pk:
        assert f"{name} = EXCLUDED.{name}" in assignments
    # The PK must never appear in the SET clause.
    assert "certificate_number = EXCLUDED.certificate_number" not in UPDATE_SET
