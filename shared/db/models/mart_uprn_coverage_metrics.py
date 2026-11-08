"""Table for ``mart_uprn_coverage_metrics`` — the pre-aggregated coverage rollup.

One row per (constituent_country, county, district, postcode_prefix). It is
rebuilt wholesale each run (TRUNCATE + INSERT) and has no primary key — the group
columns can be NULL for junk postcodes — so it is a Core ``Table``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, Numeric, Table, Text

from ..base import Base

mart_uprn_coverage_metrics = Table(
    "mart_uprn_coverage_metrics",
    Base.metadata,
    # The four grouping dimensions (one row per distinct combination).
    Column("constituent_country", Text, info={"pg_type": "text", "group": True}),
    Column("county", Text, info={"pg_type": "text", "group": True}),
    Column("district", Text, info={"pg_type": "text", "group": True}),
    Column("postcode_prefix", Text, info={"pg_type": "text", "group": True}),
    Column("total_land_registry_sales", BigInteger, info={"pg_type": "bigint"}),
    Column("matched_uprn_count", BigInteger, info={"pg_type": "bigint"}),
    Column("coverage_percentage", Numeric, info={"pg_type": "numeric"}),
)
