"""Single source of truth for the per-table data-quality tables.

Every served table gets one small, materialised ``<table>_quality`` companion
that carries **one row per source column**, recording how populated that column
is. "Quality" here means *coverage*: for each column, how many rows actually
carry a value versus how many are NULL (or, for text columns, blank). The
headline figure is ``coverage_pct`` = populated / total_rows * 100.

The quality tables all share the same shape (``QUALITY_COLUMN_TYPES``); only the
*source* table and its column list differ. Each source's column list is imported
straight from that service's own schema module, so the quality check can never
drift from the real table — add a column to a source schema and its quality
table automatically reports on it.

The per-column metrics are produced by one SQL statement (``quality_metrics_select``)
that scans the source table **once** (a single aggregate CTE) and then unpivots
that one aggregate row into one output row per column. It uses only functions
Postgres and DuckDB share (``count(*) FILTER``, ``trim``, ``nullif``, ``round``,
``now``), so the exact SELECT runs unchanged in tests (DuckDB) and production
(Postgres).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from services.ingestion.epc.schema import EPC_SCHEMA
from services.ingestion.land_registry.schema import PPD_SCHEMA
from services.ingestion.os_open_uprn.schema import OS_OPEN_UPRN_SCHEMA
from services.ingestion.reconciliation.schema import (
    ENRICHMENT_COLUMN_TYPES,
    MASTER_COLUMNS,
)
from services.ingestion.reconciliation.schema import TARGET_TABLE as PUM_TABLE

# --------------------------------------------------------------------------- #
# The served source tables. Their names mirror each service's utils.TARGET_TABLE
# (land_registry/epc/os_open_uprn) and reconciliation's TARGET_TABLE.          #
# --------------------------------------------------------------------------- #
LR_TABLE = "land_registry_sales"
EPC_TABLE = "epc_domestic_certificates"
OS_OPEN_UPRN_TABLE = "os_open_uprn"


# --------------------------------------------------------------------------- #
# The shape shared by every *_quality table: one row per source column.       #
# --------------------------------------------------------------------------- #
# ``column_name`` is the PK — one row per column, rebuilt wholesale each run.
# ``coverage_pct`` is nullable only to cover an empty source table (total_rows
# = 0, where the ratio is undefined); for a non-empty table it is always set.
QUALITY_COLUMN_TYPES: dict[str, str] = {
    "column_name": "text",  # the source column this row describes
    "data_type": "text",  # its Postgres type, for context on the dashboard
    "column_position": "integer",  # source column order, for a stable sort
    "total_rows": "bigint",  # rows in the source table (same for every row)
    "populated_count": "bigint",  # rows with a real value (not NULL / not blank)
    "null_count": "bigint",  # rows where the column IS NULL
    "empty_string_count": "bigint",  # text only: non-NULL but blank/whitespace
    "coverage_pct": "numeric",  # populated / total_rows * 100, rounded 2 dp
    "checked_at": "timestamptz",  # when this snapshot was taken
}
QUALITY_COLUMNS: list[str] = list(QUALITY_COLUMN_TYPES)

# Postgres CREATE TABLE body. column_name is the natural PK (one row per column).
QUALITY_PG_DDL_COLS: str = (
    ",\n    ".join(f"{name:<18} {ddl}" for name, ddl in QUALITY_COLUMN_TYPES.items())
    + ",\n    PRIMARY KEY (column_name)"
)


# --------------------------------------------------------------------------- #
# A source table to run the quality check over.                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class QualitySource:
    """One served table to profile, plus the columns to profile in it."""

    source_table: str
    # (name, Postgres DDL type) per column, in table order. The DDL type may
    # carry a constraint tail (e.g. "text PRIMARY KEY"); _base_type strips it.
    columns: tuple[tuple[str, str], ...]
    # The load assets this quality check sits downstream of — lineage only; the
    # check always re-reads the whole current table when it runs.
    load_asset_keys: tuple[str, ...]

    @property
    def quality_table(self) -> str:
        """The companion table name, e.g. ``land_registry_sales_quality``."""
        return f"{self.source_table}_quality"


def _base_type(pg_type: str) -> str:
    """The bare type, with any constraint tail dropped: 'text PRIMARY KEY' -> 'text'."""
    return pg_type.split(" PRIMARY")[0].strip()


def _is_text(pg_type: str) -> bool:
    """Whether a column is textual — only text columns get the blank-string check."""
    base = _base_type(pg_type).lower()
    return base.startswith("text") or "char" in base


# The four served tables, each with its authoritative column list pulled from
# the owning service's schema (so this can never drift from the real table).
_PUM_COLUMN_TYPES: dict[str, str] = {
    "transaction_id": "text",
    "uprn": "text",
    "match_score": "double precision",
    "match_type": "text",
    **ENRICHMENT_COLUMN_TYPES,
}
assert list(_PUM_COLUMN_TYPES) == MASTER_COLUMNS  # stays in lock-step with the bridge

QUALITY_SOURCES: dict[str, QualitySource] = {
    LR_TABLE: QualitySource(
        source_table=LR_TABLE,
        columns=tuple((c.name, c.pg_type) for c in PPD_SCHEMA),
        load_asset_keys=(
            "ppd_complete_loaded_to_postgres",
            "ppd_monthly_loaded_to_postgres",
        ),
    ),
    EPC_TABLE: QualitySource(
        source_table=EPC_TABLE,
        columns=tuple((c.name, c.pg_type) for c in EPC_SCHEMA),
        load_asset_keys=(
            "epc_complete_loaded_to_postgres",
            "epc_monthly_loaded_to_postgres",
        ),
    ),
    OS_OPEN_UPRN_TABLE: QualitySource(
        source_table=OS_OPEN_UPRN_TABLE,
        columns=tuple((c.name, c.pg_type) for c in OS_OPEN_UPRN_SCHEMA),
        load_asset_keys=("os_open_uprn_loaded_to_postgres",),
    ),
    PUM_TABLE: QualitySource(
        source_table=PUM_TABLE,
        columns=tuple(_PUM_COLUMN_TYPES.items()),
        load_asset_keys=(
            "reconciliation_full_loaded_to_postgres",
            "reconciliation_incremental_loaded_to_postgres",
        ),
    ),
}


def _populated_predicate(col: str, is_text: bool) -> str:
    """SQL for 'this column carries a real value' — NULL, and blank for text."""
    if is_text:
        return f"{col} IS NOT NULL AND trim({col}) <> ''"
    return f"{col} IS NOT NULL"


def quality_metrics_select(
    source_table: str, columns: Sequence[tuple[str, str]]
) -> str:
    """The SELECT that profiles ``source_table`` into one row per column.

    A single aggregate CTE scans the table once, computing per column the
    populated / NULL / blank counts in one pass (``count(*) FILTER (...)``).
    The table is then read no further: each column's output row is projected
    from that one aggregate row via ``UNION ALL ... FROM agg``, so the whole
    statement costs a single scan of the source regardless of column count.
    Postgres materialises a CTE referenced more than once, so the one scan is
    guaranteed there; in the tiny DuckDB test tables it is immaterial.
    """
    agg_lines = ["count(*) AS total_rows"]
    for i, (name, pg_type) in enumerate(columns):
        is_text = _is_text(pg_type)
        agg_lines.append(
            f"count(*) FILTER (WHERE {_populated_predicate(name, is_text)}) AS pop_{i}"
        )
        agg_lines.append(f"count(*) FILTER (WHERE {name} IS NULL) AS null_{i}")
        if is_text:
            agg_lines.append(
                f"count(*) FILTER (WHERE {name} IS NOT NULL AND trim({name}) = '') "
                f"AS empty_{i}"
            )
        else:
            # Non-text columns have no blank-string state; pin the count to 0 so
            # every quality row still carries the column, typed as bigint.
            agg_lines.append(f"CAST(0 AS bigint) AS empty_{i}")
    agg = ",\n           ".join(agg_lines)

    branches = []
    for i, (name, pg_type) in enumerate(columns):
        branches.append(
            f"SELECT '{name}' AS column_name, "
            f"'{_base_type(pg_type)}' AS data_type, "
            f"{i + 1} AS column_position, "
            f"total_rows, "
            f"pop_{i} AS populated_count, "
            f"null_{i} AS null_count, "
            f"empty_{i} AS empty_string_count, "
            f"round(pop_{i} * 100.0 / nullif(total_rows, 0), 2) AS coverage_pct, "
            f"now() AS checked_at "
            f"FROM agg"
        )
    body = "\n    UNION ALL\n    ".join(branches)

    return (
        f"WITH agg AS (\n    SELECT {agg}\n    FROM {source_table}\n)\n"
        f"{body}\n"
        f"ORDER BY column_position"
    )


# =========================================================================== #
# Cross-table key-duplication checks.                                         #
#                                                                             #
# A second, single companion table — ``key_duplication_quality`` — answers a  #
# different question from the per-column coverage tables above: for a chosen  #
# *key column*, how many rows share a key value (how duplicated, or how       #
# multiply-mapped, that key is). Unlike the coverage tables (one per source), #
# this is ONE table with one row per check, so the three headline duplication #
# figures sit side by side:                                                   #
#                                                                             #
#   * property_uprn_mapping / uprn — how many transaction_ids map to a uprn   #
#     (a property's sales fan-out: avg and max transactions per property);    #
#   * land_registry_sales / transaction_id — repeated transaction_ids (the PK #
#     is unique, so keys_with_duplicates is ideally 0);                       #
#   * epc_domestic_certificates / uprn — repeated uprns (a property carrying  #
#     more than one EPC certificate).                                         #
#                                                                             #
# ``duplication_metrics_select`` groups the source by its key once and        #
# aggregates the group sizes, using only functions Postgres and DuckDB share, #
# so it runs unchanged in tests (DuckDB) and production (Postgres).           #
# =========================================================================== #
DUPLICATION_TABLE = "key_duplication_quality"

# One row per check. NULL keys are excluded from the grouping (they have no key
# to be "duplicated") but still counted in ``total_rows`` — e.g. an UNMATCHED_LR
# row in property_uprn_mapping has a NULL uprn.
DUPLICATION_COLUMN_TYPES: dict[str, str] = {
    "source_table": "text",  # the table this check profiles
    "key_column": "text",  # the column whose values are counted per group
    "total_rows": "bigint",  # rows in the source table (NULL keys included)
    "non_null_keys": "bigint",  # rows carrying a non-NULL key
    "distinct_keys": "bigint",  # distinct non-NULL key values
    "keys_with_duplicates": "bigint",  # distinct keys appearing more than once
    "duplicate_rows": "bigint",  # rows sharing a key with >=1 other row
    "max_rows_per_key": "bigint",  # largest group size for any one key
    "avg_rows_per_key": "numeric",  # non_null_keys / distinct_keys, 2 dp
    "checked_at": "timestamptz",  # when this snapshot was taken
}
DUPLICATION_COLUMNS: list[str] = list(DUPLICATION_COLUMN_TYPES)

# (source_table, key_column) is the natural PK — one row per check.
DUPLICATION_PG_DDL_COLS: str = (
    ",\n    ".join(
        f"{name:<20} {ddl}" for name, ddl in DUPLICATION_COLUMN_TYPES.items()
    )
    + ",\n    PRIMARY KEY (source_table, key_column)"
)


@dataclass(frozen=True)
class DuplicationCheck:
    """One (table, key column) pair to profile for key duplication / fan-out."""

    source_table: str
    key_column: str

    @property
    def load_asset_keys(self) -> tuple[str, ...]:
        """Reuse the source's load lineage already declared in QUALITY_SOURCES."""
        return QUALITY_SOURCES[self.source_table].load_asset_keys


