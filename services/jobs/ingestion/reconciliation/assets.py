"""Dagster assets for the Land Registry <-> EPC UPRN reconciliation pipeline.

Like the other ingestion services there are TWO chains, each a normalize ->
build -> load trip that produces the ``property_uprn_mapping`` bridge table:

  * full         — rebuild the whole table from scratch. A one-off, launched
                   manually once the land_registry and epc backfills have landed
                   (see ``reconciliation_full_job`` in schedules.py).
  * incremental  — refresh after a monthly Land Registry delta. Runs on the
                   monthly SCHEDULE and PROTECTS transaction_ids already decided
                   (it never re-scores or overwrites them); it only matches the
                   new transactions and refreshes the unmatched-UPRN coverage.

Both chains run identical logic (it lives in utils.py) and differ only in their
object-key prefix and whether they rebuild or protect — so both sets of assets
come from a single factory, ``_build_reconciliation_assets``, rather than being
written out twice. The master table schema is defined once in schema.py.
"""

from datetime import datetime, timezone

import dagster as dg
from dagster import AssetExecutionContext

from .resources import PostgresResource, R2Resource
from .utils import (
    build_coverage_metrics,
    build_master_parquet,
    load_master,
    normalize_sources,
)


def _stamp() -> str:
    """UTC date stamp used to partition the run's R2 objects."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_reconciliation_assets(
    chain: str, incremental: bool
) -> tuple[dg.AssetsDefinition, dg.AssetsDefinition, dg.AssetsDefinition]:
    """Build the normalize -> master -> load asset trio for one chain.

    ``chain`` ("full" or "incremental") names the assets and keys the R2 object
    prefixes; ``incremental`` switches on both "protect existing matches" in the
    build and the non-destructive upsert in the load. The three assets are wired
    together via explicit ``AssetIn``s so the keys stay stable regardless of the
    Python parameter names.
    """

    @dg.asset(name=f"reconciliation_{chain}_normalized", group_name="reconciliation")
    def normalized(
        context: AssetExecutionContext, r2: R2Resource, postgres: PostgresResource
    ) -> dict[str, str]:
        """Step A: standardise the join keys on both sources into R2 Parquet."""
        stamp = _stamp()
        return normalize_sources(
            context,
            r2,
            postgres,
            lr_key=f"clean/reconciliation/{chain}/{stamp}/lr.parquet",
            epc_key=f"clean/reconciliation/{chain}/{stamp}/epc.parquet",
        )

    @dg.asset(
        name=f"reconciliation_{chain}_master_parquet",
        group_name="reconciliation",
        ins={"normalized": dg.AssetIn(f"reconciliation_{chain}_normalized")},
    )
    def master_parquet(
        context: AssetExecutionContext,
        r2: R2Resource,
        postgres: PostgresResource,
        normalized: dict[str, str],
    ) -> str:
        """Steps B/C/D: exact + fuzzy match, then full-coverage assembly."""
        return build_master_parquet(
            context,
            r2,
            postgres,
            lr_key=normalized["lr"],
            epc_key=normalized["epc"],
            master_key=f"clean/reconciliation/{chain}/{_stamp()}/master.parquet",
            incremental=incremental,
        )

    @dg.asset(
        name=f"reconciliation_{chain}_loaded_to_postgres",
        group_name="reconciliation",
        ins={"master_parquet": dg.AssetIn(f"reconciliation_{chain}_master_parquet")},
    )
    def loaded_to_postgres(
        context: AssetExecutionContext,
        r2: R2Resource,
        postgres: PostgresResource,
        master_parquet: str,
    ) -> None:
        """Load the master Parquet into property_uprn_mapping."""
        load_master(context, r2, postgres, master_parquet, incremental=incremental)

    return normalized, master_parquet, loaded_to_postgres


# --------------------------------------------------------------------------- #
# Chain 1: full rebuild (manually triggered, replaces the whole table).       #
# --------------------------------------------------------------------------- #
(
    reconciliation_full_normalized,
    reconciliation_full_master_parquet,
    reconciliation_full_loaded_to_postgres,
) = _build_reconciliation_assets("full", incremental=False)

# --------------------------------------------------------------------------- #
# Chain 2: incremental refresh (scheduled; protects already-decided matches). #
# --------------------------------------------------------------------------- #
(
    reconciliation_incremental_normalized,
    reconciliation_incremental_master_parquet,
    reconciliation_incremental_loaded_to_postgres,
) = _build_reconciliation_assets("incremental", incremental=True)


# --------------------------------------------------------------------------- #
# Downstream mart: pre-aggregated UPRN coverage metrics.                      #
# --------------------------------------------------------------------------- #
# Reads the loaded property_uprn_mapping bridge and rolls it up into the small,
# dashboard-facing mart_uprn_coverage_metrics table. It has its OWN job/schedule
# (mart_coverage_metrics_job) rather than riding the reconciliation jobs, so the
# rollup can be rebuilt on its own without re-reconciling. The deps on both load
# chains are lineage only — they record that the mart is derived from either
# bridge build; the mart always re-reads the whole current bridge when it runs.
@dg.asset(
    name="mart_uprn_coverage_metrics",
    group_name="reconciliation",
    deps=[
        dg.AssetKey("reconciliation_full_loaded_to_postgres"),
        dg.AssetKey("reconciliation_incremental_loaded_to_postgres"),
    ],
)
def mart_uprn_coverage_metrics(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Pre-aggregate coverage stats from the bridge into the serving mart."""
    build_coverage_metrics(context, postgres)
