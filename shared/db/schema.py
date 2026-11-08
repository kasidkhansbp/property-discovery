"""Read-side schema constants, derived from the models.

The gateway reads the served/companion tables and needs their table names and
column lists — but it must not import the ingestion (``services``) package, which
pulls in Dagster/DuckDB/boto3. These constants come straight from the shared
models instead, so the gateway depends only on ``shared`` and can never drift
from the real tables.
"""

from __future__ import annotations

from typing import NamedTuple

from .models.mart_uprn_coverage_metrics import mart_uprn_coverage_metrics
from .models.quality import key_duplication_quality, quality_tables

# --- mart_uprn_coverage_metrics (coverage dashboard rollup) --- #
MART_TABLE: str = mart_uprn_coverage_metrics.name
MART_COLUMNS: list[str] = [c.name for c in mart_uprn_coverage_metrics.columns]
MART_GROUP_COLUMNS: list[str] = [
    c.name for c in mart_uprn_coverage_metrics.columns if c.info.get("group")
]

# --- per-table <source>_quality companions --- #
# Every quality table shares one shape, so take the column list from any of them.
_any_quality = next(iter(quality_tables.values()))
QUALITY_COLUMNS: list[str] = [c.name for c in _any_quality.columns]


class QualitySourceRef(NamedTuple):
    """The gateway's view of one profiled table: its name and companion table."""

    source_table: str
    quality_table: str

    @property
    def name(self) -> str:  # convenience alias
        return self.source_table


# {source_table: ref} — iteration order matches QUALITY_SOURCE_TABLES.
QUALITY_SOURCES: dict[str, QualitySourceRef] = {
    src: QualitySourceRef(src, tbl.name) for src, tbl in quality_tables.items()
}

# --- key_duplication_quality (cross-table fan-out checks) --- #
DUPLICATION_TABLE: str = key_duplication_quality.name
DUPLICATION_COLUMNS: list[str] = [c.name for c in key_duplication_quality.columns]
