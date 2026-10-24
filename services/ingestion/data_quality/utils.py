"""The build step behind every ``<table>_quality`` asset.

One generic function profiles any served table into its quality companion: it
runs ``quality_metrics_select`` (one scan, one row per column) into a fresh
table and swaps it into place. The logic is identical for all four sources —
only the ``QualitySource`` passed in changes — so it lives here once and each
asset is a one-line wrapper.
"""

from __future__ import annotations

from dagster import AssetExecutionContext

from .resources import PostgresResource
from .schema import (
    QUALITY_COLUMNS,
    QUALITY_PG_DDL_COLS,
    QualitySource,
    quality_metrics_select,
)


def build_quality_metrics(
    context: AssetExecutionContext, postgres: PostgresResource, source: QualitySource
) -> None:
    """Rebuild ``<source>_quality`` with one coverage row per source column.

    The build is load-and-swap, mirroring the coverage mart: fill a fresh
    ``*_new`` table from ``quality_metrics_select``, then drop-and-rename it into
    place inside one transaction. Readers keep seeing the previous snapshot until
    the rename commits, so a refresh never exposes a half-built or empty table.
    The aggregation runs entirely in Postgres (the source table is already
    there and the result is tiny — one row per column), so there is no DuckDB or
    object-storage round-trip.
    """
    quality_table = source.quality_table
    new_table = f"{quality_table}_new"
    cols = ", ".join(QUALITY_COLUMNS)
    select_sql = quality_metrics_select(source.source_table, source.columns)

    with postgres.connect() as conn, conn.cursor() as cur:
        context.log.info(
            "Building %s from %s (%d columns)",
            quality_table,
            source.source_table,
            len(source.columns),
        )
        # Build the next snapshot off to the side with the fixed quality DDL.
        cur.execute(f"DROP TABLE IF EXISTS {new_table};")
        cur.execute(f"CREATE TABLE {new_table} (\n    {QUALITY_PG_DDL_COLS}\n);")
        cur.execute(f"INSERT INTO {new_table} ({cols})\n{select_sql};")
        columns_checked = cur.rowcount  # one inserted row per source column

        # Atomic swap: readers see the old quality table until this commits.
        cur.execute(f"DROP TABLE IF EXISTS {quality_table};")
        cur.execute(f"ALTER TABLE {new_table} RENAME TO {quality_table};")

        # Headline figures for the run's metadata (and a quick sanity check).
        cur.execute(
            f"SELECT coalesce(max(total_rows), 0), "
            f"       round(avg(coverage_pct), 2), "
            f"       min(coverage_pct) "
            f"FROM {quality_table};"
        )
        total_rows, avg_coverage, min_coverage = cur.fetchone()
        conn.commit()

    # Postgres returns bigint as int already and numeric as Decimal; coerce the
    # coverage figures to plain floats so the metadata is JSON-friendly. They are
    # NULL only when the source table is empty (no rows to average over).
    total_rows = int(total_rows)
    avg_coverage = float(avg_coverage) if avg_coverage is not None else None
    min_coverage = float(min_coverage) if min_coverage is not None else None

    context.log.info(
        "Built %s: %s column(s) over %s row(s); avg coverage %s%%, worst %s%%",
        quality_table,
        columns_checked,
        total_rows,
        avg_coverage,
        min_coverage,
    )
    context.add_output_metadata(
        {
            "quality_table": quality_table,
            "source_table": source.source_table,
            "columns_checked": columns_checked,
            "total_rows": total_rows,
            "average_coverage_pct": avg_coverage,
            "worst_column_coverage_pct": min_coverage,
        }
    )
