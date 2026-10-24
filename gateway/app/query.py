"""Pure SQL builders for the ``mart_uprn_coverage_metrics`` read API.

Kept deliberately free of FastAPI and of any live database handle: every
function here takes plain Python and returns ``(sql, params)``, so the whole
filter/sort/paginate surface can be unit-tested the same DB-less way the mart's
aggregation SQL already is (see tests/ingestion/reconciliation/test_schema.py).
The router in ``routers/coverage.py`` is then just "call the builder, run the
tuple, shape the rows".

Two safety rules hold for every query this module emits:

  * **Identifiers are whitelisted, never interpolated from the request.** The
    only column names that can reach the SQL are the ones defined by the owning
    service in ``MART_COLUMNS`` / ``MART_GROUP_COLUMNS``; anything else raises
    before a query is built. So the f-strings below splice only names this
    process already trusts.
  * **Values are always parameters.** Filter values and the limit/offset go in
    as ``%s`` placeholders bound by psycopg, never formatted into the string.

Matching on the four text dimensions is case-insensitive (``upper(col) = ANY``)
because Land Registry stores county/district upper-cased while
``constituent_country`` is title-case ('England'/'Wales') — a UI shouldn't have
to know which. Each filter accepts a *list* of values (``= ANY(array)``) so a
multi-select dropdown maps to one parameter.
"""

from __future__ import annotations

from typing import Any

from services.ingestion.reconciliation.schema import (
    MART_COLUMNS,
    MART_GROUP_COLUMNS,
    MART_TABLE,
)

# The dimensions a caller may filter on — exactly the mart's grouping columns
# (the address components), which are the only non-metric columns. Re-exported
# as the single list the router, the response models, and the tests all read.
FILTER_COLUMNS: list[str] = list(MART_GROUP_COLUMNS)

# Columns a caller may sort by: any mart column. Default is the most useful
# dashboard ordering — worst-covered areas first — with a stable tiebreak so
# pagination is deterministic across pages.
SORTABLE_COLUMNS: frozenset[str] = frozenset(MART_COLUMNS)
DEFAULT_SORT_BY: str = "coverage_percentage"
DEFAULT_SORT_DIR: str = "asc"
_TIEBREAK_COLUMNS: tuple[str, ...] = (
    "constituent_country",
    "county",
    "district",
    "postcode_prefix",
)

MAX_LIMIT: int = 1000
DEFAULT_LIMIT: int = 100


def _where(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    """Build the shared ``WHERE`` clause (and its params) from active filters.

    ``filters`` maps a filter column to the list of values selected for it; a
    column with an empty/absent list places no constraint. Unknown columns are
    rejected here rather than silently ignored, so a typo in the API layer fails
    loudly instead of returning an unfiltered table.
    """
    clauses: list[str] = []
    params: list[Any] = []
    for col, values in filters.items():
        if col not in FILTER_COLUMNS:
            raise ValueError(f"not a filterable column: {col!r}")
        if not values:
            continue
        # Case-insensitive membership: upper-case both the column and the bound
        # values so 'devon', 'Devon', 'DEVON' all match the stored 'DEVON'.
        clauses.append(f"upper({col}) = ANY(%s)")
        params.append([v.upper() for v in values])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def build_coverage_query(
    filters: dict[str, list[str]],
    *,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    sort_by: str = DEFAULT_SORT_BY,
    sort_dir: str = DEFAULT_SORT_DIR,
) -> tuple[str, list[Any]]:
    """SQL + params for a filtered, sorted, paginated page of the mart.

    Returns every mart column (the four dimensions plus the three metrics) for
    the rows matching ``filters``, ordered by ``sort_by``/``sort_dir`` with a
    fixed tiebreak, limited to one page. Raises ``ValueError`` on an unknown
    filter column, an unsortable ``sort_by``, or an out-of-range page.
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

    # Sort on the chosen column, then by the dimensions, so rows that tie on the
    # sort key keep a stable order between pages. The explicit column in front is
    # dropped from the tiebreak list to avoid naming it twice.
    tiebreak = [c for c in _TIEBREAK_COLUMNS if c != sort_by]
    order_by = ", ".join([f"{sort_by} {direction}", *tiebreak])

    sql = (
        f"SELECT {', '.join(MART_COLUMNS)}\n"
        f"FROM {MART_TABLE}\n"
        f"{where}\n"
        f"ORDER BY {order_by}\n"
        f"LIMIT %s OFFSET %s"
    ).replace("\n\n", "\n")
    params = [*params, limit, offset]
    return sql, params


def build_count_query(filters: dict[str, list[str]]) -> tuple[str, list[Any]]:
    """SQL + params for the total row count under the same ``filters``.

    Lets the response report ``total`` alongside the page so the UI can render
    "showing 1–100 of N" and page controls without fetching every row.
    """
    where, params = _where(filters)
    sql = f"SELECT count(*) FROM {MART_TABLE}\n{where}".strip()
    return sql, params


def build_filter_options_query(
    column: str, filters: dict[str, list[str]]
) -> tuple[str, list[Any]]:
    """SQL + params for the distinct, non-NULL values of one filter column.

    Used to populate a dropdown. ``filters`` carries the *other* currently
    selected filters so the options can cascade — e.g. once a county is picked,
    only its districts are offered. The target ``column`` is excluded from the
    applied filters by the caller so choosing a value doesn't collapse its own
    list to the single chosen value.
    """
    if column not in FILTER_COLUMNS:
        raise ValueError(f"not a filterable column: {column!r}")
    where, params = _where(filters)
    extra = f"{'AND' if where else 'WHERE'} {column} IS NOT NULL"
    sql = (
        f"SELECT DISTINCT {column}\n"
        f"FROM {MART_TABLE}\n"
        f"{where} {extra}\n"
        f"ORDER BY {column}"
    ).strip()
    return sql, params
