"""Dagster assets for the Land Registry Price Paid Data (PPD) pipeline.

There are TWO chains, each its own download -> clean -> load trip:

  * complete  — the full ~5GB history (pp-complete.csv). A one-off BACKFILL,
                launched manually (see the `ppd_backfill_job` in schedules.py).
  * monthly   — the small monthly delta (pp-monthly-update-new-version.csv),
                which carries Add/Change/Delete flags. Runs on the monthly
                SCHEDULE and keeps the table current after the backfill.

Both land in the same R2 bucket and load into the same `land_registry_sales`
table, so run the backfill once, then let the monthly job maintain it.

The two chains run identical logic (it lives in utils.py) and differ only in
their source URL, object-key prefix, and whether they apply deletes — so both
sets of assets are produced by a single factory, `_build_ppd_assets`, rather
than written out twice. The schema they share is defined once in schema.py.
"""

from datetime import datetime, timezone

import dagster as dg
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource
from .utils import clean_to_parquet, download_to_r2, load_to_postgres

# HMLR serves both files over plain HTTP from its public S3 website endpoint.
_HMLR_BASE = (
    "http://prod.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com"
)
# Full Price Paid Data — every transaction since 1995 (~5GB).
PPD_COMPLETE_URL = f"{_HMLR_BASE}/pp-complete.csv"
# Monthly delta — the "new version" carries Add(A)/Change(C)/Delete(D) flags.
PPD_MONTHLY_URL = f"{_HMLR_BASE}/pp-monthly-update-new-version.csv"


def _stamp() -> str:
    """UTC date stamp used to partition raw/clean objects by run."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_ppd_assets(
    chain: str, url: str, handle_deletes: bool
) -> tuple[dg.AssetsDefinition, dg.AssetsDefinition, dg.AssetsDefinition]:
    """Build the raw -> clean -> load asset trio for one PPD chain.

    `chain` ("complete" or "monthly") names the assets and keys the R2 object
    prefixes; `url` is the HMLR source; `handle_deletes` applies the delta's 'D'
    flags on load (monthly only). The three assets are wired raw -> clean ->
    load via explicit `AssetIn`s so the keys stay stable regardless of the
    Python parameter names.
    """

    @dg.asset(name=f"ppd_{chain}_raw_csv", group_name="land_registry")
    def raw_csv(context: AssetExecutionContext, r2: R2Resource) -> str:
        """Step 1: stream the source CSV into the R2 raw zone."""
        return download_to_r2(
            context, r2, url, f"raw/land_registry/{chain}/{_stamp()}.csv"
        )

    @dg.asset(
        name=f"ppd_{chain}_clean_parquet",
        group_name="land_registry",
        ins={"raw_csv": dg.AssetIn(f"ppd_{chain}_raw_csv")},
    )
    def clean_parquet(
        context: AssetExecutionContext, r2: R2Resource, raw_csv: str
    ) -> str:
        """Step 2: clean the CSV into Parquet in R2."""
        return clean_to_parquet(
            context, r2, raw_csv, f"clean/land_registry/{chain}/{_stamp()}.parquet"
        )

    @dg.asset(
        name=f"ppd_{chain}_loaded_to_postgres",
        group_name="land_registry",
        ins={"clean_parquet": dg.AssetIn(f"ppd_{chain}_clean_parquet")},
    )
    def loaded_to_postgres(
        context: AssetExecutionContext,
        r2: R2Resource,
        postgres: PostgresResource,
        clean_parquet: str,
    ) -> None:
        """Step 3: upsert into land_registry_sales (applying deletes for monthly)."""
        load_to_postgres(
            context, r2, postgres, clean_parquet, handle_deletes=handle_deletes
        )

    return raw_csv, clean_parquet, loaded_to_postgres


# --------------------------------------------------------------------------- #
# Chain 1: complete backfill (manually triggered, one-off ~5GB load).         #
# No delete handling — the complete file is a pure snapshot (all 'A' rows).    #
# --------------------------------------------------------------------------- #
(
    ppd_complete_raw_csv,
    ppd_complete_clean_parquet,
    ppd_complete_loaded_to_postgres,
) = _build_ppd_assets("complete", PPD_COMPLETE_URL, handle_deletes=False)

# --------------------------------------------------------------------------- #
# Chain 2: monthly delta (scheduled, keeps the table current after backfill).  #
# Adds/changes are upserted; rows flagged 'D' are deleted.                     #
# --------------------------------------------------------------------------- #
(
    ppd_monthly_raw_csv,
    ppd_monthly_clean_parquet,
    ppd_monthly_loaded_to_postgres,
) = _build_ppd_assets("monthly", PPD_MONTHLY_URL, handle_deletes=True)
