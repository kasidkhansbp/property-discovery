"""Pure SQL builders for the ``mart_epc_uprn_coverage`` read API.

The EPC-side companion to ``query.py`` (which serves the Land Registry-side
mart). Same shape and the same two safety rules:

  * **Identifiers are whitelisted.** Only column names from the shared model
    (``EPC_COVERAGE_COLUMNS`` / ``EPC_COVERAGE_GROUP_COLUMNS``) are spliced into
    SQL; anything else raises ``ValueError`` before a query is built.
  * **Values are always parameters** (``%s``), never formatted into the string.

Filters are case-insensitive multi-selects on the six grouping columns
(``upper(col) = ANY(%s)``). The extra builder here is ``build_summary_query``:
the mart is fine-grained (~280K rows), so the dashboard's headline cards sum it
up by one dimension — property type by default — under the same filters.
"""

from __future__ import annotations

from typing import Any

from shared.db.schema import (
    EPC_COVERAGE_COLUMNS,
    EPC_COVERAGE_GROUP_COLUMNS,
    EPC_COVERAGE_TABLE,
)

FILTER_COLUMNS: list[str] = list(EPC_COVERAGE_GROUP_COLUMNS)

# Any dimension can be the summary's grouping; property type is the headline.
GROUP_BY_COLUMNS: list[str] = list(EPC_COVERAGE_GROUP_COLUMNS)
DEFAULT_GROUP_BY: str = "property_type"

# Rows are returned without built_at (it is identical on every row and served
# once, by the summary). Sortable: any returned column.
ROW_COLUMNS: list[str] = [c for c in EPC_COVERAGE_COLUMNS if c != "built_at"]
SORTABLE_COLUMNS: frozenset[str] = frozenset(ROW_COLUMNS)
# Default: biggest gaps first — the groups with the most unlinked UPRNs.
DEFAULT_SORT_BY: str = "uprns_without_transaction"
DEFAULT_SORT_DIR: str = "desc"

MAX_LIMIT: int = 1000
DEFAULT_LIMIT: int = 100


def _where(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    """Shared ``WHERE`` clause (and params) from the active filters."""
    clauses: list[str] = []
    params: list[Any] = []
    for col, values in filters.items():
        if col not in FILTER_COLUMNS:
            raise ValueError(f"not a filterable column: {col!r}")
        if not values:
            continue
        clauses.append(f"upper({col}) = ANY(%s)")
        params.append([v.upper() for v in values])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def build_rows_query(
    filters: dict[str, list[str]],
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
) -> tuple[str, list[Any]]:
    """SQL + params for a filtered, sorted, paginated page of mart rows.

    Ties on the sort key are broken by the six dimensions so pages are stable.
    """
    if sort_by not in SORTABLE_COLUMNS:
        raise ValueError(f"not a sortable column: {sort_by!r}")
    direction = sort_dir.lower()
    if direction not in ("asc", "desc"):
        raise ValueError(f"sort_dir must be 'asc' or 'desc', got {sort_dir!r}")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")

    where, params = _where(filters)
    tiebreak = [c for c in FILTER_COLUMNS if c != sort_by]
    order_by = ", ".join([f"{sort_by} {direction}", *tiebreak])
    sql = "\n".join(
        part
        for part in (
            f"SELECT {', '.join(ROW_COLUMNS)}",
            f"FROM {EPC_COVERAGE_TABLE}",
            where,
            f"ORDER BY {order_by}",
            "LIMIT %s OFFSET %s",
        )
        if part
    )
    return sql, [*params, limit, offset]


def build_count_query(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    """SQL + params for the number of mart rows under ``filters``."""
    where, params = _where(filters)
    return f"SELECT count(*) FROM {EPC_COVERAGE_TABLE}\n{where}".strip(), params


def build_summary_query(
    filters: dict[str, list[str]], *, group_by: str = DEFAULT_GROUP_BY
) -> tuple[str, list[Any]]:
    """SQL + params summing the mart by one dimension under ``filters``.

    One row per value of ``group_by`` (biggest first), each with its UPRN totals
    and the coverage recomputed from the sums — never an average of the per-row
    percentages, which would weight a 3-UPRN group like a 3,000-UPRN one. Sums
    are cast to bigint because Postgres widens SUM(bigint) to numeric.
    """
    if group_by not in GROUP_BY_COLUMNS:
        raise ValueError(f"not a groupable column: {group_by!r}")
    where, params = _where(filters)
    sql = "\n".join(
        part
        for part in (
            "SELECT",
            f"    {group_by} AS value,",
            "    sum(epc_uprns)::bigint                 AS epc_uprns,",
            "    sum(uprns_with_transaction)::bigint    AS uprns_with_transaction,",
            "    sum(uprns_without_transaction)::bigint AS uprns_without_transaction",
            f"FROM {EPC_COVERAGE_TABLE}",
            where,
            "GROUP BY 1",
            "ORDER BY 2 DESC, 1",
        )
        if part
    )
    return sql, params


def build_built_at_query() -> tuple[str, list[Any]]:
    """SQL for the snapshot's build time (NULL while the mart is empty)."""
    return f"SELECT max(built_at) FROM {EPC_COVERAGE_TABLE}", []


def build_filter_options_query(
    column: str, filters: dict[str, list[str]]
) -> tuple[str, list[Any]]:
    """SQL + params for the distinct non-NULL values of one filter column.

    ``filters`` holds the *other* applied filters (the caller drops ``column``
    itself), so the dropdowns cascade without collapsing their own list.
    """
    if column not in FILTER_COLUMNS:
        raise ValueError(f"not a filterable column: {column!r}")
    where, params = _where(filters)
    extra = f"{'AND' if where else 'WHERE'} {column} IS NOT NULL"
    sql = (
        f"SELECT DISTINCT {column}\n"
        f"FROM {EPC_COVERAGE_TABLE}\n"
        f"{where} {extra}\n"
        f"ORDER BY {column}"
    )
    return sql, params


def coverage_pct(with_txn: int, total: int) -> float | None:
    """with / total * 100 to 2 dp; None for an empty group."""
    return round(with_txn * 100.0 / total, 2) if total else None
