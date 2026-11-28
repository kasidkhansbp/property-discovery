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


# --------------------------------------------------------------------------- #
# Downstream mart: pre-aggregated UPRN coverage metrics.                      #
# --------------------------------------------------------------------------- #
# A small, dashboard-facing rollup. The bridge is ~40M rows, so a dashboard that
# recomputes coverage on every page load would re-scan it each time; this mart
# pre-aggregates coverage down to one row per (constituent_country, county,
# district, postcode_prefix) so the dashboard reads a tiny, already-grouped
# table instead.
#
# The geography is taken from ``land_registry_sales`` (keyed by transaction_id),
# NOT from the bridge's enrichment columns. Those enrichment columns (postcode,
# constituent_country) come from EPC and so only exist on *matched* rows — using
# them would funnel every unmatched sale into a NULL bucket and make per-area
# coverage read as a meaningless 0%/100% split. The sale's own postcode /
# district / county exist for every transaction, matched or not, so grouping on
# them yields true blended coverage per area. The bridge is joined on only for
# the matched flag (``uprn IS NOT NULL``). (The reconciliation brief refers to
# the bridge as ``fact_transaction_uprn_mapping``; here that is TARGET_TABLE,
# ``property_uprn_mapping``.)
MART_TABLE = "mart_uprn_coverage_metrics"

# The per-sale source of the grouping geography (owned by the land_registry
# service). Carries one row per transaction_id with postcode/district/county.
LR_SALES_TABLE = "land_registry_sales"

# Mart columns with their Postgres DDL types, in output order. ``text`` is the
# Postgres idiom for VARCHAR (matching this table's other string columns);
# ``numeric`` holds the 2-dp coverage percentage exactly.
MART_COLUMN_TYPES: dict[str, str] = {
    "constituent_country": "text",
    "county": "text",
    "district": "text",
    "postcode_prefix": "text",  # outward code, e.g. 'EX4' / 'CF36'
    "total_land_registry_sales": "bigint",  # transactions in the group
    "matched_uprn_count": "bigint",  # of those, how many carry a UPRN
    "coverage_percentage": "numeric",  # matched / total * 100, rounded 2 dp
}
MART_COLUMNS: list[str] = list(MART_COLUMN_TYPES)
MART_GROUP_COLUMNS: list[str] = [
    "constituent_country",
    "county",
    "district",
    "postcode_prefix",
]

MART_PG_DDL_COLS: str = ",\n    ".join(
    f"{name:<26} {ddl}" for name, ddl in MART_COLUMN_TYPES.items()
)


# Normalised postcode: upper-cased with all whitespace stripped ("ex4 6pr" ->
# "EX46PR"). Both derived expressions below build on this, so a missing or
# doubled space never changes the result. Uses only functions DuckDB and
# Postgres share, so the mart SELECT runs unchanged in tests (DuckDB) and
# production (Postgres).
def _norm_postcode_sql(col: str) -> str:
    return f"regexp_replace(upper({col}), '\\s', '', 'g')"


def postcode_prefix_sql(col: str = "postcode") -> str:
    """SQL expression extracting a UK postcode's outward code from ``col``.

    The outward code is the postcode with its final three characters (the inward
    code — always ``digit + 2 letters``) removed: 'EX4 6PR' -> 'EX4',
    'CF36 1AB' -> 'CF36'. We normalise first, then take all but the last three
    characters. Anything shorter than four characters once stripped isn't a real
    postcode, so it yields NULL rather than a garbage prefix.
    """
    norm = _norm_postcode_sql(col)
    return f"CASE WHEN length({norm}) >= 4 THEN left({norm}, length({norm}) - 3) END"


# Land Registry PPD covers England & Wales only, so a sale's country is one of
# those two — and it can be read from the postcode area (the leading letters of
# the outward code). These are the postcode areas that are wholly/predominantly
# Welsh; every other area is treated as England. Border areas (CH, SY, HR, LD's
# edges) are approximate at this granularity — good enough for a coverage
# dashboard, and noted so no one mistakes it for an authoritative boundary.
WELSH_POSTCODE_AREAS: tuple[str, ...] = ("CF", "LD", "LL", "NP", "SA")


