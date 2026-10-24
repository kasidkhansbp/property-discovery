"""HTTP routes over ``mart_uprn_coverage_metrics``.

Two endpoints, both read-only:

  * ``GET /coverage-metrics`` — a filtered, sorted, paginated page of the mart.
    The four address components are each multi-select (repeat the query param,
    e.g. ``?county=DEVON&county=CORNWALL``), mapping straight to a multi-select
    dropdown in the UI.
  * ``GET /coverage-metrics/filter-options`` — the distinct values for each of
    those four dropdowns, cascading on whatever filters are already applied.

The route functions stay thin: translate query params into the ``filters`` dict,
hand it to the pure builders in ``query.py``, run the resulting ``(sql, params)``
on a pooled connection, and shape the rows. A bad filter/sort value surfaces
from the builder as ``ValueError`` and is returned as HTTP 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg_pool import ConnectionPool

from ..db import get_pool, run_query, scalar
from ..query import (
    DEFAULT_LIMIT,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIR,
    FILTER_COLUMNS,
    MAX_LIMIT,
    SORTABLE_COLUMNS,
    build_count_query,
    build_coverage_query,
    build_filter_options_query,
)
from ..schemas import CoveragePage, CoverageRow, FilterOptions

router = APIRouter(prefix="/coverage-metrics", tags=["coverage"])

# Shared query-param declarations for the four address-component filters, so the
# endpoint signature and the OpenAPI docs stay in lock-step with FILTER_COLUMNS.
_FILTER_DESCRIPTION = {
    "constituent_country": "Country bucket, e.g. England / Wales (repeatable).",
    "county": "County name (repeatable; case-insensitive).",
    "district": "District / local-authority name (repeatable; case-insensitive).",
    "postcode_prefix": "Outward code, e.g. EX4 / CF36 (repeatable).",
}


@router.get("", response_model=CoveragePage, summary="Filtered coverage metrics")
def list_coverage_metrics(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    constituent_country: Annotated[
        list[str] | None, Query(description=_FILTER_DESCRIPTION["constituent_country"])
    ] = None,
    county: Annotated[
        list[str] | None, Query(description=_FILTER_DESCRIPTION["county"])
    ] = None,
    district: Annotated[
        list[str] | None, Query(description=_FILTER_DESCRIPTION["district"])
    ] = None,
    postcode_prefix: Annotated[
        list[str] | None, Query(description=_FILTER_DESCRIPTION["postcode_prefix"])
    ] = None,
    sort_by: Annotated[
        str, Query(description=f"One of: {', '.join(sorted(SORTABLE_COLUMNS))}")
    ] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(pattern="^(?i)(asc|desc)$")] = DEFAULT_SORT_DIR,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CoveragePage:
    """Return one page of coverage buckets matching the address-component filters.

    ``total`` is the full count under the same filters (ignoring paging) so the
    UI can render page controls.
    """
    filters = _collect_filters(
        constituent_country=constituent_country,
        county=county,
        district=district,
        postcode_prefix=postcode_prefix,
    )
    try:
        page_sql, page_params = build_coverage_query(
            filters, limit=limit, offset=offset, sort_by=sort_by, sort_dir=sort_dir
        )
        count_sql, count_params = build_count_query(filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = run_query(pool, page_sql, page_params)
    total = scalar(pool, count_sql, count_params) or 0
    return CoveragePage(
        total=total,
        limit=limit,
        offset=offset,
        items=[CoverageRow(**row) for row in rows],
    )


@router.get(
    "/filter-options",
    response_model=FilterOptions,
    summary="Distinct values for each filter dropdown",
)
def coverage_filter_options(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    constituent_country: Annotated[list[str] | None, Query()] = None,
    county: Annotated[list[str] | None, Query()] = None,
    district: Annotated[list[str] | None, Query()] = None,
    postcode_prefix: Annotated[list[str] | None, Query()] = None,
) -> FilterOptions:
    """Return the selectable values for every filter, cascading on the applied ones.

    For each of the four columns, the options reflect the *other* three filters
    currently set (the column itself is excluded from its own narrowing), so
    picking a county shrinks the district/prefix lists but leaves the full list
    of counties visible.
    """
    applied = _collect_filters(
        constituent_country=constituent_country,
        county=county,
        district=district,
        postcode_prefix=postcode_prefix,
    )
    options: dict[str, list[str]] = {}
    for column in FILTER_COLUMNS:
        others = {c: v for c, v in applied.items() if c != column}
        sql, params = build_filter_options_query(column, others)
        options[column] = [next(iter(row.values())) for row in run_query(pool, sql, params)]
    return FilterOptions(**options)


def _collect_filters(**kwargs: list[str] | None) -> dict[str, list[str]]:
    """Drop unset (None) params so only active filters reach the query builder."""
    return {col: values for col, values in kwargs.items() if values}
