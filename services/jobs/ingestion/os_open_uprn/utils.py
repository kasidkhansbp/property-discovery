"""Shared download / clean / load logic for the OS Open UPRN pipeline.

OS Open UPRN is a free OpenData product served from the OS Data Hub **Downloads
API** (no key required). Every ~6 weeks OS republishes the whole of Great Britain
as one file; there is no delta feed. The pipeline is three stages, each a thin
Dagster asset in assets.py wrapping one function here:

  1. ``download_to_r2``   — ask the Downloads API for the current CSV release's
                            metadata (download URL + md5 + size), and if that md5
                            differs from the one we last loaded, stream the ~600MB
                            ZIP straight into R2. If the md5 matches, the release is
                            unchanged, so this SKIPS the download (and everything
                            downstream) without transferring the body.
  2. ``clean_zip_to_parquet`` — pull the ZIP back from R2, extract the data CSV,
                            and DuckDB cleans it into Parquet (columns matched by
                            header name, cast per the schema).
  3. ``load_to_postgres`` — bulk-load the clean Parquet into a staging table, then
                            apply only the DIFFERENCE to ``os_open_uprn``: INSERT
                            new UPRNs, UPDATE only rows whose coordinates moved,
                            DELETE UPRNs that dropped out of the release — all in
                            one transaction. Then record the release md5.

Two layers answer "don't do work when nothing changed": the API md5 skips the
whole run when the release is unchanged, and the diff-merge never rewrites the
~99% of rows that didn't change between two different releases.

The raw download and the Postgres load stream; only the ZIP extraction touches
local disk, and only transiently.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import duckdb
import requests
from dagster import AssetExecutionContext

from ..duckdb_support import bounded_duckdb
from .resources import PostgresResource, R2Resource
from .schema import (
    CHANGED_PREDICATE,
    CLEAN_SELECT,
    COLUMNS,
    PG_DDL_COLS,
    PK_COLUMN,
    UPDATE_SET_FROM_STAGING,
)

TARGET_TABLE = "os_open_uprn"
STAGING_TABLE = "os_open_uprn_staging"
# Singleton bookkeeping row recording the md5 of the last release that
# successfully loaded, so an unchanged release can be skipped before download.
STATE_TABLE = "os_open_uprn_load_state"


@contextmanager
def duckdb_con(r2: R2Resource) -> Iterator[duckdb.DuckDBPyConnection]:
    """A memory-bounded DuckDB connection pointed at this R2 bucket, auto-closed.

    Thin wrapper over the shared ``bounded_duckdb`` (duckdb_support.py).
    """
    with bounded_duckdb(r2) as con:
        yield con


def _ensure_state_table(cur) -> None:
    """Create the singleton load-state table if missing.

    The ``singleton`` CHECK + PRIMARY KEY pins the table to a single row, so the
    release md5 is upserted rather than accumulating history.
    """
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STATE_TABLE} (
            singleton  boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            file_name  text        NOT NULL,
            md5        text        NOT NULL,
            size_bytes bigint      NOT NULL,
            rows_total bigint      NOT NULL,
            loaded_at  timestamptz NOT NULL
        );
        """
    )


def _last_loaded_md5(postgres: PostgresResource) -> str | None:
    """The md5 of the release currently loaded, or None if nothing has loaded."""
    with postgres.connect() as conn, conn.cursor() as cur:
        _ensure_state_table(cur)
        conn.commit()
        cur.execute(f"SELECT md5 FROM {STATE_TABLE} WHERE singleton;")
        row = cur.fetchone()
    return row[0] if row else None


def select_download(entries: list[dict], fmt: str, area: str) -> dict:
    """Pick the one download matching `fmt`/`area` from the API's list response.

    Pure (no network) so the selection is unit-testable. Raises if the desired
    format/area isn't offered, rather than silently downloading the wrong file.
    """
    for entry in entries:
        if entry.get("format") == fmt and entry.get("area") == area:
            return entry
    offered = ", ".join(f"{e.get('format')}/{e.get('area')}" for e in entries)
    raise ValueError(
        f"No OS Open UPRN download for format={fmt} area={area}; offered: {offered}"
    )


