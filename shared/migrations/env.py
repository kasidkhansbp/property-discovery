"""Alembic environment for the shared schema.

``target_metadata`` is the shared ``Base.metadata`` with every model imported, so
``--autogenerate`` diffs the models against the live database. The URL comes from
``POSTGRES_DSN`` via ``shared.db.connection`` — never from the ini file.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from shared.db import models  # noqa: F401 — registers every table on the metadata
from shared.db.base import Base
from shared.db.connection import dsn, get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL against the URL, without a live connection."""
    context.configure(
        url=dsn(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection built from POSTGRES_DSN."""
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
