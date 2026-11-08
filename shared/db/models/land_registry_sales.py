"""Model for ``land_registry_sales`` — HM Land Registry Price Paid Data.

Single source of truth for the table's columns. Each column carries, in its
``info``, the DuckDB read type and cleaning rule the ingestion pipeline needs;
``services.jobs.ingestion.land_registry.schema`` builds its ``PPD_SCHEMA`` from
this model, so the DuckDB read, the DDL, and the upsert all derive from here.
"""

from __future__ import annotations

from sqlalchemy import Index

from ..base import Base
from ..columns import pg_column


class LandRegistrySales(Base):
    __tablename__ = "land_registry_sales"

    # PPD "Transaction unique identifier" — the natural PK.
    transaction_id = pg_column("text PRIMARY KEY", csv_type="VARCHAR")
    price = pg_column("bigint", csv_type="BIGINT")
    transfer_date = pg_column("date", csv_type="TIMESTAMP")
    postcode = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    property_type = pg_column("text", csv_type="VARCHAR")
    old_new = pg_column("text", csv_type="VARCHAR")
    duration = pg_column("text", csv_type="VARCHAR")
    paon = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    saon = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    street = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    locality = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    town_city = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    district = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    county = pg_column("text", csv_type="VARCHAR", nullif_empty=True)
    ppd_category = pg_column("text", csv_type="VARCHAR")
    # A=add, C=change, D=delete (monthly); always A in complete.
    record_status = pg_column("text", csv_type="VARCHAR")

    __table_args__ = (
        # The pipeline creates this index by this exact name; match it so a
        # migration-built DB is identical to a pipeline-built one.
        Index("land_registry_sales_postcode_idx", "postcode"),
    )