# The three checks the one table carries, in display order.
DUPLICATION_CHECKS: tuple[DuplicationCheck, ...] = (
    DuplicationCheck(PUM_TABLE, "uprn"),  # transaction_ids per property
    DuplicationCheck(LR_TABLE, "transaction_id"),  # repeated LR transaction ids
    DuplicationCheck(EPC_TABLE, "uprn"),  # repeated EPC uprns
)


def duplication_metrics_select(check: DuplicationCheck) -> str:
    """The SELECT that profiles one key column into a single duplication row.

    The source is grouped by its key once (NULL keys excluded from the group,
    but still counted in ``total_rows``); the group sizes are then aggregated
    into the headline figures. ``agg`` and ``tot`` are each a single-row
    aggregate, so their CROSS JOIN yields exactly one output row even when the
    table is empty or every key is NULL (the counts fall back to 0 via
    ``coalesce``; ``avg_rows_per_key`` is NULL when there are no keys to average).
    Column order matches ``DUPLICATION_COLUMNS`` for a direct INSERT.
    """
    table = check.source_table
    key = check.key_column
    return (
        f"WITH key_counts AS (\n"
        f"    SELECT {key} AS key_value, count(*) AS n\n"
        f"    FROM {table}\n"
        f"    WHERE {key} IS NOT NULL\n"
        f"    GROUP BY {key}\n"
        f"),\n"
        f"agg AS (\n"
        f"    SELECT\n"
        f"        coalesce(sum(n), 0) AS non_null_keys,\n"
        f"        count(*) AS distinct_keys,\n"
        f"        count(*) FILTER (WHERE n > 1) AS keys_with_duplicates,\n"
        f"        coalesce(sum(n) FILTER (WHERE n > 1), 0) AS duplicate_rows,\n"
        f"        coalesce(max(n), 0) AS max_rows_per_key,\n"
        f"        round(sum(n) * 1.0 / nullif(count(*), 0), 2) AS avg_rows_per_key\n"
        f"    FROM key_counts\n"
        f"),\n"
        f"tot AS (\n"
        f"    SELECT count(*) AS total_rows FROM {table}\n"
        f")\n"
        f"SELECT\n"
        f"    '{table}' AS source_table,\n"
        f"    '{key}' AS key_column,\n"
        f"    tot.total_rows,\n"
        f"    agg.non_null_keys,\n"
        f"    agg.distinct_keys,\n"
        f"    agg.keys_with_duplicates,\n"
        f"    agg.duplicate_rows,\n"
        f"    agg.max_rows_per_key,\n"
        f"    agg.avg_rows_per_key,\n"
        f"    now() AS checked_at\n"
        f"FROM agg CROSS JOIN tot"
    )
