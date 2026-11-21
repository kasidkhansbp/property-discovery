"""HTTP routes over the ``properties`` search table.

  * ``GET /properties`` — one page of properties ordered by uprn (default 50
    rows). Page forward with ``after_uprn`` (pass the previous page's
    ``next_after_uprn``); constant cost at any depth. No offset paging.

The total is the planner's estimate rather than ``count(*)``; see
``properties_query.py`` for why.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import errors as pg_errors
from psycopg_pool import ConnectionPool

from ..db import get_pool, run_query, scalar
from ..properties_query import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    build_properties_estimate_query,
    build_properties_page_query,
)
from ..schemas import PropertiesPage, PropertyRow

router = APIRouter(prefix="/properties", tags=["properties"])

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
