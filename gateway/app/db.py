"""A small Postgres connection pool for the read API.

A coverage dashboard issues many small, short-lived SELECTs; opening a fresh
connection per request would dominate their latency. ``psycopg_pool`` keeps a
handful of connections warm and hands one to each request through the
``get_pool`` FastAPI dependency. The pool is created in the app's lifespan
(``main.py``) and closed on shutdown; nothing here opens a connection at import
time, so importing the module never needs a database.
"""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import postgres_dsn

# Rows come back as dicts keyed by column name, so the router can build response
# objects by field rather than by positional index.
_pool: ConnectionPool | None = None


def open_pool() -> ConnectionPool:
    """Create the process-wide pool (idempotent). Called from the lifespan."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=postgres_dsn(),
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


def close_pool() -> None:
    """Close the pool on shutdown. Safe to call when it was never opened."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def get_pool() -> ConnectionPool:
    """FastAPI dependency: the live pool, or a clear error if it isn't open."""
    if _pool is None:
        raise RuntimeError("connection pool is not open")
    return _pool


def run_query(pool: ConnectionPool, sql: str, params: list[Any]) -> list[dict]:
    """Run a read-only query on a pooled connection and return dict rows."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def scalar(pool: ConnectionPool, sql: str, params: list[Any]) -> Any:
    """Run a query expected to return one row/one column and return that value."""
    with pool.connection() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return next(iter(row.values())) if row else None
