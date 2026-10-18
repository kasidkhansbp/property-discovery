"""Single source of truth for the ``property_uprn_mapping`` master table.

This is the reconciliation bridge: one row per decided (transaction_id, uprn)
relationship, plus a row for every transaction that found no UPRN and every
UPRN that has never been sold (see the coverage rules in utils.py). Describing
the columns and the four ``match_type`` values once here keeps the DuckDB
projection, the table DDL, and the load SQL from drifting apart.

The columns fall into two groups:

  * **match columns** — produced by the match step itself (``transaction_id``,
    ``uprn``, ``match_score``, ``match_type``). These are *intrinsic to the
    match decision*; only the reconciliation build knows them (EXACT vs FUZZY
    cannot be reconstructed from another table).
  * **enrichment columns** — joined on *after* matching, all keyed by ``uprn``:
    the coordinates (``latitude``/``longitude``/``x_coordinate``/``y_coordinate``)
    from ``os_open_uprn``, and ``postcode`` + ``constituent_country`` (from EPC's
    ``country``) from ``epc_domestic_certificates`` (latest certificate per UPRN).
    ``district`` and ``county`` have no clean EPC source — EPC carries only a
    local-authority label and MHCLG dropped ``county`` — so they are carried as
    NULL placeholders in this first (EPC) pass and filled later from
    ``land_registry_sales`` (which has a real ``district`` and ``county``, keyed
    by ``transaction_id``).
"""

from __future__ import annotations

# The served bridge table (named in data-platform-structure.md).
TARGET_TABLE = "property_uprn_mapping"

# The four match tiers that can land in `match_type`.
MATCH_EXACT = "EXACT"  # deterministic key hit — score 1.0
MATCH_FUZZY = "FUZZY"  # probabilistic string-similarity hit — fractional score
MATCH_UNMATCHED_LR = "UNMATCHED_LR"  # a sale with no UPRN — score 0.0
MATCH_UNMATCHED_UPRN = "UNMATCHED_UPRN"  # a UPRN never sold — score 0.0

# Columns the match step emits, in order. One row of these per decided
# relationship or coverage row; see utils.build_master_parquet.
MATCH_COLUMNS: list[str] = ["transaction_id", "uprn", "match_score", "match_type"]

# Enrichment columns, joined on after the match, with the Postgres DDL type for
# each. Order matters: it defines the tail of MASTER_COLUMNS and the DDL below.
# All are nullable — a row only carries the enrichment that applies to it (an
# UNMATCHED_LR row has no uprn, so no coordinates/EPC fields).
ENRICHMENT_COLUMN_TYPES: dict[str, str] = {
    "latitude": "double precision",  # os_open_uprn, keyed by uprn (WGS84)
    "longitude": "double precision",  # os_open_uprn, keyed by uprn (WGS84)
    "x_coordinate": "double precision",  # os_open_uprn — BNG easting (EPSG:27700)
    "y_coordinate": "double precision",  # os_open_uprn — BNG northing (EPSG:27700)
    "postcode": "text",  # EPC, keyed by uprn (latest certificate)
    "district": "text",  # land_registry_sales (by transaction_id) — later pass
    "county": "text",  # land_registry_sales (by transaction_id) — later pass
    "constituent_country": "text",  # EPC.country, keyed by uprn
}
ENRICHMENT_COLUMNS: list[str] = list(ENRICHMENT_COLUMN_TYPES)

# Full column order shared by the master Parquet, the staging load, and the
# target table: the match columns first, then the enrichment columns.
MASTER_COLUMNS: list[str] = MATCH_COLUMNS + ENRICHMENT_COLUMNS

# Postgres CREATE TABLE column list. transaction_id / uprn are both nullable so
# the table can carry UNMATCHED_LR (uprn NULL) and UNMATCHED_UPRN
# (transaction_id NULL) rows; uniqueness on transaction_id is enforced by a
# partial index (below), not here, because of those NULLs. The enrichment
# columns are appended from ENRICHMENT_COLUMN_TYPES so they stay in lock-step
# with MASTER_COLUMNS.
PG_DDL_COLS: str = (
    "transaction_id      text,\n"
    "    uprn                text,\n"
    "    match_score         double precision NOT NULL DEFAULT 0.0,\n"
    "    match_type          text NOT NULL,\n    "
    + ",\n    ".join(f"{name:<19} {ddl}" for name, ddl in ENRICHMENT_COLUMN_TYPES.items())
)
