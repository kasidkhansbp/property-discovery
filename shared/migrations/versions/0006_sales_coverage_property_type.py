"""mart_uprn_coverage_metrics: add property_type + built_at

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-28

The Sales -> UPRN dashboard now shows headline cards per Land Registry property
type and the snapshot's build date, so the mart gains a ``property_type``
grouping column, a ``built_at`` timestamp, and an index on ``property_type``.

The reconciliation asset ``mart_uprn_coverage_metrics`` rebuilds the table
wholesale (load-and-swap) with the new columns in model order, so this migration
only has to make the *existing* table match until that next rebuild: rows already
there keep a NULL property_type / built_at until then. On a fresh database, 0001
builds every current model from the metadata, so each step is skipped when the
column / index already exists.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "mart_uprn_coverage_metrics"
_INDEX = "mart_uprn_coverage_metrics_type_idx"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(_TABLE):
        return
    columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if "property_type" not in columns:
        op.add_column(_TABLE, sa.Column("property_type", sa.Text))
    if "built_at" not in columns:
        op.add_column(_TABLE, sa.Column("built_at", sa.DateTime(timezone=True)))
    if _INDEX not in {i["name"] for i in inspector.get_indexes(_TABLE)}:
        op.create_index(_INDEX, _TABLE, ["property_type"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE, if_exists=True)
    op.drop_column(_TABLE, "built_at")
    op.drop_column(_TABLE, "property_type")
