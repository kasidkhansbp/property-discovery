"""Dagster assets for the Land Registry Price Paid Data (PPD) pipeline.

The trip one record takes:
    download PPD CSV  ->  land in R2 (raw, untouched)  ->  DuckDB clean to Parquet  ->  load into Postgres

Each step below is its own @asset so Dagster can run, retry, and show them
individually. Fill in the TODOs with real logic when you're ready — the shapes
here are deliberately minimal so `dagster dev` loads without errors.
"""

import dagster as dg
from dagster import AssetExecutionContext


@dg.asset(group_name="land_registry")
def ppd_raw_csv(context: AssetExecutionContext) -> str:
    """Step 1: download the monthly PPD CSV from GOV.UK / HMLR and land it,
    untouched, in the R2 raw zone.

    Returns the R2 object key (path) so the next asset knows where to read from.
    """
    # TODO: download from https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads
    # TODO: upload the bytes to R2 exactly as received (no edits) via resources.r2
    raw_key = "raw/land_registry/pp-monthly-latest.csv"
    context.log.info("Landed raw PPD CSV at %s (stub)", raw_key)
    return raw_key


@dg.asset(group_name="land_registry")
def ppd_clean_parquet(context: AssetExecutionContext, ppd_raw_csv: str) -> str:
    """Step 2: use DuckDB to read the raw CSV, tidy it, and write clean Parquet.

    Takes the raw R2 key from step 1, returns the clean Parquet R2 key.
    """
    # TODO: DuckDB read_csv on ppd_raw_csv -> select/rename/cast columns -> COPY TO parquet
    clean_key = "clean/land_registry/pp-monthly-latest.parquet"
    context.log.info("Wrote clean Parquet at %s (stub)", clean_key)
    return clean_key


@dg.asset(group_name="land_registry")
def ppd_loaded_to_postgres(
    context: AssetExecutionContext, ppd_clean_parquet: str
) -> None:
    """Step 3: load the clean Parquet into the `land_registry_sales` table in Postgres.

    This is the end of the land_registry pipeline. EPC gets its own separate
    table; the two are reconciled later in dbt on a shared key (address/postcode).
    """
    # TODO: read ppd_clean_parquet and upsert into land_registry_sales via resources.postgres
    context.log.info("Loaded PPD into land_registry_sales (stub)")