def constituent_country_sql(col: str = "postcode") -> str:
    """SQL expression mapping a sale's postcode to 'England' / 'Wales' / NULL.

    The postcode *area* is the leading alphabetic run of the outward code, got
    by dropping everything from the first digit onward ('CF14' -> 'CF',
    'SW1A' -> 'SW'). It yields NULL for the same too-short/missing postcodes that
    ``postcode_prefix_sql`` nulls out, so country and prefix stay NULL together.
    """
    norm = _norm_postcode_sql(col)
    area = f"regexp_replace({norm}, '[0-9].*$', '')"
    welsh = ", ".join(f"'{a}'" for a in WELSH_POSTCODE_AREAS)
    return (
        f"CASE WHEN length({norm}) < 4 THEN NULL "
        f"WHEN {area} IN ({welsh}) THEN 'Wales' "
        f"ELSE 'England' END"
    )


# The single SELECT that builds the mart. Geography comes from the sale itself
# (land_registry_sales, one row per transaction_id), so every sale — matched or
# not — lands in its real postcode prefix / district / county. The bridge is
# LEFT-JOINed on transaction_id purely to read the matched UPRN: ``m.uprn`` is
# non-NULL exactly for matched sales, NULL for UNMATCHED_LR rows and for any sale
# the bridge hasn't covered yet, so ``count(m.uprn)`` is the matched count and
# ``count(*)`` the total. Both transaction_id columns are unique (LR's PK, the
# bridge's partial unique index), so the join never fans a sale out; the bridge's
# UNMATCHED_UPRN rows (transaction_id NULL) simply never join. count(*) over a
# group is always >= 1, so the ratio never divides by zero. GROUP BY is
# positional (1..4) to avoid repeating the derived expressions.
COVERAGE_METRICS_SELECT: str = f"""
SELECT
    {constituent_country_sql("lr.postcode")} AS constituent_country,
    lr.county,
    lr.district,
    {postcode_prefix_sql("lr.postcode")} AS postcode_prefix,
    count(*)                                   AS total_land_registry_sales,
    count(m.uprn)                              AS matched_uprn_count,
    round(count(m.uprn) * 100.0 / count(*), 2) AS coverage_percentage
FROM {LR_SALES_TABLE} lr
LEFT JOIN {TARGET_TABLE} m ON m.transaction_id = lr.transaction_id
GROUP BY 1, 2, 3, 4
""".strip()


# --------------------------------------------------------------------------- #
# Downstream mart: EPC UPRN -> transaction coverage, by property type.        #
# --------------------------------------------------------------------------- #
# The opposite direction to mart_uprn_coverage_metrics. That mart asks "of the
# Land Registry sales, how many found a UPRN?"; this one asks "of the UPRNs EPC
# knows about, how many have at least one sale linked in the bridge?" — and its
# headline split is the property type (House / Flat / Maisonette / Bungalow /
# Park home).
#
# Each EPC UPRN is described by its LATEST certificate (lodgement_date, then
# certificate_number as the tie-break — the same rule build_properties.sql
# uses), so a UPRN is counted exactly once, under one property type. A UPRN
# counts as "with transaction" when the bridge holds any row for it with a
# non-NULL transaction_id (EXACT or FUZZY); UNMATCHED_UPRN rows, and UPRNs the
# bridge hasn't seen at all, count as "without".
#
# It reads epc_domestic_certificates directly rather than the `properties`
# table, because `properties` has no monthly refresh yet — reading it would
# freeze the attribute side of the mart at whenever it was last rebuilt.
#
# Secondary dimensions (built form, tenure, how the UPRN got onto the cert,
# country, postcode prefix) are kept so the dashboard can drill into a type —
# e.g. unsold flats that are owner-occupied, or whose UPRN was address-matched
# rather than entered by the assessor. NULL / blank attribute values are folded
# into 'Unknown' so every row is filterable, and tenure is lower-cased because
# EPC records it in two casings ('rented (social)' vs 'Rented (social)') — which
# also merges a blank tenure into EPC's own 'unknown' value.
EPC_COVERAGE_MART_TABLE = "mart_epc_uprn_coverage"

# Owned by the epc service; one row per certificate.
EPC_CERTS_TABLE = "epc_domestic_certificates"

