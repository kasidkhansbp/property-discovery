"""Response models for the coverage API.

These mirror the mart's columns (the four address dimensions plus the three
coverage metrics) and give the endpoints a typed, self-documenting shape in the
generated OpenAPI schema the frontend reads. All dimension fields are optional
because the mart carries NULL buckets for sales whose postcode was too short to
derive a prefix/country (see schema.postcode_prefix_sql).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CoverageRow(BaseModel):
    """One pre-aggregated coverage bucket: an area and its match rate."""

    constituent_country: str | None = Field(None, examples=["England"])
    county: str | None = Field(None, examples=["DEVON"])
    district: str | None = Field(None, examples=["EXETER"])
    postcode_prefix: str | None = Field(None, examples=["EX4"])
    total_land_registry_sales: int = Field(examples=[1240])
    matched_uprn_count: int = Field(examples=[1115])
    coverage_percentage: float = Field(examples=[89.92])


class CoveragePage(BaseModel):
    """A filtered page of coverage rows plus the unpaged total for the filters."""

    total: int = Field(description="Total rows matching the filters (ignores paging)")
    limit: int
    offset: int
    items: list[CoverageRow]


class FilterOptions(BaseModel):
    """Distinct values available for each address-component filter.

    Lists cascade: each reflects the *other* filters currently applied, so the
    UI can narrow districts once a county is chosen, etc.
    """

    constituent_country: list[str]
    county: list[str]
    district: list[str]
    postcode_prefix: list[str]


# --------------------------------------------------------------------------- #
# Data-quality API (the per-table <table>_quality companions).                #
# --------------------------------------------------------------------------- #
class QualityColumnRow(BaseModel):
    """Coverage of one source column: how much of it is actually populated."""

    column_name: str = Field(examples=["postcode"])
    data_type: str = Field(examples=["text"])
    column_position: int = Field(examples=[4])
    total_rows: int = Field(examples=[31610742])
    populated_count: int = Field(examples=[31559950])
    null_count: int = Field(examples=[50792])
    empty_string_count: int = Field(examples=[0])
    coverage_pct: float | None = Field(
        None, description="populated / total * 100 (NULL only if the table is empty)"
    )
    checked_at: datetime


class QualityTable(BaseModel):
    """Every profiled column of one source table, plus the table-level context."""

    source_table: str = Field(examples=["land_registry_sales"])
    quality_table: str = Field(examples=["land_registry_sales_quality"])
    total_rows: int = Field(description="Rows in the source table")
    checked_at: datetime | None = Field(
        None, description="When this snapshot was taken (NULL if never built)"
    )
    columns: list[QualityColumnRow]


class QualitySummaryRow(BaseModel):
    """One profiled table's headline coverage, for the quality landing view."""

    source_table: str = Field(examples=["epc_domestic_certificates"])
    quality_table: str = Field(examples=["epc_domestic_certificates_quality"])
    total_rows: int
    columns_profiled: int
    average_coverage_pct: float | None = None
    worst_coverage_pct: float | None = None
    checked_at: datetime | None = None


class QualitySummary(BaseModel):
    """Headline coverage for every profiled table."""

    items: list[QualitySummaryRow]
