#!/usr/bin/env python3
"""One-time backfill of the enrichment columns on ``property_uprn_mapping``.

The reconciliation pipeline now produces these columns for every *new* row, but
its incremental load protects rows already in the table (``ON CONFLICT DO
NOTHING``), so the ~40.6M rows written before the enrichment existed stay NULL.
This script fills them once, in place, for the existing history. After it runs,
the monthly job keeps new rows populated and you never need this script again.

Sources — EVERYTHING KEYED BY uprn (the first pass):

  * latitude / longitude / x_coordinate / y_coordinate
        <- os_open_uprn            (its uprn PK is a bigint, so the text uprn is
                                     cast after a numeric guard)
  * postcode / constituent_country
        <- epc_domestic_certificates (constituent_country = EPC's `country`),
                                     deduplicated to the LATEST certificate per
                                     uprn (a uprn can hold several)

  district / county are intentionally LEFT NULL here — EPC has no clean source
  for them (only a local-authority label; MHCLG dropped `county`). Fill them in
  a later pass from land_registry_sales (keyed by transaction_id), which this
  script can also do with ``--with-lr`` once you're ready.

Efficient + observable, by design:

  * ONE heap pass. The big UPDATE walks the table in physical ``ctid`` page
    ranges and sets all six uprn-keyed columns in a single statement per batch,
    so every row is rewritten at most once (minimal MVCC bloat) and the whole
    table is scanned once across all batches — not once per column.
  * Observable DURING the load. Each page-range batch is its own committed
    transaction, so from a second psql session you can watch progress live:

        -- rows filled so far (climbs after every batch commit):
        SELECT count(*) FILTER (WHERE latitude IS NOT NULL)      AS coords,
               count(*) FILTER (WHERE postcode IS NOT NULL)      AS epc
        FROM property_uprn_mapping;

        -- what the backfill is doing right now, and for how long:
        SELECT pid, state, wait_event, now()-xact_start AS elapsed, query
        FROM pg_stat_activity WHERE query ILIKE '%property_uprn_mapping%';

    The script also prints a page-range percentage after each batch.

The work runs server-side: DuckDB is the orchestrator but every statement is
dispatched with ``postgres_execute`` so the joins/UPDATEs execute natively inside
Postgres, where all three tables already live — no rows are dragged across the
wire. (This is why it's a Postgres-to-Postgres job rather than a DuckDB Parquet
round-trip: the data never leaves the server.)

Usage (from the repo root, with POSTGRES_DSN set):

    python scripts/backfill_property_uprn_mapping_enrichment.py
    python scripts/backfill_property_uprn_mapping_enrichment.py --pages 20000
    python scripts/backfill_property_uprn_mapping_enrichment.py --start-page 123000   # resume
    python scripts/backfill_property_uprn_mapping_enrichment.py --with-lr             # later LR pass
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

# Make the project importable when run as `python scripts/...` from the repo
# root, so we can borrow the column contract rather than duplicating it.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.jobs.ingestion.reconciliation.schema import (  # noqa: E402
    ENRICHMENT_COLUMN_TYPES,
    TARGET_TABLE,
)

# Reference tables, named exactly as the other services load them. Hard-coded
# (rather than imported from utils.py) to keep this script free of the Dagster
# dependency; they change about as often as the table names themselves.
OS_OPEN_UPRN_TABLE = "os_open_uprn"
EPC_TABLE = "epc_domestic_certificates"
LR_TABLE = "land_registry_sales"
EPC_LATEST = "epc_latest_by_uprn"  # transient staging: one EPC cert per uprn


def _dsn_from_dotenv() -> str | None:
    """Fallback: read POSTGRES_DSN from the repo-root .env (Dagster auto-loads it;
    a plain script doesn't, so we parse the one line we need ourselves)."""
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("POSTGRES_DSN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def pg_exec(con: duckdb.DuckDBPyConnection, sql: str) -> None:
    """Run one statement natively in the attached Postgres (alias ``pg``).

    ``postgres_execute`` sends the SQL straight to the Postgres server, so the
    join/UPDATE executes there — DuckDB only orchestrates. DuckDB runs each
    top-level CALL as its own auto-committed transaction, which is exactly what
    makes each batch visible to other sessions the moment it finishes.
    """
    con.execute(f"CALL postgres_execute('pg', '{sql.replace(chr(39), chr(39) * 2)}')")


def pg_scalar(con: duckdb.DuckDBPyConnection, sql: str):
    """Read a single value from Postgres via the postgres-extension query path."""
    return con.execute(
        f"SELECT * FROM postgres_query('pg', '{sql.replace(chr(39), chr(39) * 2)}')"
    ).fetchone()[0]


def add_columns(con: duckdb.DuckDBPyConnection) -> None:
    """Add every enrichment column if missing (nullable -> metadata-only, no rewrite)."""
    adds = ", ".join(
        f"ADD COLUMN IF NOT EXISTS {name} {ddl}"
        for name, ddl in ENRICHMENT_COLUMN_TYPES.items()
    )
    pg_exec(con, f"ALTER TABLE {TARGET_TABLE} {adds}")
    print(f"  columns ensured: {', '.join(ENRICHMENT_COLUMN_TYPES)}")


def build_epc_latest(con: duckdb.DuckDBPyConnection) -> None:
    """Materialise one EPC certificate per uprn (the latest) into a staging table.

    Built once (natively in Postgres via DISTINCT ON) and indexed on uprn, so the
    per-batch UPDATE joins to a slim, keyed table instead of re-deduplicating the
    whole EPC table on every batch.
    """
    pg_exec(con, f"DROP TABLE IF EXISTS {EPC_LATEST}")
    pg_exec(
        con,
        f"""
        CREATE TABLE {EPC_LATEST} AS
        SELECT DISTINCT ON (uprn) uprn, postcode, country
        FROM {EPC_TABLE}
        WHERE uprn IS NOT NULL AND btrim(uprn) <> ''
        ORDER BY uprn,
                 lodgement_date DESC NULLS LAST,
                 inspection_date DESC NULLS LAST,
                 certificate_number
        """,
    )
    pg_exec(con, f"CREATE INDEX ON {EPC_LATEST} (uprn)")
    n = pg_scalar(con, f"SELECT count(*) FROM {EPC_LATEST}")
    print(f"  {EPC_LATEST}: {n:,} distinct uprns")


def _page_count(con: duckdb.DuckDBPyConnection, table: str) -> int:
    """Heap page count for ctid batching (ceil(relation bytes / block size))."""
    pages = pg_scalar(
        con,
        f"SELECT ceil(pg_relation_size('{table}')::numeric "
        f"/ current_setting('block_size')::numeric)::bigint",
    )
    return max(1, int(pages))


def backfill_by_uprn(con: duckdb.DuckDBPyConnection, pages: int, start_page: int) -> None:
    """Fill the six uprn-keyed columns in one ctid heap pass, committing per batch.

    Coordinates from os_open_uprn, postcode + constituent_country from the EPC
    staging table. Only rows that have a uprn AND match at least one source are
    written, so untouched rows stay clean and the pass creates the fewest row
    versions possible.
    """
    total = _page_count(con, TARGET_TABLE)
    print(f"Backfilling by uprn over {total:,} heap pages, {pages} pages/batch...")
    for lo in range(start_page, total, pages):
        hi = lo + pages
        pg_exec(
            con,
            f"""
            UPDATE {TARGET_TABLE} m
            SET latitude     = src.latitude,
                longitude    = src.longitude,
                x_coordinate = src.x_coordinate,
                y_coordinate = src.y_coordinate,
                postcode     = src.postcode,
                constituent_country = src.country
            FROM (
                SELECT pm.ctid AS cid,
                       o.latitude, o.longitude, o.x_coordinate, o.y_coordinate,
                       e.postcode, e.country
                FROM {TARGET_TABLE} pm
                LEFT JOIN {OS_OPEN_UPRN_TABLE} o
                       ON pm.uprn ~ '^[0-9]+$' AND o.uprn = CAST(pm.uprn AS bigint)
                LEFT JOIN {EPC_LATEST} e ON e.uprn = pm.uprn
                WHERE pm.ctid >= '({lo},0)'::tid AND pm.ctid < '({hi},0)'::tid
                  AND pm.uprn IS NOT NULL
                  AND (o.uprn IS NOT NULL OR e.uprn IS NOT NULL)
                  -- only rows still missing at least one uprn-keyed value, so a
                  -- re-run (e.g. alongside --with-lr) skips already-filled rows
                  AND (pm.latitude IS NULL OR pm.longitude IS NULL
                       OR pm.x_coordinate IS NULL OR pm.y_coordinate IS NULL
                       OR pm.postcode IS NULL OR pm.constituent_country IS NULL)
            ) src
            WHERE m.ctid = src.cid
            """,
        )
        pct = min(hi, total) / total * 100
        print(f"  pages [{lo:,}, {min(hi, total):,}) committed  ({pct:4.1f}%)", flush=True)


def backfill_lr_district_county(
    con: duckdb.DuckDBPyConnection, pages: int, start_page: int
) -> None:
    """Optional later pass: district/county from land_registry_sales by transaction_id."""
    total = _page_count(con, TARGET_TABLE)
    print(f"Backfilling district/county from LR over {total:,} heap pages...")
    for lo in range(start_page, total, pages):
        hi = lo + pages
        pg_exec(
            con,
            f"""
            UPDATE {TARGET_TABLE} m
            SET district = src.district, county = src.county
            FROM (
                SELECT pm.ctid AS cid, lr.district, lr.county
                FROM {TARGET_TABLE} pm
                JOIN {LR_TABLE} lr ON lr.transaction_id = pm.transaction_id
                WHERE pm.ctid >= '({lo},0)'::tid AND pm.ctid < '({hi},0)'::tid
                  AND pm.transaction_id IS NOT NULL
                  AND (pm.district IS NULL OR pm.county IS NULL)  -- skip filled rows
            ) src
            WHERE m.ctid = src.cid
            """,
        )
        pct = min(hi, total) / total * 100
        print(f"  pages [{lo:,}, {min(hi, total):,}) committed  ({pct:4.1f}%)", flush=True)


def report(con: duckdb.DuckDBPyConnection) -> None:
    """Print how many rows are filled per column, as a sanity check."""
    total = pg_scalar(con, f"SELECT count(*) FROM {TARGET_TABLE}")
    print(f"\nTable {TARGET_TABLE}: {total:,} rows")
    for col in ENRICHMENT_COLUMN_TYPES:
        nulls = pg_scalar(con, f"SELECT count(*) FROM {TARGET_TABLE} WHERE {col} IS NULL")
        print(f"  {col:<20} {total - nulls:>12,} filled  ({nulls:,} NULL)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=os.environ.get("POSTGRES_DSN"),
                    help="Postgres DSN (defaults to $POSTGRES_DSN, then repo .env).")
    ap.add_argument("--pages", type=int, default=10000,
                    help="Heap pages per committed batch (bigger = fewer commits).")
    ap.add_argument("--start-page", type=int, default=0,
                    help="Resume from this heap page (after an interrupted run).")
    ap.add_argument("--with-lr", action="store_true",
                    help="Also run the later district/county pass from land_registry_sales.")
    args = ap.parse_args()
    dsn = args.dsn or _dsn_from_dotenv()
    if not dsn:
        ap.error("no DSN: pass --dsn, set POSTGRES_DSN, or add it to the repo .env")

    con = duckdb.connect()
    try:
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres);")
        # Keep the per-batch hash joins in memory rather than spilling to temp
        # files (the server default work_mem is tiny, e.g. 4MB).
        pg_exec(con, "SET work_mem = '256MB'")
        print("Adding columns...")
        add_columns(con)
        print("Building latest-EPC-per-uprn staging...")
        build_epc_latest(con)
        backfill_by_uprn(con, args.pages, args.start_page)
        if args.with_lr:
            backfill_lr_district_county(con, args.pages, args.start_page)
        pg_exec(con, f"DROP TABLE IF EXISTS {EPC_LATEST}")
        report(con)
    finally:
        con.close()
    print(
        "\nDone. district/county are still NULL "
        + ("(LR pass ran)." if args.with_lr else "— run again with --with-lr to fill them.")
    )
    print("Tip: run `VACUUM (ANALYZE) property_uprn_mapping;` afterwards to reclaim "
          "space and refresh planner stats.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
