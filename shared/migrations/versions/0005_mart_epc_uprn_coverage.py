"""mart_epc_uprn_coverage (EPC UPRN -> transaction coverage by property type)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-27

Creates the empty mart so the gateway's /epc-uprn-coverage endpoints return an
empty result (rather than a missing-table error) before the first Dagster run.
The reconciliation asset ``mart_epc_uprn_coverage`` fills it, replacing the
table wholesale each month (load-and-swap), and recreates the index each time.

On a fresh database, 0001 already builds every current model (including this
table) from the metadata, so the create is skipped when the table exists.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mart_epc_uprn_coverage"


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table(_TABLE):
        return

    op.create_table(
        _TABLE,
        sa.Column("property_type", sa.Text),
        sa.Column("built_form", sa.Text),
        sa.Column("tenure", sa.Text),
        sa.Column("uprn_source", sa.Text),
        sa.Column("constituent_country", sa.Text),
        sa.Column("postcode_prefix", sa.Text),
        sa.Column("epc_uprns", sa.BigInteger),
        sa.Column("uprns_with_transaction", sa.BigInteger),
        sa.Column("uprns_without_transaction", sa.BigInteger),
        sa.Column("coverage_percentage", sa.Numeric),
        sa.Column("built_at", sa.DateTime(timezone=True)),
    )
    op.create_index("mart_epc_uprn_coverage_type_idx", _TABLE, ["property_type"])


def downgrade() -> None:
    op.drop_table(_TABLE)
