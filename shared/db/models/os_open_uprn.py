"""Models for ``os_open_uprn`` and its singleton ``os_open_uprn_load_state``.

``os_open_uprn`` is the OS Open UPRN reference table (one row per UPRN with its
coordinates); ``services.jobs.ingestion.os_open_uprn.schema`` builds
``OS_OPEN_UPRN_SCHEMA`` from the model. ``os_open_uprn_load_state`` is a one-row
bookkeeping table recording the md5 of the last release that loaded, so an
unchanged release can be skipped before download.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..columns import pg_column


class OsOpenUprn(Base):
    __tablename__ = "os_open_uprn"

    # OS "UPRN" — the Unique Property Reference Number; natural PK (fits bigint).
    uprn = pg_column("bigint PRIMARY KEY", csv_type="BIGINT", csv_name="UPRN")
    # Eastings/northings on the British National Grid (EPSG:27700), in metres.
    x_coordinate = pg_column(
        "double precision", csv_type="DOUBLE", csv_name="X_COORDINATE"
    )
    y_coordinate = pg_column(
        "double precision", csv_type="DOUBLE", csv_name="Y_COORDINATE"
    )
    # WGS84 (EPSG:4326) latitude/longitude, in degrees.
    latitude = pg_column("double precision", csv_type="DOUBLE", csv_name="LATITUDE")
    longitude = pg_column("double precision", csv_type="DOUBLE", csv_name="LONGITUDE")


class OsOpenUprnLoadState(Base):
    __tablename__ = "os_open_uprn_load_state"

    # The CHECK + single-value PK pin the table to one row (the md5 is upserted).
    singleton: Mapped[bool] = mapped_column(
        Boolean, primary_key=True, server_default=text("true")
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    md5: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rows_total: Mapped[int] = mapped_column(BigInteger, nullable=False)
    loaded_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint("singleton", name="os_open_uprn_load_state_singleton_check"),
    )
