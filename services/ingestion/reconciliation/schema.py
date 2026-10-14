"""Single source of truth for the ``property_uprn_mapping`` master table.

This is the reconciliation bridge: one row per decided (transaction_id, uprn)
relationship, plus a row for every transaction that found no UPRN and every
UPRN that has never been sold (see the coverage rules in utils.py). Describing
the four columns and the four ``match_type`` values once here keeps the DuckDB
projection, the table DDL, and the load SQL from drifting apart.
"""

from __future__ import annotations

# The served bridge table (named in data-platform-structure.md).
TARGET_TABLE = "property_uprn_mapping"

# The four match tiers that can land in `match_type`.
MATCH_EXACT = "EXACT"  # deterministic key hit — score 1.0
MATCH_FUZZY = "FUZZY"  # probabilistic string-similarity hit — fractional score
MATCH_UNMATCHED_LR = "UNMATCHED_LR"  # a sale with no UPRN — score 0.0
MATCH_UNMATCHED_UPRN = "UNMATCHED_UPRN"  # a UPRN never sold — score 0.0

# Column order shared by the master Parquet, the staging load, and the target.
MASTER_COLUMNS: list[str] = ["transaction_id", "uprn", "match_score", "match_type"]

# Postgres CREATE TABLE column list. transaction_id / uprn are both nullable so
# the table can carry UNMATCHED_LR (uprn NULL) and UNMATCHED_UPRN
# (transaction_id NULL) rows; uniqueness on transaction_id is enforced by a
# partial index (below), not here, because of those NULLs.
PG_DDL_COLS: str = (
    "transaction_id text,\n"
    "    uprn           text,\n"
    "    match_score    double precision NOT NULL DEFAULT 0.0,\n"
    "    match_type     text NOT NULL"
)
