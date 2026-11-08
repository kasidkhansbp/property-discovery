"""Dagster assets for the OS Open UPRN pipeline.

One chain — download -> clean -> load — because OS Open UPRN is a full
Great-Britain snapshot (no complete/monthly split: every release is the whole
dataset).

  * download — ask the OS Downloads API for the current CSV release and stream its
               ZIP into R2, unless the release md5 matches the one already loaded
               (then the whole run is skipped before any transfer).
  * clean    — extract the CSV from the ZIP and write clean Parquet to R2.
  * load     — diff-merge the clean Parquet into `os_open_uprn`: insert new UPRNs,
               update only moved coordinates, delete retired UPRNs.

The steps are wired download -> clean -> load via explicit `AssetIn`s so the keys
stay stable regardless of the Python parameter names. The schema they share is
defined once in schema.py; the logic lives in utils.py.
"""

from datetime import datetime, timezone

import dagster as dg
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource
from .utils import clean_zip_to_parquet, download_to_r2, load_to_postgres

# OS Data Hub Downloads API — the OpenData product's download list (no API key
# required). Each entry carries a redirecting download URL, md5, size and
# fileName; we pick the GB / CSV one.
OS_OPEN_UPRN_DOWNLOADS_URL = (
    "https://api.os.uk/downloads/v1/products/OpenUPRN/downloads"
)
DOWNLOAD_FORMAT = "CSV"
DOWNLOAD_AREA = "GB"


def _stamp() -> str:
    """UTC date stamp used to partition the run's R2 objects."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dg.asset(name="os_open_uprn_raw_zip", group_name="os_open_uprn")
def os_open_uprn_raw_zip(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
) -> dict:
    """Step 1: fetch the current release ZIP into R2 (or skip if unchanged)."""
    return download_to_r2(
        context,
        r2,
        postgres,
        OS_OPEN_UPRN_DOWNLOADS_URL,
        DOWNLOAD_FORMAT,
        DOWNLOAD_AREA,
        f"raw/os_open_uprn/{_stamp()}.zip",
    )


@dg.asset(
    name="os_open_uprn_clean_parquet",
    group_name="os_open_uprn",
    ins={"raw": dg.AssetIn("os_open_uprn_raw_zip")},
)
def os_open_uprn_clean_parquet(
    context: AssetExecutionContext, r2: R2Resource, raw: dict
) -> dict:
    """Step 2: extract the CSV from the ZIP and clean it into Parquet."""
    return clean_zip_to_parquet(
        context, r2, raw, f"clean/os_open_uprn/{_stamp()}.parquet"
    )


@dg.asset(
    name="os_open_uprn_loaded_to_postgres",
    group_name="os_open_uprn",
    ins={"clean": dg.AssetIn("os_open_uprn_clean_parquet")},
)
def os_open_uprn_loaded_to_postgres(
    context: AssetExecutionContext,
    r2: R2Resource,
    postgres: PostgresResource,
    clean: dict,
) -> None:
    """Step 3: diff-merge the clean Parquet into os_open_uprn."""
    load_to_postgres(context, r2, postgres, clean)
