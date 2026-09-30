"""Dagster assets for the Land Registry Price Paid Data (PPD) pipeline.

There are TWO chains, each its own download -> clean -> load trip:

  * complete  — the full ~5GB history (pp-complete.csv). A one-off BACKFILL,
                launched manually (see the `ppd_backfill_job` in schedules.py).
  * monthly   — the small monthly delta (pp-monthly-update-new-version.csv),
                which carries Add/Change/Delete flags. Runs on the monthly
                SCHEDULE and keeps the table current after the backfill.

Both land in the same R2 bucket and load into the same `land_registry_sales`
table, so run the backfill once, then let the monthly job maintain it.

Nothing here touches the local filesystem: the raw file is streamed from HMLR
straight into R2, DuckDB reads/writes R2 over httpfs, and the Postgres load is
driven by DuckDB's postgres extension. That keeps the pipeline portable to any
deployment target with no assumption about local disk or OS.
"""

from datetime import datetime, timezone

import dagster as dg
import duckdb
import requests
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource

# HMLR serves both files over plain HTTP from its public S3 website endpoint.
_HMLR_BASE = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
)
# Full Price Paid Data — every transaction since 1995 (~5GB).
PPD_COMPLETE_URL = f"{_HMLR_BASE}/pp-complete.csv"
# Monthly delta — the "new version" carries Add(A)/Change(C)/Delete(D) flags.
PPD_MONTHLY_URL = f"{_HMLR_BASE}/pp-monthly-update-new-version.csv"

TARGET_TABLE = "land_registry_sales"
STAGING_TABLE = "land_registry_sales_staging"

# The clean column set, in order. PPD's raw CSV has no header; these map 1:1 to
# its 16 positional columns. This single list drives the DuckDB read, the table
# DDL, and the upsert, so the shape only ever has to be described once.
COLUMNS: list[str] = [
    "transaction_id",  # PPD "Transaction unique identifier" — the natural PK
    "price",
    "transfer_date",
    "postcode",
    "property_type",
    "old_new",
    "duration",
    "paon",
    "saon",
    "street",
    "locality",
    "town_city",
    "district",
    "county",
    "ppd_category",
    "record_status",  # A=add, C=change, D=delete (monthly); always A in complete
]

# DuckDB CSV column spec (raw file order == COLUMNS order). Typed where DuckDB
# can parse directly, text where the value needs cleaning first.
_CSV_COLUMNS = {
    "transaction_id": "VARCHAR",
    "price": "BIGINT",
    "transfer_date": "TIMESTAMP",
    "postcode": "VARCHAR",
    "property_type": "VARCHAR",
    "old_new": "VARCHAR",
    "duration": "VARCHAR",
    "paon": "VARCHAR",
    "saon": "VARCHAR",
    "street": "VARCHAR",
    "locality": "VARCHAR",
    "town_city": "VARCHAR",
    "district": "VARCHAR",
    "county": "VARCHAR",
    "ppd_category": "VARCHAR",
    "record_status": "VARCHAR",
}

# Postgres column types for the served table.
_PG_COLUMN_TYPES = {
    "transaction_id": "text PRIMARY KEY",
    "price": "bigint",
    "transfer_date": "date",
    "postcode": "text",
    "property_type": "text",
    "old_new": "text",
    "duration": "text",
    "paon": "text",
    "saon": "text",
    "street": "text",
    "locality": "text",
    "town_city": "text",
    "district": "text",
    "county": "text",
    "ppd_category": "text",
    "record_status": "text",
}

# Text columns whose empty strings should become NULL during cleaning.
_TEXT_COLS = (
    "postcode", "paon", "saon", "street",
    "locality", "town_city", "district", "county",
)


