"""Shared normalize / match / load logic for the UPRN reconciliation pipeline.

The pipeline runs in three sequential stages, each a thin Dagster asset in
assets.py wrapping one function here:

  1. ``normalize_sources``    — read land_registry_sales + epc_domestic_certificates
                                from Postgres, standardise the join keys, and land
                                two clean Parquet files in R2 (Step A).
  2. ``build_master_parquet`` — exact pass, then a probabilistic fallback for the
                                leftovers, then full-coverage + cardinality
                                assembly, written as one master Parquet in R2
                                (Steps B, C, D).
  3. ``load_master``          — upsert the master Parquet into
                                ``property_uprn_mapping`` in Postgres.

Everything heavy stays in DuckDB: it reads the source tables over its postgres
extension, reads/writes Parquet in R2 over httpfs, and does the exact join and
the blocked fuzzy join in-engine. The probabilistic scorer is DuckDB's built-in
``jaro_winkler_similarity`` (0..1, computed in vectorised C++), so the similarity
is evaluated right where the candidate pairs live — no Python UDF, no dragging
millions of rows out of the engine. (rapidfuzz would do the same job in Python;
the native function is the faster, dependency-free equivalent the brief's "e.g."
left open.)

Match design:
  * Keys are normalised to a single ``addr_key`` per side — Land Registry's
    PAON + Street concatenated, EPC's address1 — both whitespace-collapsed and
    upper-cased, alongside a whitespace-stripped, upper-cased ``norm_postcode``.
  * EXACT  = equal (norm_postcode, addr_key). FUZZY = best Jaro-Winkler over
    candidates sharing a postcode, kept only above ``DEFAULT_FUZZY_THRESHOLD``.
  * Cardinality is enforced by keeping a single best UPRN per transaction_id
    (a UPRN may still recur across many transactions).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import duckdb
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource
from .schema import (
    ENRICHMENT_COLUMN_TYPES,
    MASTER_COLUMNS,
    MATCH_COLUMNS,
    MATCH_EXACT,
    MATCH_FUZZY,
    MATCH_UNMATCHED_LR,
    MATCH_UNMATCHED_UPRN,
    PG_DDL_COLS,
    TARGET_TABLE,
)

# Source tables (loaded by the land_registry and epc services, respectively).
LR_TABLE = "land_registry_sales"
EPC_TABLE = "epc_domestic_certificates"

# Reference table for coordinate enrichment (loaded by the os_open_uprn service).
# Its uprn PK is a bigint; property_uprn_mapping.uprn is text, so the join casts.
OS_OPEN_UPRN_TABLE = "os_open_uprn"

STAGING_TABLE = "property_uprn_mapping_staging"

# Below this Jaro-Winkler similarity (0..1) a fuzzy candidate is discarded and
# the transaction is left UNMATCHED_LR. 0.90 keeps only near-identical address
# strings within a shared postcode; tune per observed precision.
DEFAULT_FUZZY_THRESHOLD = 0.90


@contextmanager
def duckdb_con(r2: R2Resource) -> Iterator[duckdb.DuckDBPyConnection]:
    """A DuckDB connection pre-configured for this R2 bucket, auto-closed.

    Same helper as the other services: open, point at R2 over httpfs, yield,
    and always close on exit — even if a query raises.
    """
    con = duckdb.connect()
    try:
        r2.configure_duckdb(con)
        # Stream a live progress bar for long-running queries. The exact/fuzzy
        # joins and the big COPYs are single blocking statements, so without this
        # there's nothing to watch until they finish; with it, DuckDB prints a
        # percentage bar that Dagster captures into the step's stdout/compute log.
        # progress_bar_time=0 shows it immediately rather than after a delay.
        con.execute("SET enable_progress_bar = true;")
        con.execute("SET enable_progress_bar_print = true;")
        con.execute("SET progress_bar_time = 0;")
        yield con
    finally:
        con.close()


def ensure_target_table(postgres: PostgresResource) -> None:
    """Create ``property_uprn_mapping`` (and its indexes) if it doesn't exist.

    Idempotent, and safe to call from both the build step (incremental runs read
    the existing table) and the load step. The partial unique index on
    ``transaction_id`` enforces the 1:1 transaction->UPRN cardinality at the DB
    level while still permitting the many NULL transaction_ids carried by the
    UNMATCHED_UPRN rows.
    """
    with postgres.connect() as conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (\n    {PG_DDL_COLS}\n);")
        # Self-heal a table created before the enrichment columns existed: add
        # any that are missing (nullable, so this is a metadata-only change even
        # on a 40M-row table — no rewrite). Adding the columns does NOT backfill
        # history; the incremental load's ON CONFLICT DO NOTHING protects
        # existing rows, so run scripts/backfill_property_uprn_mapping_enrichment.py
        # (or a full rebuild) once to populate the rows already in the table.
        for name, ddl in ENRICHMENT_COLUMN_TYPES.items():
            cur.execute(
                f"ALTER TABLE {TARGET_TABLE} ADD COLUMN IF NOT EXISTS {name} {ddl};"
            )
        cur.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {TARGET_TABLE}_txn_uidx "
            f"ON {TARGET_TABLE} (transaction_id) WHERE transaction_id IS NOT NULL;"
        )
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {TARGET_TABLE}_uprn_idx "
            f"ON {TARGET_TABLE} (uprn);"
        )
        conn.commit()


def _attach_pg(con: duckdb.DuckDBPyConnection, postgres: PostgresResource) -> None:
    """Attach the serving Postgres to a DuckDB connection as schema ``pg``."""
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{postgres.dsn}' AS pg (TYPE postgres);")


# --------------------------------------------------------------------------- #
# Step A: normalise both sources into clean Parquet (join keys only).         #
# --------------------------------------------------------------------------- #
# Postcode: drop ALL whitespace, upper-case ("SW1A 1AA" -> "SW1A1AA").
_NORM_POSTCODE = "upper(regexp_replace(coalesce({col}, ''), '\\s', '', 'g'))"
# Text key: upper-case, collapse internal whitespace runs to one space, trim.
_NORM_TEXT = "trim(regexp_replace(upper(coalesce({expr}, '')), '\\s+', ' ', 'g'))"


def normalize_sources(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    lr_key: str,
    epc_key: str,
) -> dict[str, str]:
    """Standardise the join keys on both datasets; write two Parquet files to R2.

    Land Registry contributes ``transaction_id`` plus a normalised postcode and
    an ``addr_key`` built from PAON + Street. EPC contributes ``uprn`` plus a
    normalised postcode and an ``addr_key`` built from address1 (EPC does not
    split house number from street, so address1 is the comparable line). Rows
    with no UPRN are dropped from the EPC side — they can neither be matched to
    nor stand in as an unmatched UPRN.
    """
    lr_postcode = _NORM_POSTCODE.format(col="postcode")
    lr_addr = _NORM_TEXT.format(expr="concat_ws(' ', paon, street)")
    epc_postcode = _NORM_POSTCODE.format(col="postcode")
    epc_addr = _NORM_TEXT.format(expr="address1")

    with duckdb_con(r2) as con:
        _attach_pg(con, postgres)
        context.log.info("Normalising %s -> %s", LR_TABLE, r2.s3_url(lr_key))
        con.execute(
            f"""
            COPY (
                SELECT
                    transaction_id,
                    {lr_postcode} AS norm_postcode,
                    {lr_addr}     AS addr_key
                FROM pg.{LR_TABLE}
            ) TO '{r2.s3_url(lr_key)}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
        )
        context.log.info("Normalising %s -> %s", EPC_TABLE, r2.s3_url(epc_key))
        con.execute(
            f"""
            COPY (
                SELECT
                    uprn,
                    {epc_postcode} AS norm_postcode,
                    {epc_addr}     AS addr_key
                FROM pg.{EPC_TABLE}
                WHERE uprn IS NOT NULL AND trim(uprn) <> ''
            ) TO '{r2.s3_url(epc_key)}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
        )
        # Cheap row counts (Parquet footers) to report how much landed.
        n_lr = con.execute(
            f"SELECT count(*) FROM read_parquet('{r2.s3_url(lr_key)}');"
        ).fetchone()[0]
        n_epc = con.execute(
            f"SELECT count(*) FROM read_parquet('{r2.s3_url(epc_key)}');"
        ).fetchone()[0]
        con.execute("DETACH pg;")

    context.log.info(
        "Wrote normalised Parquet: %s LR row(s), %s EPC row(s)", n_lr, n_epc
    )
    context.add_output_metadata(
        {"lr_rows": n_lr, "epc_rows": n_epc, "lr_key": lr_key, "epc_key": epc_key}
    )
    return {"lr": lr_key, "epc": epc_key}


# --------------------------------------------------------------------------- #
# Steps B/C/D: exact pass, fuzzy fallback, full-coverage assembly.            #
# --------------------------------------------------------------------------- #
# DuckDB's built-in normalised Jaro-Winkler (0..1), which rewards a shared
# prefix — exactly right for addresses that start with the same house number /
# name. Used in SQL below; no Python UDF needed.
_SIM = "jaro_winkler_similarity"


def build_master_parquet(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    lr_key: str,
    epc_key: str,
    master_key: str,
    *,
    incremental: bool,
    threshold: float = DEFAULT_FUZZY_THRESHOLD,
) -> str:
    """Produce the master reconciliation Parquet from the normalised sources.

    Stages, all within one DuckDB connection:
      * EXACT  — inner join on (norm_postcode, addr_key); one best UPRN per
        transaction (lowest UPRN as a stable tie-break), score 1.0.
      * FUZZY  — for transactions the exact pass missed, block on postcode, score
        every candidate with Jaro-Winkler, keep the single best per transaction
        above ``threshold``.
      * COVERAGE — add an UNMATCHED_LR row (uprn NULL, 0.0) for every remaining
        transaction, and an UNMATCHED_UPRN row (transaction_id NULL, 0.0) for
        every EPC UPRN that no transaction matched.

    Incremental runs honour "protect existing matches": transaction_ids already
    present in ``property_uprn_mapping`` are excluded from the LR scope entirely
    (not re-matched, not re-scored), and the UNMATCHED_UPRN set is computed
    against both this run's matches and the UPRNs already covered in the table.
    """
    with duckdb_con(r2) as con:
        # Load the normalised sources and derive the distinct EPC candidate set.
        con.execute(
            f"CREATE TABLE lr_all AS SELECT * FROM read_parquet('{r2.s3_url(lr_key)}');"
        )
        con.execute(
            f"CREATE TABLE epc AS SELECT * FROM read_parquet('{r2.s3_url(epc_key)}');"
        )
        con.execute(
            "CREATE TABLE epc_addr AS "
            "SELECT DISTINCT uprn, norm_postcode, addr_key FROM epc "
            "WHERE norm_postcode <> '' AND addr_key <> '';"
        )
        con.execute("CREATE TABLE epc_uprn AS SELECT DISTINCT uprn FROM epc;")

        # Scope the LR side and collect already-covered UPRNs for incremental.
        if incremental:
            ensure_target_table(postgres)
            _attach_pg(con, postgres)
            con.execute(
                "CREATE TABLE existing_txn AS "
                f"SELECT DISTINCT transaction_id FROM pg.{TARGET_TABLE} "
                "WHERE transaction_id IS NOT NULL;"
            )
            con.execute(
                "CREATE TABLE existing_uprn AS "
                f"SELECT DISTINCT uprn FROM pg.{TARGET_TABLE} WHERE uprn IS NOT NULL;"
            )
            con.execute("DETACH pg;")
            con.execute(
                "CREATE TABLE lr AS SELECT * FROM lr_all "
                "WHERE transaction_id NOT IN (SELECT transaction_id FROM existing_txn);"
            )
        else:
            con.execute("CREATE TABLE lr AS SELECT * FROM lr_all;")
            con.execute(
                "CREATE TABLE existing_uprn (uprn VARCHAR);"  # empty on a full build
            )

        new_lr = con.execute("SELECT count(*) FROM lr;").fetchone()[0]
        n_candidates = con.execute("SELECT count(*) FROM epc_addr;").fetchone()[0]
        context.log.info(
            "Reconciling %s transaction(s) in scope against %s EPC address candidate(s)",
            new_lr,
            n_candidates,
        )

        # Step B: EXACT. row_number keeps one UPRN per transaction (1:1).
        context.log.info("Step B: exact pass (deterministic key join)...")
        con.execute(
            f"""
            CREATE TABLE exact_matches AS
            SELECT transaction_id, uprn, 1.0 AS match_score, '{MATCH_EXACT}' AS match_type
            FROM (
                SELECT lr.transaction_id, e.uprn,
                       row_number() OVER (
                           PARTITION BY lr.transaction_id ORDER BY e.uprn
                       ) AS rn
                FROM lr
                JOIN epc_addr e
                  ON e.norm_postcode = lr.norm_postcode
                 AND e.addr_key = lr.addr_key
                WHERE lr.norm_postcode <> '' AND lr.addr_key <> ''
            )
            WHERE rn = 1;
            """
        )

        n_exact_done = con.execute("SELECT count(*) FROM exact_matches;").fetchone()[0]
        context.log.info(
            "Step B done: %s exact match(es). Step C: fuzzy fallback on the rest...",
            n_exact_done,
        )

        # Step C: FUZZY fallback over the exact-pass leftovers, blocked on
        # postcode. QUALIFY keeps the single best candidate per transaction;
        # the outer filter drops it if even the best is below threshold.
        con.execute(
            f"""
            CREATE TABLE fuzzy_matches AS
            SELECT transaction_id, uprn, match_score, '{MATCH_FUZZY}' AS match_type
            FROM (
                SELECT u.transaction_id, e.uprn,
                       round({_SIM}(u.addr_key, e.addr_key), 4) AS match_score
                FROM lr u
                JOIN epc_addr e ON e.norm_postcode = u.norm_postcode
                WHERE u.norm_postcode <> '' AND u.addr_key <> ''
                  AND u.transaction_id NOT IN (
                      SELECT transaction_id FROM exact_matches
                  )
                QUALIFY row_number() OVER (
                    PARTITION BY u.transaction_id
                    ORDER BY {_SIM}(u.addr_key, e.addr_key) DESC, e.uprn
                ) = 1
            )
            WHERE match_score >= {threshold};
            """
        )

        # Everything decided this run (one row per matched transaction_id).
        con.execute(
            "CREATE TABLE matched AS "
            "SELECT * FROM exact_matches UNION ALL SELECT * FROM fuzzy_matches;"
        )

        context.log.info("Step D: assembling full coverage (unmatched LR + UPRNs)...")

        # Step D: full coverage + cardinality.
        # (i) Every in-scope transaction with no match -> UNMATCHED_LR.
        con.execute(
            f"""
            CREATE TABLE unmatched_lr AS
            SELECT transaction_id,
                   CAST(NULL AS VARCHAR) AS uprn,
                   0.0 AS match_score,
                   '{MATCH_UNMATCHED_LR}' AS match_type
            FROM lr
            WHERE transaction_id NOT IN (SELECT transaction_id FROM matched);
            """
        )
        # (ii) Every EPC UPRN not covered by this run OR already in the table
        #      -> UNMATCHED_UPRN (one row per such UPRN).
        con.execute(
            f"""
            CREATE TABLE unmatched_uprn AS
            SELECT CAST(NULL AS VARCHAR) AS transaction_id,
                   uprn,
                   0.0 AS match_score,
                   '{MATCH_UNMATCHED_UPRN}' AS match_type
            FROM epc_uprn
            WHERE uprn NOT IN (SELECT uprn FROM matched WHERE uprn IS NOT NULL)
              AND uprn NOT IN (SELECT uprn FROM existing_uprn)
            """
        )

        # Assemble the match columns for every covered row, then enrich. Keeping
        # the coverage union and the enrichment join in separate steps means the
        # match logic above is untouched — enrichment is a pure LEFT-JOIN tail.
        match_cols = ", ".join(MATCH_COLUMNS)
        con.execute(
            f"""
            CREATE TABLE coverage AS
            SELECT {match_cols} FROM matched
            UNION ALL SELECT {match_cols} FROM unmatched_lr
            UNION ALL SELECT {match_cols} FROM unmatched_uprn;
            """
        )

        # Enrichment: everything keyed by uprn. Coordinates come from
        # os_open_uprn (its PK is a bigint, so cast; TRY_CAST yields NULL for any
        # non-numeric uprn rather than erroring). postcode + constituent_country
        # come from EPC, deduplicated to the latest certificate per uprn (a uprn
        # can hold several). district/county have no clean EPC source and are
        # written as typed NULLs here, to be filled from land_registry_sales in a
        # later pass. All joins are LEFT, so an UNMATCHED_LR row (no uprn) simply
        # keeps NULL enrichment.
        _attach_pg(con, postgres)
        con.execute(
            f"""
            COPY (
                SELECT
                    c.transaction_id,
                    c.uprn,
                    c.match_score,
                    c.match_type,
                    o.latitude,
                    o.longitude,
                    o.x_coordinate,
                    o.y_coordinate,
                    e.postcode,
                    CAST(NULL AS VARCHAR) AS district,
                    CAST(NULL AS VARCHAR) AS county,
                    e.country AS constituent_country
                FROM coverage c
                LEFT JOIN pg.{OS_OPEN_UPRN_TABLE} o
                       ON o.uprn = TRY_CAST(c.uprn AS BIGINT)
                LEFT JOIN (
                    SELECT uprn, postcode, country FROM (
                        SELECT uprn, postcode, country,
                               row_number() OVER (
                                   PARTITION BY uprn
                                   ORDER BY lodgement_date DESC NULLS LAST,
                                            inspection_date DESC NULLS LAST,
                                            certificate_number
                               ) AS rn
                        FROM pg.{EPC_TABLE}
                        WHERE uprn IS NOT NULL AND trim(uprn) <> ''
                    ) WHERE rn = 1
                ) e ON e.uprn = c.uprn
            ) TO '{r2.s3_url(master_key)}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
        )
        con.execute("DETACH pg;")

        n_exact, n_fuzzy, n_unmatched_lr, n_unmatched_uprn = con.execute(
            "SELECT (SELECT count(*) FROM exact_matches),"
            "       (SELECT count(*) FROM fuzzy_matches),"
            "       (SELECT count(*) FROM unmatched_lr),"
            "       (SELECT count(*) FROM unmatched_uprn);"
        ).fetchone()

    context.log.info(
        "Master Parquet %s: %s exact, %s fuzzy, %s unmatched_lr, %s unmatched_uprn",
        master_key,
        n_exact,
        n_fuzzy,
        n_unmatched_lr,
        n_unmatched_uprn,
    )
    # Surface the outcome as structured metadata on the asset, so the Dagster UI
    # shows per-run match counts and the match rate without digging through logs.
    matched = n_exact + n_fuzzy
    context.add_output_metadata(
        {
            "transactions_in_scope": new_lr,
            "exact_matches": n_exact,
            "fuzzy_matches": n_fuzzy,
            "unmatched_lr": n_unmatched_lr,
            "unmatched_uprn": n_unmatched_uprn,
            "match_rate": (matched / new_lr) if new_lr else 0.0,
            "master_key": master_key,
        }
    )
    return master_key


