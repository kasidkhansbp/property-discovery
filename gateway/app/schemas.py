"""Response models for the coverage API.

These mirror the mart's columns (the four address dimensions plus the three
coverage metrics) and give the endpoints a typed, self-documenting shape in the
generated OpenAPI schema the frontend reads. All dimension fields are optional
because the mart carries NULL buckets for sales whose postcode was too short to
derive a prefix/country (see schema.postcode_prefix_sql).
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CoverageRow(BaseModel):
    """One pre-aggregated coverage bucket: a property type in an area, and its match rate."""

    property_type: str | None = Field(None, examples=["Flat/Maisonette"])
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
    """Distinct values available for each filter (property type + address).

    Lists cascade: each reflects the *other* filters currently applied, so the
    UI can narrow districts once a county is chosen, etc.
    """

    property_type: list[str]
    constituent_country: list[str]
    county: list[str]
    district: list[str]
    postcode_prefix: list[str]


class CoverageSummaryRow(BaseModel):
    """Sale totals for one value of the summary's grouping column."""

    value: str | None = Field(examples=["Flat/Maisonette"])
    total_land_registry_sales: int = Field(examples=[5012345])
    matched_uprn_count: int = Field(examples=[4210000])
    unmatched_count: int = Field(examples=[802345])
    coverage_percentage: float | None = Field(
        None, description="matched / total * 100, from the sums (NULL if total is 0)",
        examples=[83.99],
    )


class CoverageSummary(BaseModel):
    """Headline Sales -> UPRN coverage, grouped by one dimension, under the filters."""

    group_by: str = Field(examples=["property_type"])
    built_at: datetime | None = Field(
        None, description="When the mart snapshot was built (NULL if never built)"
    )
    total: CoverageSummaryRow = Field(description="All groups combined (value is NULL)")
    items: list[CoverageSummaryRow]


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


class PropertySearchResult(BaseModel):
    """Search results for one query box input, best matches first."""

    q: str = Field(description="The query as sent")
    mode: Literal["uprn", "postcode", "postcode_and_text", "text"] = Field(
        description=(
            "How the query was understood: a UPRN, a (partial) postcode, an "
            "address containing a full postcode, or free text"
        ),
        examples=["postcode"],
    )
    limit: int
    has_more: bool = Field(
        description="True when more rows match than were returned; refine the query"
    )
    items: list[PropertyRow]


# --------------------------------------------------------------------------- #
# Property history (one UPRN's sales and EPC certificates as a timeline).     #
# --------------------------------------------------------------------------- #
class SaleEvent(BaseModel):
    """One Land Registry sale linked to the UPRN by reconciliation."""

    kind: Literal["sale"] = "sale"
    date: Date | None = Field(None, description="transfer_date")
    transaction_id: str
    price: int | None = Field(None, examples=[540000])
    property_type: str | None = Field(None, description="D/S/T/F/O", examples=["T"])
    old_new: str | None = Field(None, description="Y = new build", examples=["N"])
    duration: str | None = Field(None, description="F = freehold, L = leasehold")
    saon: str | None = None
    paon: str | None = None
    street: str | None = None
    locality: str | None = None
    town_city: str | None = None
    postcode: str | None = None
    ppd_category: str | None = Field(None, description="A = standard, B = additional")
    match_type: str = Field(examples=["EXACT"])
    match_score: float = Field(examples=[1.0])


class EpcEvent(BaseModel):
    """One EPC certificate lodged for the UPRN."""

    kind: Literal["epc"] = "epc"
    date: Date | None = Field(None, description="lodgement_date")
    certificate_number: str
    inspection_date: Date | None = None
    current_energy_rating: str | None = Field(None, examples=["D"])
    potential_energy_rating: str | None = Field(None, examples=["B"])
    current_energy_efficiency: int | None = Field(None, examples=[61])
    potential_energy_efficiency: int | None = Field(None, examples=[84])
    property_type: str | None = None
    built_form: str | None = None
    total_floor_area: float | None = Field(None, examples=[112.0])
    construction_age_band: str | None = None
    tenure: str | None = None
    transaction_type: str | None = Field(None, examples=["marketed sale"])
    co2_emissions_current: float | None = None
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    postcode: str | None = None


HistoryEvent = Annotated[Union[SaleEvent, EpcEvent], Field(discriminator="kind")]


class PropertyHistory(BaseModel):
    """Every sale and EPC certificate for one UPRN, merged newest first."""

    uprn: int
    sale_count: int
    epc_count: int
    events: list[HistoryEvent]


# --------------------------------------------------------------------------- #
# EPC UPRN -> transaction coverage API (mart_epc_uprn_coverage).              #
# --------------------------------------------------------------------------- #
class EpcCoverageRow(BaseModel):
    """One mart group: EPC UPRNs with these attributes, and how many have a sale."""

    property_type: str = Field(examples=["Flat"])
    built_form: str = Field(examples=["Mid-Terrace"])
    tenure: str = Field(examples=["owner-occupied"])
    uprn_source: str = Field(examples=["Address Matched"])
    constituent_country: str = Field(examples=["England"])
    postcode_prefix: str | None = Field(
        None, description="NULL when the certificate's postcode is unusable",
        examples=["EX4"],
    )
    epc_uprns: int = Field(examples=[110])
    uprns_with_transaction: int = Field(examples=[10])
    uprns_without_transaction: int = Field(examples=[100])
    coverage_percentage: float = Field(examples=[9.09])


class EpcCoveragePage(BaseModel):
    """A filtered page of mart rows plus the unpaged row count."""

    total: int = Field(description="Mart rows matching the filters (ignores paging)")
    limit: int
    offset: int
    items: list[EpcCoverageRow]


class EpcCoverageSummaryRow(BaseModel):
    """Totals for one value of the summary's grouping column."""

    value: str | None = Field(examples=["Flat"])
    epc_uprns: int = Field(examples=[5252827])
    uprns_with_transaction: int = Field(examples=[2145314])
    uprns_without_transaction: int = Field(examples=[3107513])
    coverage_percentage: float | None = Field(
        None, description="with / total * 100, from the sums (NULL if total is 0)",
        examples=[40.84],
    )


class EpcCoverageSummary(BaseModel):
    """Headline coverage, grouped by one dimension, under the applied filters."""

    group_by: str = Field(examples=["property_type"])
    built_at: datetime | None = Field(
        None, description="When the mart snapshot was built (NULL if never built)"
    )
    total: EpcCoverageSummaryRow = Field(
        description="All groups combined (value is NULL)"
    )
    items: list[EpcCoverageSummaryRow]


class EpcCoverageFilterOptions(BaseModel):
    """Distinct values for each filter, cascading on the other applied filters."""

    property_type: list[str]
    built_form: list[str]
    tenure: list[str]
    uprn_source: list[str]
    constituent_country: list[str]
    postcode_prefix: list[str]
