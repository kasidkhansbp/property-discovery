"""Model for ``properties`` — the search table, one row per UPRN.

Every UPRN in ``os_open_uprn`` gets a row (with its coordinates). The address and
property attributes come from the latest EPC certificate for that UPRN (by
``lodgement_date``); UPRNs with no EPC certificate keep NULL address fields.
Address text is upper-cased and whitespace-cleaned; ``postcode_clean`` and
``search_text`` are the normalised forms the search indexes are built on.

Built by ``services/jobs/ingestion/properties/build_properties.sql``.
"""

from __future__ import annotations

from sqlalchemy import DateTime, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..columns import pg_column


class Properties(Base):
    __tablename__ = "properties"

    # os_open_uprn
    uprn = pg_column("bigint PRIMARY KEY", autoincrement=False)  # from OS, never generated
    # Address, from the latest EPC certificate — upper-cased, spaces collapsed.
    full_address = pg_column("text")  # address_line_1, posttown, postcode
    address_line_1 = pg_column("text")  # address1, address2, address3 joined
    posttown = pg_column("text")
    postcode = pg_column("text")  # as published, e.g. 'SW1A 1AA'
    postcode_clean = pg_column("text")  # no spaces, e.g. 'SW1A1AA'
    # EPC attributes, as published.
    country = pg_column("text")
    property_type = pg_column("text")
    built_form = pg_column("text")
    uprn_source = pg_column("text")
    # Which table the address came from ('EPC'), NULL when there is none.
    address_source = pg_column("text")
    # full_address with punctuation removed — what address search matches on.
    search_text = pg_column("text")
    # os_open_uprn coordinates.
    latitude = pg_column("double precision")
    longitude = pg_column("double precision")
    x_coordinate = pg_column("double precision")
    y_coordinate = pg_column("double precision")
    # When this row's data was last written.
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        info={"pg_type": "timestamptz NOT NULL DEFAULT now()"},
    )
