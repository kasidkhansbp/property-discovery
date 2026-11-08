"""Shared library: the database model, connection, and migrations.

This package is the single source of truth for the serving-database schema. Both
the ingestion jobs (``services/``) and the read API (``gateway/``) import the
table/column definitions from here, so the two can never drift, and Alembic
(``shared/migrations``) version-controls the schema itself.
"""
