"""Engine and session helpers over the serving Postgres.

Sync, not async: the ingestion jobs use psycopg (v3) + DuckDB and the gateway
uses a psycopg pool — the whole codebase is synchronous, so this builds a sync
SQLAlchemy engine on psycopg3.

The engine is created lazily on first use so importing this module never reads
the environment or opens a socket — the caller (a job or the gateway) sets
``POSTGRES_DSN`` before any DB work is triggered. ``POSTGRES_DSN`` is the same
variable the pipeline's ``PostgresResource`` and the gateway already use; a
legacy ``DATABASE_URL`` is accepted as a fallback.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _dsn() -> str:
    dsn = os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("POSTGRES_DSN (or DATABASE_URL) is not set")
    # SQLAlchemy needs an explicit driver; normalise to psycopg (v3).
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql+psycopg://", 1)
    elif dsn.startswith("postgresql://"):
        dsn = dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return dsn


def dsn() -> str:
    """The normalised SQLAlchemy URL (psycopg driver) from the environment."""
    return _dsn()


def get_engine() -> Engine:
    """The process-wide engine, built on first call from ``POSTGRES_DSN``."""
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(_dsn(), pool_pre_ping=True, future=True)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """The session factory, creating the engine on first call."""
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional session: commits on success, rolls back on error.

    Usage::

        with session_scope() as s:
            s.add(obj)
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