def _stamp() -> str:
    """UTC date stamp used to partition raw/clean objects by run."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# Shared step implementations (used by both the complete and monthly chains).  #
# --------------------------------------------------------------------------- #

def _download_to_r2(context: AssetExecutionContext, r2: R2Resource, url: str,
                    raw_key: str) -> str:
    """Stream `url` straight into R2 at `raw_key` in multipart chunks.

    The body never has to fit in memory or on local disk, so this handles the
    5GB complete file as happily as the small monthly delta.
    """
    context.log.info("Downloading %s -> %s", url, r2.s3_url(raw_key))
    # (connect timeout, read timeout=None) — the body can stream for a while.
    with requests.get(url, stream=True, timeout=(30, None)) as resp:
        resp.raise_for_status()
        resp.raw.decode_content = True  # transparently handle content-encoding
        r2.upload_stream(resp.raw, raw_key)
    context.log.info(
        "Landed raw CSV at %s (%.2f GB)", raw_key, r2.object_size(raw_key) / 1e9
    )
    return raw_key


def _clean_to_parquet(context: AssetExecutionContext, r2: R2Resource,
                      raw_key: str, clean_key: str) -> str:
    """DuckDB reads the raw CSV from R2, tidies it, writes clean Parquet to R2.

    Cleaning: strip the ``{...}`` braces off the transaction id, cast the
    transfer timestamp to a date, empty-string -> NULL for text columns. The
    record_status flag is kept intact so the load step can act on deletes.
    """
    src = r2.s3_url(raw_key)
    dst = r2.s3_url(clean_key)
    columns_spec = ", ".join(f"'{n}': '{t}'" for n, t in _CSV_COLUMNS.items())

    # Build the cleaning SELECT in COLUMNS order.
    select_exprs: list[str] = []
    for col in COLUMNS:
        if col == "transaction_id":
            select_exprs.append("trim(transaction_id, '{}') AS transaction_id")
        elif col == "transfer_date":
            select_exprs.append("CAST(transfer_date AS DATE) AS transfer_date")
        elif col in _TEXT_COLS:
            select_exprs.append(f"nullif({col}, '') AS {col}")
        else:
            select_exprs.append(col)

    con = duckdb.connect()
    try:
        r2.configure_duckdb(con)
        context.log.info("DuckDB cleaning %s -> %s", src, dst)
        con.execute(
            f"""
            COPY (
                SELECT {', '.join(select_exprs)}
                FROM read_csv('{src}', header = false, columns = {{{columns_spec}}})
            ) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
        )
    finally:
        con.close()
    context.log.info("Wrote clean Parquet at %s", clean_key)
    return clean_key


def _load_to_postgres(context: AssetExecutionContext, r2: R2Resource,
                      postgres: PostgresResource, clean_key: str,
                      handle_deletes: bool) -> None:
    """Upsert the clean Parquet into `land_registry_sales`.

    Idempotent: create the table if missing, bulk-load the Parquet into a
    staging table via DuckDB's postgres extension, then merge with
    ``ON CONFLICT``. When `handle_deletes` is set (monthly delta), rows flagged
    'D' are removed from the target instead of upserted.
    """
    col_list = ", ".join(COLUMNS)
    ddl_cols = ",\n    ".join(f"{c} {_PG_COLUMN_TYPES[c]}" for c in COLUMNS)
    update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])  # all but PK

    # 1) Ensure the target exists and give ourselves a fresh staging table.
    with postgres.connect() as conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (\n    {ddl_cols}\n);")
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {TARGET_TABLE}_postcode_idx "
            f"ON {TARGET_TABLE} (postcode);"
        )
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        cur.execute(
            f"CREATE TABLE {STAGING_TABLE} (LIKE {TARGET_TABLE} INCLUDING DEFAULTS);"
        )
        conn.commit()

    # 2) Stream the Parquet from R2 straight into staging. DuckDB reads over
    #    httpfs and writes to Postgres via its postgres extension — no local
    #    files, no row-by-row Python.
    con = duckdb.connect()
    try:
        r2.configure_duckdb(con)
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{postgres.dsn}' AS pg (TYPE postgres);")
        context.log.info("Bulk-loading %s into staging", clean_key)
        con.execute(
            f"INSERT INTO pg.{STAGING_TABLE} ({col_list}) "
            f"SELECT {col_list} FROM read_parquet('{r2.s3_url(clean_key)}');"
        )
        con.execute("DETACH pg;")
    finally:
        con.close()

    # 3) Apply staging to the target, then drop staging.
    with postgres.connect() as conn, conn.cursor() as cur:
        deleted = 0
        if handle_deletes:
            cur.execute(
                f"DELETE FROM {TARGET_TABLE} t "
                f"USING {STAGING_TABLE} s "
                f"WHERE t.transaction_id = s.transaction_id "
                f"AND s.record_status = 'D';"
            )
            deleted = cur.rowcount
        cur.execute(
            f"INSERT INTO {TARGET_TABLE} ({col_list}) "
            f"SELECT {col_list} FROM {STAGING_TABLE} "
            f"WHERE record_status IS DISTINCT FROM 'D' "
            f"ON CONFLICT (transaction_id) DO UPDATE SET {update_set};"
        )
        upserted = cur.rowcount
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        conn.commit()

    context.log.info(
        "Loaded into %s (%s upserted, %s deleted)", TARGET_TABLE, upserted, deleted
    )


