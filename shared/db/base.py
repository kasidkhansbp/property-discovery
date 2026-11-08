"""The SQLAlchemy declarative base every model inherits from.

No custom naming convention is set: the serving tables already exist (created by
the ingestion pipeline with Postgres-default constraint names like
``land_registry_sales_pkey`` and explicitly-named indexes like
``land_registry_sales_postcode_idx``). The models name those same objects
explicitly, so a database built fresh from the migrations matches a
pipeline-built one and Alembic autogenerate stays quiet.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All ORM models inherit from this. Import it when defining a new table."""
