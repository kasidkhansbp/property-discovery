"""HTTP routes over ``mart_epc_uprn_coverage`` — EPC UPRN -> transaction coverage.

Three read-only endpoints:

  * ``GET /epc-uprn-coverage/summary`` — totals grouped by one dimension
    (``group_by``, default ``property_type``) plus the overall total and the
    snapshot's build time. Feeds the dashboard's headline cards; with a filter
    and another ``group_by`` it drills in (e.g. ``?property_type=Flat&group_by=tenure``).
  * ``GET /epc-uprn-coverage`` — a filtered, sorted, paginated page of mart rows.
  * ``GET /epc-uprn-coverage/filter-options`` — cascading dropdown values.

All six dimensions are multi-select filters on every endpoint (repeat the param:
``?tenure=owner-occupied&tenure=unknown``). As in ``coverage.py``, the routes are
thin: collect filters, call the pure builders in ``epc_coverage_query.py``, run
the SQL, shape the rows. A bad column name comes back as HTTP 422.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg_pool import ConnectionPool

from ..db import get_pool, run_query, scalar
from ..epc_coverage_query import (
    DEFAULT_GROUP_BY,
    DEFAULT_LIMIT,
    DEFAULT_SORT_BY,
    DEFAULT_SORT_DIR,
    FILTER_COLUMNS,
    GROUP_BY_COLUMNS,
    MAX_LIMIT,
    SORTABLE_COLUMNS,
    build_built_at_query,
    build_count_query,
    build_filter_options_query,
    build_rows_query,
    build_summary_query,
    coverage_pct,
)
from ..schemas import (
    EpcCoverageFilterOptions,
    EpcCoveragePage,
    EpcCoverageRow,
    EpcCoverageSummary,
    EpcCoverageSummaryRow,
)

router = APIRouter(prefix="/epc-uprn-coverage", tags=["epc-uprn-coverage"])

# One declaration per filter so every endpoint's signature and OpenAPI docs agree.
PropertyType = Annotated[
    list[str] | None,
    Query(description="House / Flat / Maisonette / Bungalow / Park home (repeatable)."),
]
BuiltForm = Annotated[
    list[str] | None, Query(description="e.g. Detached / Mid-Terrace (repeatable).")
]
Tenure = Annotated[
    list[str] | None,
    Query(description="owner-occupied / rented (social) / rented (private) / unknown."),
]
UprnSource = Annotated[
    list[str] | None,
    Query(description="How the UPRN got onto the cert: Energy Assessor / Address Matched."),
]
Country = Annotated[list[str] | None, Query(description="England / Wales (repeatable).")]
PostcodePrefix = Annotated[
    list[str] | None, Query(description="Outward code, e.g. EX4 / CF36 (repeatable).")
]


def _filters(**kwargs: list[str] | None) -> dict[str, list[str]]:
    """Drop unset params so only active filters reach the builders."""
    return {col: values for col, values in kwargs.items() if values}


@router.get(
    "/summary",
    response_model=EpcCoverageSummary,
    summary="Coverage totals grouped by property type (or another dimension)",
)
def epc_coverage_summary(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    group_by: Annotated[
        str, Query(description=f"One of: {', '.join(GROUP_BY_COLUMNS)}")
    ] = DEFAULT_GROUP_BY,
    property_type: PropertyType = None,
    built_form: BuiltForm = None,
    tenure: Tenure = None,
    uprn_source: UprnSource = None,
    constituent_country: Country = None,
    postcode_prefix: PostcodePrefix = None,
) -> EpcCoverageSummary:
    """Sum the mart by ``group_by`` under the filters, plus an overall total."""
    filters = _filters(
        property_type=property_type,
        built_form=built_form,
        tenure=tenure,
        uprn_source=uprn_source,
        constituent_country=constituent_country,
        postcode_prefix=postcode_prefix,
    )
    try:
        sql, params = build_summary_query(filters, group_by=group_by)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    items = [
        EpcCoverageSummaryRow(
            **row,
            coverage_percentage=coverage_pct(
                row["uprns_with_transaction"], row["epc_uprns"]
            ),
        )
        for row in run_query(pool, sql, params)
    ]
    n = sum(i.epc_uprns for i in items)
    w = sum(i.uprns_with_transaction for i in items)
    total = EpcCoverageSummaryRow(
        value=None,
        epc_uprns=n,
        uprns_with_transaction=w,
        uprns_without_transaction=n - w,
        coverage_percentage=coverage_pct(w, n),
    )
    built_at = scalar(pool, *build_built_at_query())
    return EpcCoverageSummary(
        group_by=group_by, built_at=built_at, total=total, items=items
    )


@router.get("", response_model=EpcCoveragePage, summary="Filtered coverage rows")
def list_epc_coverage(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    property_type: PropertyType = None,
    built_form: BuiltForm = None,
    tenure: Tenure = None,
    uprn_source: UprnSource = None,
    constituent_country: Country = None,
    postcode_prefix: PostcodePrefix = None,
    sort_by: Annotated[
        str, Query(description=f"One of: {', '.join(sorted(SORTABLE_COLUMNS))}")
    ] = DEFAULT_SORT_BY,
    sort_dir: Annotated[str, Query(pattern="^(?i)(asc|desc)$")] = DEFAULT_SORT_DIR,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EpcCoveragePage:
    """One page of mart rows; by default the biggest gaps (most unlinked UPRNs) first."""
    filters = _filters(
        property_type=property_type,
        built_form=built_form,
        tenure=tenure,
        uprn_source=uprn_source,
        constituent_country=constituent_country,
        postcode_prefix=postcode_prefix,
    )
    try:
        page_sql, page_params = build_rows_query(
            filters, limit=limit, offset=offset, sort_by=sort_by, sort_dir=sort_dir
        )
        count_sql, count_params = build_count_query(filters)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    rows = run_query(pool, page_sql, page_params)
    total = scalar(pool, count_sql, count_params) or 0
    return EpcCoveragePage(
        total=total,
        limit=limit,
        offset=offset,
        items=[EpcCoverageRow(**row) for row in rows],
    )


@router.get(
    "/filter-options",
    response_model=EpcCoverageFilterOptions,
    summary="Distinct values for each filter dropdown",
)
def epc_coverage_filter_options(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    property_type: PropertyType = None,
    built_form: BuiltForm = None,
    tenure: Tenure = None,
    uprn_source: UprnSource = None,
    constituent_country: Country = None,
    postcode_prefix: PostcodePrefix = None,
) -> EpcCoverageFilterOptions:
    """Each column's options reflect the *other* applied filters (cascading)."""
    applied = _filters(
        property_type=property_type,
        built_form=built_form,
        tenure=tenure,
        uprn_source=uprn_source,
        constituent_country=constituent_country,
        postcode_prefix=postcode_prefix,
    )
    options: dict[str, list[str]] = {}
    for column in FILTER_COLUMNS:
        others = {c: v for c, v in applied.items() if c != column}
        sql, params = build_filter_options_query(column, others)
        options[column] = [next(iter(r.values())) for r in run_query(pool, sql, params)]
    return EpcCoverageFilterOptions(**options)