def fetch_download_metadata(list_url: str, fmt: str, area: str) -> dict:
    """GET the Downloads API list for the product and return the chosen entry.

    The entry carries the release's ``url`` (a redirecting download link),
    ``md5``, ``size`` and ``fileName``. No auth — this is an OpenData product.
    """
    resp = requests.get(list_url, timeout=(30, 120))
    resp.raise_for_status()
    return select_download(resp.json(), fmt, area)


def download_to_r2(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    list_url: str,
    fmt: str,
    area: str,
    raw_key: str,
) -> dict:
    """Fetch the current OS Open UPRN release into R2 — unless it's unchanged.

    Looks up the release metadata (incl. md5) from the Downloads API and compares
    the md5 to the one we last loaded. If they match, returns ``{"skip": True}``
    WITHOUT downloading the ~600MB ZIP, so the whole run no-ops. Otherwise streams
    the ZIP straight into R2 at `raw_key` (the API 302s to the file host;
    ``requests`` follows the redirect automatically).
    """
    meta = fetch_download_metadata(list_url, fmt, area)
    md5, size, file_name = meta["md5"], int(meta["size"]), meta["fileName"]
    context.log.info(
        "Latest OS Open UPRN %s/%s: %s (md5=%s, %.2f GB)",
        fmt,
        area,
        file_name,
        md5,
        size / 1e9,
    )

    if _last_loaded_md5(postgres) == md5:
        context.log.info("Release md5 unchanged — already loaded; skipping run.")
        context.add_output_metadata({"skipped": True, "file_name": file_name})
        return {"skip": True, "md5": md5, "size": size, "file_name": file_name}

    context.log.info("Downloading %s -> %s", meta["url"], r2.s3_url(raw_key))
    # (connect timeout, read timeout=None) — the body can stream for a while.
    with requests.get(meta["url"], stream=True, timeout=(30, None)) as resp:
        resp.raise_for_status()
        resp.raw.decode_content = True  # transparently handle content-encoding
        r2.upload_stream(resp.raw, raw_key)
    context.log.info(
        "Landed raw ZIP at %s (%.2f GB)", raw_key, r2.object_size(raw_key) / 1e9
    )
    context.add_output_metadata(
        {"skipped": False, "file_name": file_name, "raw_key": raw_key, "md5": md5}
    )
    return {
        "skip": False,
        "raw_key": raw_key,
        "md5": md5,
        "size": size,
        "file_name": file_name,
    }


def _extract_csvs(zip_path: str, dest_dir: str) -> int:
    """Extract every ``.csv`` member of the ZIP into `dest_dir` as a flat file.

    The OS Open UPRN CSV archive holds the single data CSV alongside a licence /
    readme (under a Docs folder). We take every ``.csv`` member and skip the
    rest, writing each to a uniquely-named file so DuckDB can glob them.
    """
    count = 0
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".csv"):
                continue
            with zf.open(info) as member, open(
                os.path.join(dest_dir, f"{count}.csv"), "wb"
            ) as out:
                shutil.copyfileobj(member, out)
            count += 1
    return count


