"""HTTP routes over the per-table ``<table>_quality`` companions.

Three read-only endpoints:

  * ``GET /quality`` — a one-row-per-table summary (source row count, columns
    profiled, average and worst coverage, snapshot time) across every profiled
    table: the dashboard landing.
  * ``GET /quality/tables`` — the profiled table names and their companion
    table names; static, no database needed.
  * ``GET /quality/{source_table}`` — every profiled column of one table, with
    its populated / NULL / blank counts and coverage, optionally narrowed to a
    coverage range and sorted.

As with the coverage router, the route functions stay thin: validate/translate
the request, hand off to the pure builders in ``quality_query.py``, run the
resulting ``(sql, params)`` on a pooled connection, and shape the rows. A bad
sort/filter value surfaces from the builder as ``ValueError`` -> HTTP 422; a
table that hasn't been built yet surfaces as ``UndefinedTable`` -> HTTP 404.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

from ..db import get_pool, run_query
from ..quality_query import (
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIR,
    SORTABLE_COLUMNS,
    SOURCE_TABLES,
    build_quality_query,
    build_quality_summary_query,
)
from ..schemas import (
    QualityColumnRow,
    QualitySummary,
    QualitySummaryRow,
    QualityTable,
)
from services.ingestion.data_quality.schema import QUALITY_SOURCES

router = APIRouter(prefix="/quality", tags=["quality"])

_NOT_BUILT = (
    "quality table not built yet — run the matching *_quality job "
    "(see services/ingestion/data_quality)"
)


@router.get("", response_model=QualitySummary, summary="Coverage summary per table")
def quality_summary(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
) -> QualitySummary:
    """Headline coverage for every profiled table — reads only the tiny companions."""
    sql, params = build_quality_summary_query()
    try:
        rows = run_query(pool, sql, params)
    except pg_errors.UndefinedTable as exc:
        raise HTTPException(status_code=404, detail=_NOT_BUILT) from exc
    return QualitySummary(items=[QualitySummaryRow(**row) for row in rows])


@router.get(
    "/tables",
    response_model=list[dict],
    summary="The profiled tables and their companion names",
)
def quality_tables() -> list[dict]:
    """List the source tables that are profiled and their ``*_quality`` companions."""
    return [
        {"source_table": name, "quality_table": source.quality_table}
        for name, source in QUALITY_SOURCES.items()
    ]


@router.get(
    "/{source_table}",
    response_model=QualityTable,
    summary="Per-column coverage of one table",
)
def quality_for_table(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    source_table: Annotated[
        str,
        Path(description=f"One of: {', '.join(SOURCE_TABLES)}"),
    ],
    min_coverage: Annotated[
        float | None,
        Query(ge=0, le=100, description="Only columns with coverage_pct >= this"),
    ] = None,
    max_coverage: Annotated[
        float | None,
        Query(ge=0, le=100, description="Only columns with coverage_pct <= this"),
    ] = None,
    sort_by: Annotated[
        str, Query(description=f"One of: {', '.join(sorted(SORTABLE_COLUMNS))}")
    ] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(pattern="^(?i)(asc|desc)$")] = DEFAULT_SORT_DIR,
) -> QualityTable:
    """Return every profiled column of ``source_table`` (worst-covered first).

    Use ``max_coverage`` to surface problem columns (e.g. ``?max_coverage=90``).
    An unknown table returns 404; a quality table that hasn't been built yet also
    returns 404 with a hint to run its job.
    """
    if source_table not in SOURCE_TABLES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown table {source_table!r}; one of: {', '.join(SOURCE_TABLES)}",
        )
    try:
        sql, params = build_quality_query(
            source_table,
            min_coverage=min_coverage,
            max_coverage=max_coverage,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        rows = run_query(pool, sql, params)
    except pg_errors.UndefinedTable as exc:
        raise HTTPException(status_code=404, detail=_NOT_BUILT) from exc

    columns = [QualityColumnRow(**row) for row in rows]
    # total_rows / checked_at are identical on every row; lift them to the top
    # level for convenience (0 / None when no rows match the coverage filter).
    return QualityTable(
        source_table=source_table,
        quality_table=QUALITY_SOURCES[source_table].quality_table,
        total_rows=columns[0].total_rows if columns else 0,
        checked_at=columns[0].checked_at if columns else None,
        columns=columns,
    )
