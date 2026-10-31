"""One data-quality asset per served table.

Each asset profiles its source table into the matching ``<table>_quality``
companion (one coverage row per column) by calling the shared
``build_quality_metrics``. The ``deps`` on each source's load assets are lineage
only — they record that the quality snapshot is derived from that table's most
recent load; the check always re-reads the whole current table when it runs.
"""

import dagster as dg
from dagster import AssetExecutionContext

from .resources import PostgresResource
from .schema import (
    DUPLICATION_CHECKS,
    DUPLICATION_TABLE,
    EPC_TABLE,
    LR_TABLE,
    OS_OPEN_UPRN_TABLE,
    PUM_TABLE,
    QUALITY_SOURCES,
)
from .utils import build_duplication_metrics, build_quality_metrics

_LR = QUALITY_SOURCES[LR_TABLE]
_EPC = QUALITY_SOURCES[EPC_TABLE]
_OS = QUALITY_SOURCES[OS_OPEN_UPRN_TABLE]
_PUM = QUALITY_SOURCES[PUM_TABLE]

# The duplication table is derived from every source its checks touch, so it
# sits downstream of all of their loads (deduped union of the sources' lineage).
_DUP_DEPS = sorted({k for c in DUPLICATION_CHECKS for k in c.load_asset_keys})


@dg.asset(
    name=_LR.quality_table,
    group_name="data_quality",
    deps=[dg.AssetKey(k) for k in _LR.load_asset_keys],
)
def land_registry_sales_quality(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Per-column coverage of ``land_registry_sales``."""
    build_quality_metrics(context, postgres, _LR)


@dg.asset(
    name=_EPC.quality_table,
    group_name="data_quality",
    deps=[dg.AssetKey(k) for k in _EPC.load_asset_keys],
)
def epc_domestic_certificates_quality(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Per-column coverage of ``epc_domestic_certificates``."""
    build_quality_metrics(context, postgres, _EPC)


@dg.asset(
    name=_OS.quality_table,
    group_name="data_quality",
    deps=[dg.AssetKey(k) for k in _OS.load_asset_keys],
)
def os_open_uprn_quality(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Per-column coverage of ``os_open_uprn``."""
    build_quality_metrics(context, postgres, _OS)


@dg.asset(
    name=_PUM.quality_table,
    group_name="data_quality",
    deps=[dg.AssetKey(k) for k in _PUM.load_asset_keys],
)
def property_uprn_mapping_quality(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Per-column coverage of ``property_uprn_mapping``."""
    build_quality_metrics(context, postgres, _PUM)


@dg.asset(
    name=DUPLICATION_TABLE,
    group_name="data_quality",
    deps=[dg.AssetKey(k) for k in _DUP_DEPS],
)
def key_duplication_quality(
    context: AssetExecutionContext, postgres: PostgresResource
) -> None:
    """Cross-table key-duplication / fan-out metrics, one row per check.

    One small table answering: how many transaction_ids map to a uprn in
    ``property_uprn_mapping``, how many ``transaction_id`` values repeat in
    ``land_registry_sales``, and how many ``uprn`` values repeat in
    ``epc_domestic_certificates``.
    """
    build_duplication_metrics(context, postgres, DUPLICATION_TABLE, DUPLICATION_CHECKS)