EPC_COVERAGE_COLUMN_TYPES: dict[str, str] = {
    "property_type": "text",  # House / Flat / Maisonette / Bungalow / Park home
    "built_form": "text",  # Detached / Semi-Detached / Mid-Terrace / ...
    "tenure": "text",  # owner-occupied / rented (social) / rented (private) / ...
    "uprn_source": "text",  # 'Energy Assessor' or 'Address Matched'
    "constituent_country": "text",  # EPC country: England / Wales
    "postcode_prefix": "text",  # outward code, e.g. 'EX4' / 'CF36'
    "epc_uprns": "bigint",  # distinct EPC UPRNs in the group
    "uprns_with_transaction": "bigint",  # of those, linked to >= 1 sale
    "uprns_without_transaction": "bigint",  # epc_uprns - uprns_with_transaction
    "coverage_percentage": "numeric",  # with / total * 100, rounded 2 dp
    "built_at": "timestamptz",  # when this snapshot was built (same on every row)
}
EPC_COVERAGE_COLUMNS: list[str] = list(EPC_COVERAGE_COLUMN_TYPES)
EPC_COVERAGE_GROUP_COLUMNS: list[str] = [
    "property_type",
    "built_form",
    "tenure",
    "uprn_source",
    "constituent_country",
    "postcode_prefix",
]

EPC_COVERAGE_PG_DDL_COLS: str = ",\n    ".join(
    f"{name:<26} {ddl}" for name, ddl in EPC_COVERAGE_COLUMN_TYPES.items()
)

# The value NULL / blank attributes are folded into.
EPC_COVERAGE_UNKNOWN = "Unknown"


def _unknown_if_blank_sql(expr: str) -> str:
    return f"coalesce(nullif(trim({expr}), ''), '{EPC_COVERAGE_UNKNOWN}')"


# The single SELECT that builds the mart. Written in the SQL subset DuckDB and
# Postgres share (DISTINCT ON, NULLS LAST, regexp_replace ... 'g') so the tests
# can run it unchanged on DuckDB.
#
#   * epc_latest — one row per UPRN: its latest certificate's attributes.
#   * sold       — distinct UPRNs the bridge links to at least one sale. DISTINCT
#                  matters: a UPRN sold five times has five bridge rows, and the
#                  LEFT JOIN must not fan it out.
#
# count(*) per group is always >= 1, so the ratio never divides by zero. GROUP BY
# is positional (1..6) to avoid repeating the derived expressions. built_at is the
# same now() on every row (one transaction), so the dashboard can show the date
# of the snapshot it is reading — Postgres records no table-creation time.
EPC_COVERAGE_SELECT: str = f"""
WITH epc_latest AS (
    SELECT DISTINCT ON (uprn)
           uprn, property_type, built_form, tenure, uprn_source, country, postcode
    FROM {EPC_CERTS_TABLE}
    WHERE uprn IS NOT NULL AND trim(uprn) <> ''
    ORDER BY uprn, lodgement_date DESC NULLS LAST, certificate_number DESC
),
sold AS (
    SELECT DISTINCT uprn
    FROM {TARGET_TABLE}
    WHERE transaction_id IS NOT NULL AND uprn IS NOT NULL
)
SELECT
    {_unknown_if_blank_sql("e.property_type")}  AS property_type,
    {_unknown_if_blank_sql("e.built_form")}     AS built_form,
    lower({_unknown_if_blank_sql("e.tenure")})  AS tenure,
    {_unknown_if_blank_sql("e.uprn_source")}    AS uprn_source,
    {_unknown_if_blank_sql("e.country")}        AS constituent_country,
    {postcode_prefix_sql("e.postcode")}         AS postcode_prefix,
    count(*)                                    AS epc_uprns,
    count(s.uprn)                               AS uprns_with_transaction,
    count(*) - count(s.uprn)                    AS uprns_without_transaction,
    round(count(s.uprn) * 100.0 / count(*), 2)  AS coverage_percentage,
    now()                                       AS built_at
FROM epc_latest e
LEFT JOIN sold s ON s.uprn = e.uprn
GROUP BY 1, 2, 3, 4, 5, 6
""".strip()

# Certificates that carry no UPRN at all can't be counted per UPRN, so they are
# reported once, as run metadata, rather than as mart rows.
EPC_CERTS_WITHOUT_UPRN_SELECT: str = (
    f"SELECT count(*) FROM {EPC_CERTS_TABLE} "
    "WHERE uprn IS NULL OR trim(uprn) = ''"
)
