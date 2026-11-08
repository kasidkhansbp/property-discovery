"""Dagster assets for the EPC (Energy Performance Certificate) pipeline.

There are TWO chains, each its own download -> clean -> load trip:

  * complete  — the full bulk file (the domestic full-load ZIP). A one-off
                BACKFILL, launched manually (see the `epc_backfill_job` in
                schedules.py).
  * monthly   — the same bulk file re-processed on a monthly SCHEDULE to pick up
                newly-lodged certificates. EPC publishes no delta file, so this
                re-loads the bulk download and upserts; new certificates arrive
                with brand-new certificate numbers, so nothing is double-counted.

Both land in the same R2 bucket and load into the same `epc_domestic_certificates`
table, so run the backfill once, then let the monthly job keep it fresh.

The two chains run identical logic (it lives in utils.py) and differ only in
their object-key prefix and trigger — so both sets of assets are produced by a
single factory, `_build_epc_assets`, rather than written out twice. The schema
they share is defined once in schema.py.
"""

from datetime import datetime, timezone

import dagster as dg
from dagster import AssetExecutionContext

from .resources import EpcResource, PostgresResource, R2Resource
from .utils import clean_to_parquet, download_to_r2, load_to_postgres

# MHCLG "Get energy performance of buildings data" bulk download — the domestic
# full-load endpoint. Both chains pull this same file; the service gates it behind
# a bearer token (see EpcResource) and answers with a 302 to a presigned S3 URL
# for a ZIP of per-year certificate CSVs, which `requests` follows transparently.
EPC_DOMESTIC_URL = (
    "https://api.get-energy-performance-data.communities.gov.uk/api/files/domestic/csv"
)


def _stamp() -> str:
    """UTC date stamp used to partition raw/clean objects by run."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_epc_assets(
    chain: str, url: str
) -> tuple[dg.AssetsDefinition, dg.AssetsDefinition, dg.AssetsDefinition]:
    """Build the raw -> clean -> load asset trio for one EPC chain.

    `chain` ("complete" or "monthly") names the assets and keys the R2 object
    prefixes; `url` is the EPC bulk source. The three assets are wired raw ->
    clean -> load via explicit `AssetIn`s so the keys stay stable regardless of
    the Python parameter names.
    """

    @dg.asset(name=f"epc_{chain}_raw_zip", group_name="epc")
    def raw_zip(
        context: AssetExecutionContext, r2: R2Resource, epc: EpcResource
    ) -> str:
        """Step 1: stream the source ZIP into the R2 raw zone."""
        return download_to_r2(
            context, r2, epc, url, f"raw/epc/{chain}/{_stamp()}.zip"
        )

    @dg.asset(
        name=f"epc_{chain}_clean_parquet",
        group_name="epc",
        ins={"raw_zip": dg.AssetIn(f"epc_{chain}_raw_zip")},
    )
    def clean_parquet(
        context: AssetExecutionContext, r2: R2Resource, raw_zip: str
    ) -> str:
        """Step 2: extract the certificate CSVs and clean them into Parquet in R2."""
        return clean_to_parquet(
            context, r2, raw_zip, f"clean/epc/{chain}/{_stamp()}.parquet"
        )

    @dg.asset(
        name=f"epc_{chain}_loaded_to_postgres",
        group_name="epc",
        ins={"clean_parquet": dg.AssetIn(f"epc_{chain}_clean_parquet")},
    )
    def loaded_to_postgres(
        context: AssetExecutionContext,
        r2: R2Resource,
        postgres: PostgresResource,
        clean_parquet: str,
    ) -> None:
        """Step 3: upsert into epc_domestic_certificates (keyed on certificate_number)."""
        load_to_postgres(context, r2, postgres, clean_parquet)

    return raw_zip, clean_parquet, loaded_to_postgres


# --------------------------------------------------------------------------- #
# Chain 1: complete backfill (manually triggered, one-off full-file load).     #
# --------------------------------------------------------------------------- #
(
    epc_complete_raw_zip,
    epc_complete_clean_parquet,
    epc_complete_loaded_to_postgres,
) = _build_epc_assets("complete", EPC_DOMESTIC_URL)

# --------------------------------------------------------------------------- #
# Chain 2: monthly refresh (scheduled, keeps the table current after backfill).#
# Re-processes the bulk file; new certificates arrive as new LMK_KEYs.         #
# --------------------------------------------------------------------------- #
(
    epc_monthly_raw_zip,
    epc_monthly_clean_parquet,
    epc_monthly_loaded_to_postgres,
) = _build_epc_assets("monthly", EPC_DOMESTIC_URL)
