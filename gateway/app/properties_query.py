"""Pure SQL builders for the ``properties`` read API.

Like ``query.py`` and ``quality_query.py``, nothing here touches FastAPI or a
live database: each function returns ``(sql, params)`` so the paging rules are
unit-testable without Postgres.

``properties`` is large (~40M rows, one per UPRN), which shapes two choices:

  * **Rows are always ordered by ``uprn``** (the primary key), so every page is
    an index range scan and paging is deterministic.
  * **Keyset paging only.** A page is "the next ``limit`` rows after
    ``after_uprn``", an index seek that costs the same on page 1 and page
    800,000. There is deliberately no ``offset``: Postgres walks every skipped
    row, so deep offsets take seconds. Previous is handled client-side by
    remembering the cursors already visited.
  * **The total is an estimate.** An exact ``count(*)`` over 40M rows takes
    seconds on every request; the planner's ``reltuples`` statistic is instant
    and accurate to well under 1% after ``ANALYZE`` (which the build script
    runs). Good enough for "page X of Y".

Same safety rules as the other builders: identifiers come only from the shared
model (``PROPERTIES_TABLE`` / ``PROPERTIES_COLUMNS``), values are always bound
as ``%s`` parameters.
"""

from __future__ import annotations

from typing import Any

from shared.db.schema import PROPERTIES_COLUMNS, PROPERTIES_TABLE

DEFAULT_LIMIT: int = 50
MAX_LIMIT: int = 200
_ORDER_COLUMN: str = "uprn"


def build_properties_page_query(
    *,
    limit: int = DEFAULT_LIMIT,
    after_uprn: int | None = None,
) -> tuple[str, list[Any]]:
    """SQL + params for one page of ``properties``, ordered by ``uprn``.

    With ``after_uprn`` set, returns the ``limit`` rows whose uprn is greater
    than it; without it, the first page. Raises ``ValueError`` for an
    out-of-range limit.
    """
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be 1..{MAX_LIMIT}, got {limit}")

    params: list[Any] = []
    where = ""
    if after_uprn is not None:
        where = f"WHERE {_ORDER_COLUMN} > %s\n"
        params.append(after_uprn)

    sql = (
        f"SELECT {', '.join(PROPERTIES_COLUMNS)}\n"
        f"FROM {PROPERTIES_TABLE}\n"
        f"{where}"
        f"ORDER BY {_ORDER_COLUMN}\n"
        f"LIMIT %s"
    )
    params.append(limit)
    return sql, params


def build_properties_estimate_query() -> tuple[str, list[Any]]:
    """SQL + params for the planner's row-count estimate of ``properties``.

    ``reltuples`` is -1 for a table that has never been vacuumed/analysed, so
    that case is clamped to 0 rather than reported as a negative total.
    """
    sql = (
        "SELECT greatest(reltuples, 0)::bigint AS estimated_total\n"
        "FROM pg_class\n"
        "WHERE oid = to_regclass(%s)"
    )
    return sql, [PROPERTIES_TABLE]
