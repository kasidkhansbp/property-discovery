"""Tests for the PPD schema and its derived SQL projections.

`schema.py` is the single source of truth: one `PPD_SCHEMA` list drives the
DuckDB read, the Postgres DDL, and the upsert. These tests pin the derived
strings to that list so the three SQL steps can never silently drift apart.
Pure data — no network, DuckDB, or Postgres needed.
"""

from __future__ import annotations

from services.ingestion.land_registry.schema import (
    COLUMNS,
    CSV_COLUMNS_SPEC,
    PG_DDL_COLS,
    PPD_SCHEMA,
    UPDATE_SET,
)


def test_schema_has_the_sixteen_positional_ppd_columns():
    # PPD's raw CSV is 16 positional columns, in this fixed order.
    assert len(PPD_SCHEMA) == 16
    assert COLUMNS[0] == "transaction_id"
    assert COLUMNS[-1] == "record_status"


def test_exactly_one_primary_key_and_it_is_transaction_id():
    pks = [c for c in PPD_SCHEMA if c.is_pk]
    assert [c.name for c in pks] == ["transaction_id"]


def test_columns_matches_schema_order():
    assert COLUMNS == [c.name for c in PPD_SCHEMA]


def test_csv_columns_spec_lists_every_column_with_its_duckdb_type():
    # One `'name': 'TYPE'` entry per column, in order.
    entries = [part.strip() for part in CSV_COLUMNS_SPEC.split(",")]
    assert len(entries) == len(PPD_SCHEMA)
    for entry, col in zip(entries, PPD_SCHEMA):
        assert entry == f"'{col.name}': '{col.csv_type}'"


def test_pg_ddl_lists_every_column_with_its_postgres_type():
    lines = [line.strip() for line in PG_DDL_COLS.split(",\n")]
    assert len(lines) == len(PPD_SCHEMA)
    for line, col in zip(lines, PPD_SCHEMA):
        assert line == f"{col.name} {col.pg_type}"
    # The PK declaration rides along on the transaction_id column.
    assert "transaction_id text PRIMARY KEY" in PG_DDL_COLS


def test_update_set_covers_every_column_except_the_primary_key():
    assignments = [part.strip() for part in UPDATE_SET.split(",")]
    non_pk = [c.name for c in PPD_SCHEMA if not c.is_pk]
    assert len(assignments) == len(non_pk)
    for name in non_pk:
        assert f"{name} = EXCLUDED.{name}" in assignments
    # The PK must never appear in the SET clause.
    assert "transaction_id = EXCLUDED.transaction_id" not in UPDATE_SET


def test_record_status_is_present_so_the_delete_flag_survives_cleaning():
    # The load step keys deletes off record_status; it must stay in the schema.
    assert "record_status" in COLUMNS
