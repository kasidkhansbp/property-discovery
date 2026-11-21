"""properties table (one row per UPRN) and the pg_trgm extension

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21

Creates the empty ``properties`` table. It is filled once by
``services/jobs/ingestion/properties/build_properties.sql``; its search indexes
are created after the fill by ``create_properties_indexes.sql`` (building them on
a loaded table is much faster than maintaining them during a 40M-row insert).

``pg_trgm`` is enabled here because the address search index needs it.

On a fresh database, 0001 already builds every current model (including this
table) from the metadata, so the create is skipped when the table exists.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    if sa.inspect(op.get_bind()).has_table("properties"):
        return

    op.create_table(
        "properties",
        # autoincrement=False: UPRNs come from OS — no sequence/default.
        sa.Column("uprn", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("full_address", sa.Text),
        sa.Column("address_line_1", sa.Text),
        sa.Column("posttown", sa.Text),
        sa.Column("postcode", sa.Text),
        sa.Column("postcode_clean", sa.Text),
        sa.Column("country", sa.Text),
        sa.Column("property_type", sa.Text),
        sa.Column("built_form", sa.Text),
        sa.Column("uprn_source", sa.Text),
        sa.Column("address_source", sa.Text),
        sa.Column("search_text", sa.Text),
        sa.Column("latitude", sa.Double),
        sa.Column("longitude", sa.Double),
        sa.Column("x_coordinate", sa.Double),
        sa.Column("y_coordinate", sa.Double),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    # pg_trgm is left installed: other objects may come to depend on it.
    op.drop_table("properties")
