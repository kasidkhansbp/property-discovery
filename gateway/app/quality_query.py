"""Pure SQL builders for the per-table data-quality read API.

Like ``query.py`` (the coverage builders), this module is kept free of FastAPI
and of any live database handle: every function takes plain Python and returns
``(sql, params)``, so the whole surface is unit-testable without Postgres.

The quality tables are the ``<table>_quality`` companions built by the
``data_quality`` service — one row per source column, carrying how populated
that column is (see services/jobs/ingestion/data_quality/schema.py). They are tiny
(at most a few dozen rows each), so there is no paging here; a caller gets every
column row for a table, optionally narrowed to a coverage range and sorted.

The same two safety rules as the coverage builders hold for every query emitted:

  * **Identifiers are whitelisted, never interpolated from the request.** The
    only table names that can reach the SQL are the ``data_quality`` service's
    own ``QUALITY_SOURCES``; the only column names are its ``QUALITY_COLUMNS``.
    Anything else raises ``ValueError`` before a query is built.
  * **Values are always parameters.** Coverage bounds go in as ``%s``
    placeholders bound by psycopg, never formatted into the string.
"""

from __future__ import annotations

from typing import Any

from shared.db.schema import (
    DUPLICATION_COLUMNS,
    DUPLICATION_TABLE,
    QUALITY_COLUMNS,
    QUALITY_SOURCES,
)

# The source tables a caller may ask about, by their real (source) name — the
# names users already know (land_registry_sales, epc_domestic_certificates, …).
# Each maps to its physical ``<name>_quality`` companion table.
SOURCE_TABLES: list[str] = list(QUALITY_SOURCES)

# Columns a caller may sort by: any column of the quality table.
SORTABLE_COLUMNS: frozenset[str] = frozenset(QUALITY_COLUMNS)
# Default ordering — worst-covered columns first — matching the coverage API's
# "problems first" default, with column order as a stable tiebreak.
DEFAULT_SORT_BY: str = "coverage_pct"
DEFAULT_SORT_DIR: str = "asc"
_TIEBREAK: str = "column_position"


def _quality_table(source_table: str) -> str:
    """Resolve a source table name to its whitelisted ``*_quality`` table name."""
    try:
        return QUALITY_SOURCES[source_table].quality_table
    except KeyError:
        raise ValueError(f"not a profiled table: {source_table!r}") from None


def build_quality_query(
    source_table: str,
    *,
    min_coverage: float | None = None,
    max_coverage: float | None = None,
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
) -> tuple[str, list[Any]]:
    """SQL + params for the per-column quality rows of one source table.

    Returns every quality column for each profiled source column, optionally
    restricted to ``min_coverage <= coverage_pct <= max_coverage`` (either bound
    may be omitted), ordered by ``sort_by``/``sort_dir`` with a stable
    column-order tiebreak. Raises ``ValueError`` on an unknown table, an
    unsortable column, a bad direction, or an out-of-range coverage bound.
    """
    table = _quality_table(source_table)  # raises on unknown table

    if sort_by not in SORTABLE_COLUMNS:
        raise ValueError(f"not a sortable column: {sort_by!r}")
    direction = sort_dir.lower()
    if direction not in ("asc", "desc"):
        raise ValueError(f"sort_dir must be 'asc' or 'desc', got {sort_dir!r}")

    clauses: list[str] = []
    params: list[Any] = []
    for bound, op in ((min_coverage, ">="), (max_coverage, "<=")):
        if bound is not None:
            if not 0 <= bound <= 100:
                raise ValueError(f"coverage bound must be 0..100, got {bound}")
            clauses.append(f"coverage_pct {op} %s")
            params.append(bound)
    where = f"WHERE {' AND '.join(clauses)}\n" if clauses else ""

    order_by = f"{sort_by} {direction}"
    if sort_by != _TIEBREAK:
        order_by += f", {_TIEBREAK}"

    sql = (
        f"SELECT {', '.join(QUALITY_COLUMNS)}\n"
        f"FROM {table}\n"
        f"{where}"
        f"ORDER BY {order_by}"
    )
    return sql, params