# --------------------------------------------------------------------------- #
# Chain 1: complete backfill (manually triggered, one-off ~5GB load).         #
# --------------------------------------------------------------------------- #

@dg.asset(group_name="land_registry")
def ppd_complete_raw_csv(context: AssetExecutionContext, r2: R2Resource) -> str:
    """Backfill step 1: stream the full pp-complete.csv into the R2 raw zone."""
    return _download_to_r2(
        context, r2, PPD_COMPLETE_URL, f"raw/land_registry/complete/{_stamp()}.csv"
    )


@dg.asset(group_name="land_registry")
def ppd_complete_clean_parquet(
    context: AssetExecutionContext, r2: R2Resource, ppd_complete_raw_csv: str
) -> str:
    """Backfill step 2: clean the complete CSV into Parquet in R2."""
    return _clean_to_parquet(
        context, r2, ppd_complete_raw_csv,
        f"clean/land_registry/complete/{_stamp()}.parquet",
    )


@dg.asset(group_name="land_registry")
def ppd_complete_loaded_to_postgres(
    context: AssetExecutionContext, r2: R2Resource, postgres: PostgresResource,
    ppd_complete_clean_parquet: str,
) -> None:
    """Backfill step 3: upsert the full history into land_registry_sales.

    No delete handling — the complete file is a pure snapshot (all 'A' rows).
    """
    _load_to_postgres(
        context, r2, postgres, ppd_complete_clean_parquet, handle_deletes=False
    )


# --------------------------------------------------------------------------- #
# Chain 2: monthly delta (scheduled, keeps the table current after backfill).  #
# --------------------------------------------------------------------------- #

@dg.asset(group_name="land_registry")
def ppd_monthly_raw_csv(context: AssetExecutionContext, r2: R2Resource) -> str:
    """Monthly step 1: stream the monthly update file into the R2 raw zone."""
    return _download_to_r2(
        context, r2, PPD_MONTHLY_URL, f"raw/land_registry/monthly/{_stamp()}.csv"
    )


@dg.asset(group_name="land_registry")
def ppd_monthly_clean_parquet(
    context: AssetExecutionContext, r2: R2Resource, ppd_monthly_raw_csv: str
) -> str:
    """Monthly step 2: clean the delta CSV into Parquet in R2."""
    return _clean_to_parquet(
        context, r2, ppd_monthly_raw_csv,
        f"clean/land_registry/monthly/{_stamp()}.parquet",
    )


@dg.asset(group_name="land_registry")
def ppd_monthly_loaded_to_postgres(
    context: AssetExecutionContext, r2: R2Resource, postgres: PostgresResource,
    ppd_monthly_clean_parquet: str,
) -> None:
    """Monthly step 3: apply the delta to land_registry_sales.

    Adds/changes are upserted; rows flagged 'D' are deleted.
    """
    _load_to_postgres(
        context, r2, postgres, ppd_monthly_clean_parquet, handle_deletes=True
    )