def clean_zip_to_parquet(
    context: AssetExecutionContext,
    r2: R2Resource,
    raw: dict,
    clean_key: str,
) -> dict:
    """Extract the raw ZIP's CSV and clean it into Parquet at `clean_key`.

    No-ops (passes the skip flag through) when the download step skipped. Columns
    are matched to the schema BY HEADER NAME via ``CLEAN_SELECT``, so OS reordering
    the columns is harmless and a renamed/missing header fails loudly.
    """
    if raw.get("skip"):
        return raw

    raw_key = raw["raw_key"]
    dst = r2.s3_url(clean_key)
    work_dir = tempfile.mkdtemp(prefix="os_open_uprn_")
    zip_path = os.path.join(work_dir, "raw.zip")
    csv_dir = os.path.join(work_dir, "csv")
    os.makedirs(csv_dir, exist_ok=True)
    try:
        context.log.info("Pulling raw ZIP %s back for extraction", raw_key)
        r2.download_file(raw_key, zip_path)
        n = _extract_csvs(zip_path, csv_dir)
        context.log.info("Extracted %s CSV member(s)", n)
        if n == 0:
            raise ValueError(f"No CSV members found in {raw_key}")

        glob = csv_dir.replace("\\", "/") + "/*.csv"  # DuckDB wants forward slashes
        with duckdb_con(r2) as con:
            context.log.info("DuckDB cleaning %s CSV(s) -> %s", n, dst)
            con.execute(
                f"""
                COPY (
                    SELECT {CLEAN_SELECT}
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
    context.add_output_metadata({"skipped": False, "clean_key": clean_key})
    return {**raw, "clean_key": clean_key}


def load_to_postgres(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    clean: dict,
) -> None:
    """Diff-merge the clean Parquet into `os_open_uprn`.

    No-ops when the upstream skipped (unchanged release). Otherwise: ensure the
    target exists, bulk-load the Parquet into a fresh staging table via DuckDB's
    postgres extension, then apply only the difference — INSERT new UPRNs, UPDATE
    rows whose coordinates moved, DELETE UPRNs no longer in the release — all in
    one transaction. Finally record the loaded release's md5.
    """
    if clean.get("skip"):
        context.log.info("Upstream skipped this release; nothing to load.")
        return

    clean_key = clean["clean_key"]
    col_list = ", ".join(COLUMNS)

    # 1) Ensure the target exists and give ourselves a fresh staging table.
    with postgres.connect() as conn, conn.cursor() as cur:
        cur.execute(f"CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (\n    {PG_DDL_COLS}\n);")
        _ensure_state_table(cur)
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

    # 3) Apply ONLY the difference, in a single transaction, then drop staging
    #    and record the release md5. Unchanged rows (the vast majority) are never
    #    touched, so there's no whole-table rewrite / bloat.
    insert_vals = ", ".join(f"s.{c}" for c in COLUMNS)
    with postgres.connect() as conn, conn.cursor() as cur:
        # UPDATE only rows whose coordinates actually changed.
        cur.execute(
            f"UPDATE {TARGET_TABLE} t SET {UPDATE_SET_FROM_STAGING} "
            f"FROM {STAGING_TABLE} s "
            f"WHERE t.{PK_COLUMN} = s.{PK_COLUMN} AND {CHANGED_PREDICATE};"
        )
        updated = cur.rowcount
        # INSERT UPRNs present in the new release but not yet in the table.
        cur.execute(
            f"INSERT INTO {TARGET_TABLE} ({col_list}) "
            f"SELECT {insert_vals} FROM {STAGING_TABLE} s "
            f"LEFT JOIN {TARGET_TABLE} t ON t.{PK_COLUMN} = s.{PK_COLUMN} "
            f"WHERE t.{PK_COLUMN} IS NULL;"
        )
        inserted = cur.rowcount
        # DELETE UPRNs that dropped out of the release (OS retired them).
        cur.execute(
            f"DELETE FROM {TARGET_TABLE} t "
            f"WHERE NOT EXISTS (SELECT 1 FROM {STAGING_TABLE} s "
            f"WHERE s.{PK_COLUMN} = t.{PK_COLUMN});"
        )
        deleted = cur.rowcount

        cur.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE};")
        cur.execute(f"SELECT count(*) FROM {TARGET_TABLE};")
        total_rows = cur.fetchone()[0]

        # Record the loaded release's md5 so an unchanged re-run is skipped next
        # time. Written in the same transaction as the merge.
        cur.execute(
            f"""
            INSERT INTO {STATE_TABLE}
                (singleton, file_name, md5, size_bytes, rows_total, loaded_at)
            VALUES (true, %s, %s, %s, %s, %s)
            ON CONFLICT (singleton) DO UPDATE SET
                file_name  = EXCLUDED.file_name,
                md5        = EXCLUDED.md5,
                size_bytes = EXCLUDED.size_bytes,
                rows_total = EXCLUDED.rows_total,
                loaded_at  = EXCLUDED.loaded_at;
            """,
            (
                clean["file_name"],
                clean["md5"],
                clean["size"],
                total_rows,
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()

    context.log.info(
        "Loaded into %s (%s inserted, %s updated, %s deleted; %s rows total)",
        TARGET_TABLE,
        inserted,
        updated,
        deleted,
        total_rows,
    )
    context.add_output_metadata(
        {
            "inserted": inserted,
            "updated": updated,
            "deleted": deleted,
            "rows_total": total_rows,
            "unchanged": total_rows - inserted - updated,
        }
    )
