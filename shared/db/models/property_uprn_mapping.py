"""Table for ``property_uprn_mapping`` — the reconciliation bridge.

One row per decided (transaction_id, uprn) relationship, plus coverage rows for
unmatched sales and never-sold UPRNs. It has no primary key: ``transaction_id`` /
``uprn`` are both nullable (to carry ``UNMATCHED_LR`` / ``UNMATCHED_UPRN`` rows),
and transaction_id uniqueness is enforced by a *partial* unique index. Because it
has no PK it is a Core ``Table`` rather than an ORM class. Columns are tagged
``role`` = ``match`` | ``enrichment`` so the reconciliation schema can derive its
column lists from here.
"""

from __future__ import annotations

from sqlalchemy import Column, Double, Index, Table, Text, text

from ..base import Base

_MATCH = {"role": "match"}
_ENRICH = {"role": "enrichment"}

property_uprn_mapping = Table(
    "property_uprn_mapping",
    Base.metadata,
    # match columns (intrinsic to the match decision)
    Column("transaction_id", Text, info={"pg_type": "text", **_MATCH}),
    Column("uprn", Text, info={"pg_type": "text", **_MATCH}),
    Column(
        "match_score",
        Double,
        nullable=False,
        server_default=text("0.0"),
        info={"pg_type": "double precision NOT NULL DEFAULT 0.0", **_MATCH},
    ),
    Column(
        "match_type",
        Text,
        nullable=False,
        info={"pg_type": "text NOT NULL", **_MATCH},
    ),
    # enrichment columns (joined on after matching; all nullable)
    Column("latitude", Double, info={"pg_type": "double precision", **_ENRICH}),
    Column("longitude", Double, info={"pg_type": "double precision", **_ENRICH}),
    Column("x_coordinate", Double, info={"pg_type": "double precision", **_ENRICH}),
    Column("y_coordinate", Double, info={"pg_type": "double precision", **_ENRICH}),
    Column("postcode", Text, info={"pg_type": "text", **_ENRICH}),
    Column("district", Text, info={"pg_type": "text", **_ENRICH}),
    Column("county", Text, info={"pg_type": "text", **_ENRICH}),
    Column("constituent_country", Text, info={"pg_type": "text", **_ENRICH}),
    # Partial unique index: transaction_id unique among rows that have one.
    Index(
        "property_uprn_mapping_txn_uidx",
        "transaction_id",
        unique=True,
        postgresql_where=text("transaction_id IS NOT NULL"),
    ),
    Index("property_uprn_mapping_uprn_idx", "uprn"),
)
