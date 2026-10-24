# data_quality

Per-table **coverage** profiling for the platform's served tables. For each
source table this service materialises a small companion table,
`<table>_quality`, holding **one row per source column** with how populated that
column is.

## Tables profiled

| Source table | Quality table | Refresh job |
|---|---|---|
| `land_registry_sales` | `land_registry_sales_quality` | `land_registry_sales_quality_job` |
| `epc_domestic_certificates` | `epc_domestic_certificates_quality` | `epc_domestic_certificates_quality_job` |
| `os_open_uprn` | `os_open_uprn_quality` | `os_open_uprn_quality_job` |
| `property_uprn_mapping` | `property_uprn_mapping_quality` | `property_uprn_mapping_quality_job` |

## What each quality table holds (one row per column)

| Column | Meaning |
|---|---|
| `column_name` | the source column this row describes (PK) |
| `data_type` | its Postgres type |
| `column_position` | source column order (for a stable sort) |
| `total_rows` | rows in the source table (same on every row) |
| `populated_count` | rows with a real value — not NULL, and for text not blank/whitespace |
| `null_count` | rows where the column IS NULL |
| `empty_string_count` | text columns only: non-NULL but blank/whitespace |
| `coverage_pct` | `populated_count / total_rows * 100`, rounded to 2 dp |
| `checked_at` | when the snapshot was taken |

"Quality" here is **coverage**: how much of each column is actually filled in.
`populated` treats a blank/whitespace text value the same as NULL (missing), so
`coverage_pct` is the share of rows carrying a usable value. Non-text columns
(dates, numbers, the UPRN bigint) have no blank-string state, so their
`empty_string_count` is always 0.

## Design

* **Column lists are not duplicated.** Each source's columns are imported from
  that service's own `schema.py` (`PPD_SCHEMA`, `EPC_SCHEMA`,
  `OS_OPEN_UPRN_SCHEMA`, and the reconciliation master columns), so adding a
  column to a source automatically profiles it here.
* **One scan per refresh.** `quality_metrics_select` aggregates the whole table
  once in a CTE, then unpivots that single aggregate row into one output row per
  column — so cost does not grow with column count.
* **Load-and-swap.** Each refresh fills a `*_new` table and drops-and-renames it
  into place in one transaction (the same pattern as
  `mart_uprn_coverage_metrics`), so readers never see a half-built table.
* **Postgres only.** The service reads tables already in Postgres and writes the
  companions back — no R2 or DuckDB round-trip. The SQL uses only functions
  Postgres and DuckDB share, so the tests exercise it on DuckDB.

## Schedules

Each job has a monthly schedule (24th, 09:00 — after the monthly loads, the
reconciliation refresh, and the coverage mart). All default to **STOPPED**; flip
them to RUNNING in the Dagster UI when ready.
