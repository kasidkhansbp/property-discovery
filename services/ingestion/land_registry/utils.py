"""Shared download / clean / load logic for the PPD pipeline.

These three steps are identical for both chains (complete backfill and monthly
delta); only the source URL, object-key prefix, and delete handling differ, and
those arrive as arguments. The Dagster assets in `assets.py` are thin wrappers
that call into here.

Nothing here touches the local filesystem: the raw file is streamed from HMLR
straight into R2, DuckDB reads/writes R2 over httpfs, and the Postgres load is
driven by DuckDB's postgres extension.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import duckdb
import requests
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource
from .schema import COLUMNS, CSV_COLUMNS_SPEC, PG_DDL_COLS, PPD_SCHEMA, UPDATE_SET

TARGET_TABLE = "land_registry_sales"
STAGING_TABLE = "land_registry_sales_staging"


@contextmanager
def duckdb_con(r2: R2Resource) -> Iterator[duckdb.DuckDBPyConnection]:
    """A DuckDB connection pre-configured for this R2 bucket, auto-closed.

    Replaces the hand-rolled ``try/finally con.close()`` at each call site: the
    connection is opened, pointed at R2 over httpfs, yielded, and always closed
    on exit — even if the query raises.
    """
    con = duckdb.connect()
    try:
        r2.configure_duckdb(con)
        yield con
    finally:
        con.close()


def download_to_r2(
    context: AssetExecutionContext, r2: R2Resource, url: str, raw_key: str
) -> str:
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


def clean_to_parquet(
    context: AssetExecutionContext, r2: R2Resource, raw_key: str, clean_key: str
) -> str:
    """DuckDB reads the raw CSV from R2, tidies it, writes clean Parquet to R2.

    Cleaning: strip the ``{...}`` braces off the transaction id, cast the
    transfer timestamp to a date, empty-string -> NULL for the flagged text
    columns. The record_status flag is kept intact so the load step can act on
    deletes.
    """
    src = r2.s3_url(raw_key)
    dst = r2.s3_url(clean_key)

    # Build the cleaning SELECT in schema order.
    select_exprs: list[str] = []
    for col in PPD_SCHEMA:
        if col.name == "transaction_id":
            select_exprs.append("trim(transaction_id, '{}') AS transaction_id")
        elif col.name == "transfer_date":
            select_exprs.append("CAST(transfer_date AS DATE) AS transfer_date")
        elif col.nullif_empty:
            select_exprs.append(f"nullif({col.name}, '') AS {col.name}")
        else:
            select_exprs.append(col.name)

    with duckdb_con(r2) as con:
        context.log.info("DuckDB cleaning %s -> %s", src, dst)
        con.execute(
            f"""
            COPY (
                SELECT {', '.join(select_exprs)}
                FROM read_csv('{src}', header = false, columns = {{{CSV_COLUMNS_SPEC}}})
            ) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """
        )
    context.log.info("Wrote clean Parquet at %s", clean_key)
    return clean_key


def load_to_postgres(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    clean_key: str,
    handle_deletes: bool,
) -> None:
    """Upsert the clean Parquet into `land_registry_sales`.

    Idempotent: create the table if missing, bulk-load the Parquet into a
    staging table via DuckDB's postgres extension, then merge with
    ``ON CONFLICT``. When `handle_deletes` is set (monthly delta), rows flagged
    'D' are removed from the target instead of upserted.
    """
    col_list = ", ".join(COLUMNS)

    # 1) Ensure the target exists and give ourselves a fresh staging table.
    with postgres.connect() as conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (\n    {PG_DDL_COLS}\n);")
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
    with duckdb_con(r2) as con:
        con.execute("INSTALL postgres; LOAD postgres;")
        con.execute(f"ATTACH '{postgres.dsn}' AS pg (TYPE postgres);")
        context.log.info("Bulk-loading %s into staging", clean_key)
        con.execute(
            f"INSERT INTO pg.{STAGING_TABLE} ({col_list}) "
            f"SELECT {col_list} FROM read_parquet('{r2.s3_url(clean_key)}');"
        )
        con.execute("DETACH pg;")

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
            f"ON CONFLICT (transaction_id) DO UPDATE SET {UPDATE_SET};"
        )
        upserted = cur.rowcount
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        conn.commit()

    context.log.info(
        "Loaded into %s (%s upserted, %s deleted)", TARGET_TABLE, upserted, deleted
    )
