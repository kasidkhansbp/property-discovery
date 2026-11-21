"""properties search indexes (postcode prefix + address trigram)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21

Adds the two indexes ``GET /properties/search`` relies on. Until now they lived
only in ``create_properties_indexes.sql``, run by hand, so an environment could
end up without them. Prod did, and every search seq-scanned 41M rows and hit
the 3s timeout ("search too broad").

  * ``properties_postcode_clean_idx``: btree ``text_pattern_ops`` on
    ``postcode_clean``, for exact and prefix (``LIKE 'SW1A%'``) postcode search.
  * ``properties_search_text_trgm_idx``: GIN ``gin_trgm_ops`` on
    ``search_text``, for "contains" matches and similarity ranking.

Both are partial (``IS NOT NULL``): unaddressed UPRNs are never searched.

Built ``CONCURRENTLY`` (as in 0002) so the pre-deploy migration doesn't block
the live table, and ``IF NOT EXISTS`` so it is a no-op where the indexes were
already built by hand or by 0001 on a fresh database. On a loaded table the
trigram build takes many minutes. Prefer running create_properties_indexes.sql
in the Railway console first, so this deploy step finds them and does nothing.

A cancelled ``CREATE INDEX CONCURRENTLY`` leaves an INVALID index behind, which
``IF NOT EXISTS`` would silently accept. Any invalid copy is dropped first, so
re-running this migration repairs a failed build.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEXES: dict[str, str] = {
    "properties_postcode_clean_idx": (
        "ON properties (postcode_clean text_pattern_ops) "
        "WHERE postcode_clean IS NOT NULL"
    ),
    "properties_search_text_trgm_idx": (
        "ON properties USING gin (search_text gin_trgm_ops) "
        "WHERE search_text IS NOT NULL"
    ),
}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    bind = op.get_bind()
    with op.get_context().autocommit_block():
        for name, definition in _INDEXES.items():
            invalid = bind.exec_driver_sql(
                "SELECT 1 FROM pg_index "
                "WHERE indexrelid = to_regclass(%(name)s) AND NOT indisvalid",
                {"name": name},
            ).first()
            if invalid:
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} {definition}")
        op.execute("ANALYZE properties")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