# --------------------------------------------------------------------------- #
# Load: master Parquet -> property_uprn_mapping.                              #
# --------------------------------------------------------------------------- #
def load_master(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    master_key: str,
    *,
    incremental: bool,
) -> None:
    """Load the master Parquet into ``property_uprn_mapping``.

    Full build: truncate and replace the whole table.

    Incremental: INSERT the transaction-bearing rows with ``ON CONFLICT ... DO
    NOTHING`` so transaction_ids already decided are never overwritten (protect
    existing matches), then replace the UNMATCHED_UPRN rows wholesale — the build
    step recomputed that set against the full coverage, so a UPRN that has just
    gained its first sale correctly drops out of it.
    """
    ensure_target_table(postgres)
    cols = ", ".join(MASTER_COLUMNS)

    # Fresh staging table shaped like the target.
    with postgres.connect() as conn, conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        cur.execute(
            f"CREATE TABLE {STAGING_TABLE} (LIKE {TARGET_TABLE} INCLUDING DEFAULTS);"
        )
        conn.commit()

    # Bulk-load the Parquet from R2 straight into staging via DuckDB's postgres
    # extension — no local files, no row-by-row Python.
    with duckdb_con(r2) as con:
        _attach_pg(con, postgres)
        context.log.info("Bulk-loading %s into staging", master_key)
        con.execute(
            f"INSERT INTO pg.{STAGING_TABLE} ({cols}) "
            f"SELECT {cols} FROM read_parquet('{r2.s3_url(master_key)}');"
        )
        con.execute("DETACH pg;")

    with postgres.connect() as conn, conn.cursor() as cur:
        if not incremental:
            cur.execute(f"TRUNCATE {TARGET_TABLE};")
            cur.execute(
                f"INSERT INTO {TARGET_TABLE} ({cols}) SELECT {cols} FROM {STAGING_TABLE};"
            )
            inserted = cur.rowcount
            refreshed_uprn = 0
        else:
            # Transaction-bearing rows: insert only what's new, never overwrite.
            cur.execute(
                f"INSERT INTO {TARGET_TABLE} ({cols}) "
                f"SELECT {cols} FROM {STAGING_TABLE} WHERE transaction_id IS NOT NULL "
                f"ON CONFLICT (transaction_id) WHERE transaction_id IS NOT NULL "
                f"DO NOTHING;"
            )
            inserted = cur.rowcount
            # UNMATCHED_UPRN rows: replace the category with the recomputed set.
            cur.execute(
                f"DELETE FROM {TARGET_TABLE} WHERE match_type = '{MATCH_UNMATCHED_UPRN}';"
            )
            cur.execute(
                f"INSERT INTO {TARGET_TABLE} ({cols}) "
                f"SELECT {cols} FROM {STAGING_TABLE} WHERE transaction_id IS NULL;"
            )
            refreshed_uprn = cur.rowcount
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        cur.execute(f"SELECT count(*) FROM {TARGET_TABLE};")
        total_rows = cur.fetchone()[0]
        conn.commit()

    context.log.info(
        "Loaded into %s (%s transaction rows inserted, %s unmatched-UPRN rows, "
        "%s rows total)",
        TARGET_TABLE,
        inserted,
        refreshed_uprn,
        total_rows,
    )
    context.add_output_metadata(
        {
            "mode": "incremental" if incremental else "full",
            "transaction_rows_inserted": inserted,
            "unmatched_uprn_rows": refreshed_uprn,
            "table_rows_total": total_rows,
        }
    )
