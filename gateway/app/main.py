"""FastAPI application for the property-discovery gateway.

Run it from the repo root (so ``services.jobs.ingestion.*`` imports resolve, same as
Dagster) with the serving DB's ``POSTGRES_DSN`` in the environment or repo
``.env``::

    uvicorn gateway.app.main:app --reload

The interactive docs are then at http://127.0.0.1:8000/docs. The connection
pool is opened on startup and closed on shutdown via the lifespan below, so no
database work happens at import time.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import close_pool, open_pool
from .routers import coverage, properties, quality


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    try:
        yield
    finally:
        close_pool()


app = FastAPI(
    title="Property Discovery — Coverage & Data-Quality API",
    description=(
        "Read-only access to the serving database. `/coverage-metrics` exposes "
        "mart_uprn_coverage_metrics (UPRN match coverage pre-aggregated per "
        "address component). `/quality` exposes the per-table data-quality "
        "companions: per-column coverage (how populated each column is) for "
        "land_registry_sales, epc_domestic_certificates, os_open_uprn and "
        "property_uprn_mapping, plus `/quality/duplication` for key-duplication "
        "/ fan-out across those tables. `/properties` pages through the "
        "properties table (one row per UPRN)."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# The frontend (frontend/) is served from a different origin in development, so
# allow cross-origin reads. Tighten `allow_origins` to the real UI origin(s)
# before this is exposed beyond local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(coverage.router)
app.include_router(quality.router)
app.include_router(properties.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
def health() -> dict[str, str]:
    return {"status": "ok"}
