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


# --------------------------------------------------------------------------- #
# Key-duplication / fan-out API (the key_duplication_quality table).          #
# --------------------------------------------------------------------------- #
class DuplicationRow(BaseModel):
    """One key-duplication check: how multiply-mapped a table's key column is."""

    source_table: str = Field(examples=["property_uprn_mapping"])
    key_column: str = Field(examples=["uprn"])
    total_rows: int = Field(
        description="Rows in the source table (NULL keys included)", examples=[4200110]
    )
    non_null_keys: int = Field(
        description="Rows carrying a non-NULL key", examples=[4100000]
    )
    distinct_keys: int = Field(
        description="Distinct non-NULL key values", examples=[3980002]
    )
    keys_with_duplicates: int = Field(
        description="Distinct keys appearing more than once", examples=[180004]
    )
    duplicate_rows: int = Field(
        description="Rows sharing a key with >=1 other row", examples=[400112]
    )
    max_rows_per_key: int = Field(
        description="Largest group size for any one key", examples=[14]
    )
    avg_rows_per_key: float | None = Field(
        None,
        description="non_null_keys / distinct_keys (NULL if there are no keys)",
        examples=[1.03],
    )
    checked_at: datetime


class DuplicationSummary(BaseModel):
    """Every key-duplication check, one row each."""

    items: list[DuplicationRow]


# --------------------------------------------------------------------------- #
# Properties API (the ``properties`` search table, one row per UPRN).         #
# --------------------------------------------------------------------------- #
class PropertyRow(BaseModel):
    """One UPRN: OS coordinates plus the address from its latest EPC certificate.

    Address/attribute fields are NULL for UPRNs that have no EPC certificate.
    """

    uprn: int = Field(examples=[100023336956])
    full_address: str | None = Field(
        None, examples=["10 DOWNING STREET, LONDON, SW1A 2AA"]
    )
    address_line_1: str | None = Field(None, examples=["10 DOWNING STREET"])
    posttown: str | None = Field(None, examples=["LONDON"])
    postcode: str | None = Field(None, examples=["SW1A 2AA"])
    postcode_clean: str | None = Field(None, examples=["SW1A2AA"])
    country: str | None = None
    property_type: str | None = Field(None, examples=["House"])
    built_form: str | None = Field(None, examples=["Mid-Terrace"])
    uprn_source: str | None = None
    address_source: str | None = Field(None, examples=["EPC"])
    latitude: float | None = None
    longitude: float | None = None
    x_coordinate: float | None = None
    y_coordinate: float | None = None
    updated_at: datetime


class PropertiesPage(BaseModel):
    """One page of properties, ordered by uprn."""

    total: int = Field(
        description="Row count of the whole table (planner estimate, see total_is_estimate)"
    )
    total_is_estimate: bool = Field(
        True, description="True: total comes from pg_class.reltuples, not count(*)"
    )
    limit: int
    after_uprn: int | None = Field(
        None, description="The keyset cursor this page was requested with, if any"
    )
    next_after_uprn: int | None = Field(
        None,
        description="Pass as after_uprn to fetch the next page; NULL on the last page",
    )
    items: list[PropertyRow]
