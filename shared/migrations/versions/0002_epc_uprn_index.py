"""index epc_domestic_certificates.uprn

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21

Adds a B-tree index on ``epc_domestic_certificates.uprn`` so the properties
refresh can look up specific UPRNs without scanning the whole table.

Built ``CONCURRENTLY`` so the deploy's pre-deploy migration does not block
reads or writes on the live table. ``CONCURRENTLY`` cannot run inside a
transaction, hence the ``autocommit_block``. ``IF NOT EXISTS`` makes it a no-op
where the index already exists (e.g. a fresh DB built by 0001 from the models).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS epc_domestic_certificates_uprn_idx "
            "ON epc_domestic_certificates (uprn)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS epc_domestic_certificates_uprn_idx")
