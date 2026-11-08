"""Shared download / clean / load logic for the EPC pipeline.

These three steps are identical for both chains (complete backfill and monthly
refresh); only the object-key prefix differs, and that arrives as an argument.
The Dagster assets in `assets.py` are thin wrappers that call into here.

One unavoidable difference from land_registry: EPC's bulk file is a ZIP of many
per-year ``.csv`` files, which DuckDB can't read in place over httpfs. So unlike
PPD's single streamed CSV, the clean step pulls the raw ZIP back from R2 to a
temp dir, extracts the CSV members, and lets DuckDB read them as a glob. The raw
download and the Postgres load still stream — only the extraction touches local
disk, and only transiently.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from typing import Iterator

import duckdb
import requests
from dagster import AssetExecutionContext

from .resources import EpcResource, PostgresResource, R2Resource
from .schema import COLUMNS, EPC_SCHEMA, PG_DDL_COLS, PK_COLUMN, UPDATE_SET

TARGET_TABLE = "epc_domestic_certificates"
STAGING_TABLE = "epc_domestic_certificates_staging"


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


def _clean_select() -> str:
    """Build the cleaning SELECT list from EPC_SCHEMA.

    The CSV is read ``all_varchar``, so every value starts as text. Text columns
    optionally empty-string -> NULL; typed columns are NULLIF'd then CAST (so an
    empty cell becomes NULL rather than blowing up the cast).
    """
    exprs: list[str] = []
    for col in EPC_SCHEMA:
        src = f'"{col.csv_name}"'
        if col.csv_type == "VARCHAR":
            exprs.append(f"nullif({src}, '') AS {col.name}" if col.nullif_empty
                         else f"{src} AS {col.name}")
        else:
            exprs.append(f"CAST(nullif({src}, '') AS {col.csv_type}) AS {col.name}")
    return ", ".join(exprs)


def download_to_r2(
    context: AssetExecutionContext,
    r2: R2Resource,
    epc: EpcResource,
    url: str,
    raw_key: str,
) -> str:
    """Stream the EPC bulk ZIP straight into R2 at `raw_key` in multipart chunks.

    The download is gated behind the EPC API's bearer token, so the auth headers
    from `epc` ride along. The endpoint answers with a 302 to a presigned S3 URL;
    `requests` follows it automatically (dropping the Authorization header on the
    cross-host hop, as the presigned URL expects). The body never has to fit in
    memory or on local disk.
    """
    context.log.info("Downloading %s -> %s", url, r2.s3_url(raw_key))
    # (connect timeout, read timeout=None) — the body can stream for a while.
    with requests.get(
        url, headers=epc.auth_headers(), stream=True, timeout=(30, None)
    ) as resp:
        resp.raise_for_status()
        resp.raw.decode_content = True  # transparently handle content-encoding
        r2.upload_stream(resp.raw, raw_key)
    context.log.info(
        "Landed raw ZIP at %s (%.2f GB)", raw_key, r2.object_size(raw_key) / 1e9
    )
    return raw_key


def _extract_certificate_csvs(zip_path: str, dest_dir: str) -> int:
    """Extract every ``.csv`` member of the bulk ZIP into `dest_dir`.

    The new MHCLG domestic full-load archive holds the dataset as a series of
    per-year ``.csv`` files (one ZIP, domestic certificates only — recommendations
    have their own endpoint). We take every CSV member and skip anything else
    (e.g. a licence/readme), writing each to a flat, uniquely-named file so DuckDB
    can glob them.
    """
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename
            if info.is_dir() or not name.lower().endswith(".csv"):
                continue
            with zf.open(info) as member, open(
                os.path.join(dest_dir, f"{count}.csv"), "wb"
            ) as out:
                shutil.copyfileobj(member, out)
            count += 1
    return count


def clean_to_parquet(
    context: AssetExecutionContext, r2: R2Resource, raw_key: str, clean_key: str
) -> str:
    """Extract the ZIP's certificate CSVs, tidy them, write clean Parquet to R2.

    Cleaning: project the useful column subset (see schema.py), NULL out empty
    strings, and cast dates / numerics. DuckDB reads the extracted CSVs as a glob
    (``all_varchar``, ``union_by_name`` so a stray column in one authority's file
    doesn't break the read) and writes a single clean Parquet to R2.
    """
    dst = r2.s3_url(clean_key)
    work_dir = tempfile.mkdtemp(prefix="epc_")
    zip_path = os.path.join(work_dir, "raw.zip")
    csv_dir = os.path.join(work_dir, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    try:
        context.log.info("Pulling raw ZIP %s back for extraction", raw_key)
        r2.download_file(raw_key, zip_path)
        n = _extract_certificate_csvs(zip_path, csv_dir)
        context.log.info("Extracted %s CSV members", n)
        if n == 0:
            raise ValueError(f"No CSV members found in {raw_key}")

        # DuckDB wants forward-slash globs, even on Windows.
        glob = csv_dir.replace("\\", "/") + "/*.csv"
        with duckdb_con(r2) as con:
            context.log.info("DuckDB cleaning %s CSVs -> %s", n, dst)
            con.execute(
                f"""
                COPY (
                    SELECT {_clean_select()}
                    FROM read_csv(
                        '{glob}',
                        header = true,
                        all_varchar = true,
                        union_by_name = true
                    )
                ) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD);
                """
            )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    context.log.info("Wrote clean Parquet at %s", clean_key)
    return clean_key


def load_to_postgres(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    clean_key: str,
) -> None:
    """Upsert the clean Parquet into `epc_domestic_certificates`.

    Idempotent: create the table if missing, bulk-load the Parquet into a staging
    table via DuckDB's postgres extension, then merge with ``ON CONFLICT``. EPC
    certificates are immutable and superseding — a re-lodged property gets a brand
    new certificate number rather than mutating an old row — so there are no
    deletes to apply; both chains are pure upserts keyed on certificate_number.

    The full-load file repeats some ``certificate_number`` values (the dataset is
    published as a series of per-year CSVs and a reference can recur across them),
    so staging is de-duplicated to one row per certificate — the most recent by
    ``lodgement_date`` — with ``DISTINCT ON`` before the upsert. Postgres rejects
    an ``ON CONFLICT`` command that would touch the same target row twice, so this
    dedup is what makes the merge legal, while ``ON CONFLICT`` still reconciles
    against certificates loaded on a previous run.
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
        cur.execute(
            f"INSERT INTO {TARGET_TABLE} ({col_list}) "
            f"SELECT DISTINCT ON ({PK_COLUMN}) {col_list} FROM {STAGING_TABLE} "
            f"ORDER BY {PK_COLUMN}, lodgement_date DESC NULLS LAST "
            f"ON CONFLICT ({PK_COLUMN}) DO UPDATE SET {UPDATE_SET};"
        )
        upserted = cur.rowcount
        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        conn.commit()

    context.log.info("Loaded into %s (%s upserted)", TARGET_TABLE, upserted)