def build_quality_summary_query() -> tuple[str, list[Any]]:
    """SQL (no params) for a one-row-per-table rollup across all quality tables.

    For each profiled table it reports the source row count, how many columns
    were profiled, the average and worst per-column coverage, and when the
    snapshot was taken — a cheap dashboard landing that reads only the tiny
    quality tables, never the multi-million-row sources. The table names spliced
    in are the service's own ``QUALITY_SOURCES`` (never request input).
    """
    branches = []
    for source_table, source in QUALITY_SOURCES.items():
        branches.append(
            f"SELECT '{source_table}' AS source_table, "
            f"'{source.quality_table}' AS quality_table, "
            f"coalesce(max(total_rows), 0) AS total_rows, "
            f"count(*) AS columns_profiled, "
            f"round(avg(coverage_pct), 2) AS average_coverage_pct, "
            f"min(coverage_pct) AS worst_coverage_pct, "
            f"max(checked_at) AS checked_at "
            f"FROM {source.quality_table}"
        )
    sql = "\nUNION ALL\n".join(branches) + "\nORDER BY source_table"
    return sql, []


# --------------------------------------------------------------------------- #
# Key-duplication / fan-out table (``key_duplication_quality``).              #
#                                                                             #
# One flat table, one row per check — already a summary — so there is a single #
# builder returning every row, optionally narrowed to checks with at least N  #
# duplicated keys and sorted. Same two safety rules as above: the table name   #
# is the service's own constant (never request input) and the only sortable    #
# identifiers are its own ``DUPLICATION_COLUMNS``; the filter value is bound.   #
# --------------------------------------------------------------------------- #
DUPLICATION_SORTABLE_COLUMNS: frozenset[str] = frozenset(DUPLICATION_COLUMNS)
# Default ordering — the most duplicated keys first (problems first), matching
# the coverage API's convention, with the source table as a stable tiebreak.
DEFAULT_DUP_SORT_BY: str = "keys_with_duplicates"
DEFAULT_DUP_SORT_DIR: str = "desc"
_DUP_TIEBREAK: str = "source_table"


def build_duplication_query(
    *,
    min_duplicate_keys: int | None = None,
    sort_by: str = DEFAULT_DUP_SORT_BY,
    sort_dir: str = DEFAULT_DUP_SORT_DIR,
) -> tuple[str, list[Any]]:
    """SQL + params for the key-duplication checks (one row per check).

    Returns every check row, optionally restricted to those with at least
    ``min_duplicate_keys`` duplicated key values, ordered by ``sort_by`` /
    ``sort_dir`` with a stable source-table tiebreak. Raises ``ValueError`` on an
    unsortable column, a bad direction, or a negative ``min_duplicate_keys``.
    """
    if sort_by not in DUPLICATION_SORTABLE_COLUMNS:
        raise ValueError(f"not a sortable column: {sort_by!r}")
    direction = sort_dir.lower()
    if direction not in ("asc", "desc"):
        raise ValueError(f"sort_dir must be 'asc' or 'desc', got {sort_dir!r}")

    params: list[Any] = []
    where = ""
    if min_duplicate_keys is not None:
        if min_duplicate_keys < 0:
            raise ValueError(
                f"min_duplicate_keys must be >= 0, got {min_duplicate_keys}"
            )
        where = "WHERE keys_with_duplicates >= %s\n"
        params.append(min_duplicate_keys)

    order_by = f"{sort_by} {direction}"
    if sort_by != _DUP_TIEBREAK:
        order_by += f", {_DUP_TIEBREAK}"

    sql = (
        f"SELECT {', '.join(DUPLICATION_COLUMNS)}\n"
        f"FROM {DUPLICATION_TABLE}\n"
        f"{where}"
        f"ORDER BY {order_by}"
    )
    return sql, params
