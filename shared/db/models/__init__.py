"""All models, imported here so ``Base.metadata`` carries every table.

Alembic's ``env.py`` imports this package, so adding a model file and importing
it here is all that's needed for migrations to see a new table.
"""

from __future__ import annotations

from .epc_domestic_certificates import EpcDomesticCertificates
from .land_registry_sales import LandRegistrySales
from .mart_uprn_coverage_metrics import mart_uprn_coverage_metrics
from .os_open_uprn import OsOpenUprn, OsOpenUprnLoadState
from .properties import Properties
from .property_uprn_mapping import property_uprn_mapping
from .quality import (
    QUALITY_SOURCE_TABLES,
    key_duplication_quality,
    quality_tables,
)

__all__ = [
    "LandRegistrySales",
    "EpcDomesticCertificates",
    "OsOpenUprn",
    "OsOpenUprnLoadState",
    "Properties",
    "property_uprn_mapping",
    "mart_uprn_coverage_metrics",
    "quality_tables",
    "key_duplication_quality",
    "QUALITY_SOURCE_TABLES",
]
