"""Model for ``epc_domestic_certificates`` — MHCLG EPC domestic certificates.

The useful projection of the ~90-column source CSV. Each column's ``info``
carries the source header (``csv_name``), the DuckDB cast (``csv_type``) and the
cleaning rule; ``services.jobs.ingestion.epc.schema`` builds ``EPC_SCHEMA`` from
this model.
"""

from __future__ import annotations

from sqlalchemy import Index

from ..base import Base
from ..columns import pg_column


def _text(nullif_empty: bool = False, **kw):
    return pg_column("text", csv_type="VARCHAR", nullif_empty=nullif_empty, **kw)


class EpcDomesticCertificates(Base):
    __tablename__ = "epc_domestic_certificates"

    # "certificate_number" — unique certificate reference number; natural PK.
    certificate_number = pg_column(
        "text PRIMARY KEY", csv_type="VARCHAR", csv_name="certificate_number"
    )
    uprn = _text(True, csv_name="uprn")
    uprn_source = _text(True, csv_name="uprn_source")
    address1 = _text(True, csv_name="address1")
    address2 = _text(True, csv_name="address2")
    address3 = _text(True, csv_name="address3")
    posttown = _text(True, csv_name="posttown")
    postcode = _text(True, csv_name="postcode")
    local_authority = _text(True, csv_name="local_authority")
    local_authority_label = _text(True, csv_name="local_authority_label")
    constituency = _text(True, csv_name="constituency")
    region = _text(True, csv_name="region")
    country = _text(True, csv_name="country")
    property_type = _text(True, csv_name="property_type")
    built_form = _text(True, csv_name="built_form")
    construction_age_band = _text(True, csv_name="construction_age_band")
    tenure = _text(True, csv_name="tenure")
    transaction_type = _text(True, csv_name="transaction_type")
    total_floor_area = pg_column(
        "double precision", csv_type="DOUBLE", csv_name="total_floor_area"
    )
    current_energy_rating = _text(True, csv_name="current_energy_rating")
    potential_energy_rating = _text(True, csv_name="potential_energy_rating")
    current_energy_efficiency = pg_column(
        "integer", csv_type="INTEGER", csv_name="current_energy_efficiency"
    )
    potential_energy_efficiency = pg_column(
        "integer", csv_type="INTEGER", csv_name="potential_energy_efficiency"
    )
    co2_emissions_current = pg_column(
        "double precision", csv_type="DOUBLE", csv_name="co2_emissions_current"
    )
    co2_emissions_potential = pg_column(
        "double precision", csv_type="DOUBLE", csv_name="co2_emissions_potential"
    )
    inspection_date = pg_column("date", csv_type="DATE", csv_name="inspection_date")
    lodgement_date = pg_column("date", csv_type="DATE", csv_name="lodgement_date")

    __table_args__ = (
        Index("epc_domestic_certificates_postcode_idx", "postcode"),
        # Lets the properties refresh look up specific UPRNs without a full scan.
        Index("epc_domestic_certificates_uprn_idx", "uprn"),
    )
