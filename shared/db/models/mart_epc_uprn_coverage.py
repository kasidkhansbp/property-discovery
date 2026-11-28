"""Table for ``mart_epc_uprn_coverage`` — EPC UPRN -> transaction coverage.

One row per (property_type, built_form, tenure, uprn_source,
constituent_country, postcode_prefix): how many EPC UPRNs fall in that group and
how many of them are linked to at least one Land Registry sale. Built by the
reconciliation service (``build_epc_uprn_coverage``), which rebuilds it
wholesale each month with a load-and-swap. No primary key (postcode_prefix can
be NULL), so it is a Core ``Table``.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, Index, Numeric, Table, Text

from ..base import Base

mart_epc_uprn_coverage = Table(
    "mart_epc_uprn_coverage",
    Base.metadata,
    # The six grouping dimensions; property_type is the headline split.
    Column("property_type", Text, info={"pg_type": "text", "group": True}),
    Column("built_form", Text, info={"pg_type": "text", "group": True}),
    Column("tenure", Text, info={"pg_type": "text", "group": True}),
    Column("uprn_source", Text, info={"pg_type": "text", "group": True}),
    Column("constituent_country", Text, info={"pg_type": "text", "group": True}),
    Column("postcode_prefix", Text, info={"pg_type": "text", "group": True}),
    Column("epc_uprns", BigInteger, info={"pg_type": "bigint"}),
    Column("uprns_with_transaction", BigInteger, info={"pg_type": "bigint"}),
    Column("uprns_without_transaction", BigInteger, info={"pg_type": "bigint"}),
    Column("coverage_percentage", Numeric, info={"pg_type": "numeric"}),
    Column("built_at", DateTime(timezone=True), info={"pg_type": "timestamptz"}),
    # The pipeline recreates this index on every rebuild (see utils.py).
    Index("mart_epc_uprn_coverage_type_idx", "property_type"),
)
