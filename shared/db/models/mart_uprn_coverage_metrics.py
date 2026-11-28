"""Table for ``mart_uprn_coverage_metrics`` — the pre-aggregated coverage rollup.

One row per (property_type, constituent_country, county, district,
postcode_prefix). It is rebuilt wholesale each run (load-and-swap) and has no
primary key — the geography columns can be NULL for junk postcodes — so it is a
Core ``Table``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Index, Numeric, Table, Text

from ..base import Base

mart_uprn_coverage_metrics = Table(
    "mart_uprn_coverage_metrics",
    Base.metadata,
    # The five grouping dimensions (one row per distinct combination);
    # property_type is the dashboard's headline split.
    Column("property_type", Text, info={"pg_type": "text", "group": True}),
    Column("constituent_country", Text, info={"pg_type": "text", "group": True}),
    Column("county", Text, info={"pg_type": "text", "group": True}),
    Column("district", Text, info={"pg_type": "text", "group": True}),
    Column("postcode_prefix", Text, info={"pg_type": "text", "group": True}),
    Column("total_land_registry_sales", BigInteger, info={"pg_type": "bigint"}),
    Column("matched_uprn_count", BigInteger, info={"pg_type": "bigint"}),
    Column("coverage_percentage", Numeric, info={"pg_type": "numeric"}),
    Column("built_at", DateTime(timezone=True), info={"pg_type": "timestamptz"}),
    # The pipeline recreates this index on every rebuild (see utils.py).
    Index("mart_uprn_coverage_metrics_type_idx", "property_type"),
)
