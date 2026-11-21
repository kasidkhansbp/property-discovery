"""HTTP routes over the ``properties`` search table.

  * ``GET /properties`` — one page of properties ordered by uprn (default 50
    rows). Page forward with ``after_uprn`` (pass the previous page's
    ``next_after_uprn``); constant cost at any depth. No offset paging.
  * ``GET /properties/search?q=...`` — one search box: a UPRN, a full or
    partial postcode, an address containing a postcode, or free text. Returns
    the top ``limit`` matches (no paging) plus ``has_more``; see
    ``properties_query.classify_search`` for how the input is read.
  * ``GET /properties/{uprn}/history`` — every Land Registry sale and EPC
    certificate for one UPRN, merged into one timeline, newest first.

The total is the planner's estimate rather than ``count(*)``; see
``properties_query.py`` for why.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

from ..db import get_pool, run_query, scalar
from ..properties_query import (
    DEFAULT_LIMIT,
    DEFAULT_SEARCH_LIMIT,
    MAX_LIMIT,
    MAX_SEARCH_LIMIT,
    build_epc_history_query,
    build_properties_estimate_query,
    build_properties_page_query,
    build_sales_history_query,
    build_search_query,
    classify_search,
)
from ..schemas import (
    EpcEvent,
    PropertiesPage,
    PropertyHistory,
    PropertyRow,
    PropertySearchResult,
    SaleEvent,
)

router = APIRouter(prefix="/properties", tags=["properties"])

# A search that runs longer than this is cancelled and reported as "too broad"
# instead of tying up a pooled connection. Indexed lookups take milliseconds.
SEARCH_TIMEOUT_MS = 3000

_NOT_BUILT = (
    "properties table not built yet — run migration 0003, then "
    "services/jobs/ingestion/properties/build_properties.sql"
)


@router.get("", response_model=PropertiesPage, summary="A page of properties")
def list_properties(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    after_uprn: Annotated[
        int | None,
        Query(description="Keyset cursor: return rows with uprn greater than this"),
    ] = None,
) -> PropertiesPage:
    """Return ``limit`` properties ordered by uprn.

    Omit ``after_uprn`` for the first page; for the next page pass the previous
    response's ``next_after_uprn``. Each page is an index seek, so it costs the
    same at any depth.
    """
    try:
        page_sql, page_params = build_properties_page_query(
            limit=limit, after_uprn=after_uprn
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        rows = run_query(pool, page_sql, page_params)
    except pg_errors.UndefinedTable as exc:
        raise HTTPException(status_code=404, detail=_NOT_BUILT) from exc

    est_sql, est_params = build_properties_estimate_query()
    total = scalar(pool, est_sql, est_params) or 0

    items = [PropertyRow(**row) for row in rows]
    return PropertiesPage(
        total=total,
        total_is_estimate=True,
        limit=limit,
        after_uprn=after_uprn,
        # A short page means there's nothing after it.
        next_after_uprn=items[-1].uprn if len(items) == limit else None,
        items=items,
    )


@router.get(
    "/search", response_model=PropertySearchResult, summary="Search properties"
)
def search_properties(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    q: Annotated[
        str,
        Query(
            min_length=1,
            max_length=200,
            description=(
                "A UPRN, a full or partial postcode (SW1A 1AA, SW1A 1, SW1A), "
                "an address containing a postcode, or free address text"
            ),
        ),
    ],
    limit: Annotated[int, Query(ge=1, le=MAX_SEARCH_LIMIT)] = DEFAULT_SEARCH_LIMIT,
) -> PropertySearchResult:
    """Return the best ``limit`` matches for ``q``. There is no paging.

    The response's ``mode`` says how ``q`` was read. ``has_more`` means more
    rows match than were returned, so the query should be narrowed.
    """
    try:
        search = classify_search(q)
        sql, params = build_search_query(search, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        rows = run_query(pool, sql, params, timeout_ms=SEARCH_TIMEOUT_MS)
    except pg_errors.UndefinedTable as exc:
        raise HTTPException(status_code=404, detail=_NOT_BUILT) from exc
    except pg_errors.QueryCanceled as exc:
        raise HTTPException(
            status_code=422,
            detail="search too broad: add a postcode or more of the address",
        ) from exc

    items = [PropertyRow(**row) for row in rows[:limit]]
    return PropertySearchResult(
        q=q,
        mode=search.mode,
        limit=limit,
        has_more=len(rows) > limit,
        items=items,
    )


# History lookups are two index seeks (a few ms); anything slower is a fault.
HISTORY_TIMEOUT_MS = 5000


def merge_history(
    sales: list[SaleEvent], certificates: list[EpcEvent]
) -> list[SaleEvent | EpcEvent]:
    """Merge both sources into one list, newest first, undated events last.

    On the same day a sale sorts above a certificate: an EPC is usually lodged
    before the sale it was made for, so newest-first puts the sale on top.
    """
    events: list[SaleEvent | EpcEvent] = [*sales, *certificates]
    events.sort(key=lambda e: e.kind == "epc")
    events.sort(key=lambda e: e.date is not None)
    events.sort(key=lambda e: e.date or date.min, reverse=True)
    return events


@router.get(
    "/{uprn}/history",
    response_model=PropertyHistory,
    summary="Sales and EPC certificates for one property",
)
def property_history(
    pool: Annotated[ConnectionPool, Depends(get_pool)],
    uprn: Annotated[int, Path(ge=0, le=999_999_999_999)],
) -> PropertyHistory:
    """Every Land Registry sale and EPC certificate for ``uprn``, newest first.

    Nothing is capped: every linked sale and every certificate is returned. A
    UPRN with no records returns empty ``events`` rather than 404.
    """
    sales_sql, sales_params = build_sales_history_query(uprn)
    epc_sql, epc_params = build_epc_history_query(uprn)
    try:
        sale_rows = run_query(
            pool, sales_sql, sales_params, timeout_ms=HISTORY_TIMEOUT_MS
        )
        epc_rows = run_query(pool, epc_sql, epc_params, timeout_ms=HISTORY_TIMEOUT_MS)
    except pg_errors.UndefinedTable as exc:
        raise HTTPException(
            status_code=404, detail=f"history source table missing: {exc}"
        ) from exc

    sales = [SaleEvent(date=r.pop("transfer_date"), **r) for r in sale_rows]
    certificates = [EpcEvent(date=r.pop("lodgement_date"), **r) for r in epc_rows]
    return PropertyHistory(
        uprn=uprn,
        sale_count=len(sales),
        epc_count=len(certificates),
        events=merge_history(sales, certificates),
    )
