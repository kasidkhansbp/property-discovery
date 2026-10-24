# Gateway — Coverage API

A thin, read-only HTTP layer over the serving database. It owns no business
logic and no copy of the schema: the columns it filters, sorts, and returns are
imported from the owning service
(`services/ingestion/reconciliation/schema.py`), so they can't drift.

The first resource it exposes is **`mart_uprn_coverage_metrics`** — UPRN match
coverage pre-aggregated to one row per area.

## Run it

From the repo root (so `services.ingestion.*` imports resolve, as with Dagster),
with the serving DB's `POSTGRES_DSN` set in the environment or repo `.env`:

```bash
python -m pip install -r requirements.txt
uvicorn gateway.app.main:app --reload
```

Interactive OpenAPI docs: <http://127.0.0.1:8000/docs>.

## Endpoints

### `GET /coverage-metrics`

A filtered, sorted, paginated page of the mart.

**Filters — the four address components (each repeatable = multi-select):**

| Query param           | Mart column           | Example         |
| --------------------- | --------------------- | --------------- |
| `constituent_country` | `constituent_country` | `England`       |
| `county`              | `county`              | `DEVON`         |
| `district`            | `district`            | `EXETER`        |
| `postcode_prefix`     | `postcode_prefix`     | `EX4`           |

These four — and only these four — are the UI filter fields; they are the mart's
grouping dimensions (`MART_GROUP_COLUMNS`). The other three columns
(`total_land_registry_sales`, `matched_uprn_count`, `coverage_percentage`) are
metrics, surfaced as outputs and as `sort_by` keys rather than filters. Matching
is case-insensitive.

**Paging & sort:** `limit` (1–1000, default 100), `offset` (default 0),
`sort_by` (any mart column, default `coverage_percentage`), `sort_dir`
(`asc`/`desc`, default `asc` → worst-covered areas first).

```bash
# Exeter + Cornwall, England only, worst coverage first:
curl 'http://127.0.0.1:8000/coverage-metrics?constituent_country=England&county=DEVON&county=CORNWALL&sort_by=coverage_percentage&sort_dir=asc'
```

Response: `{ total, limit, offset, items: [CoverageRow, ...] }`.

### `GET /coverage-metrics/filter-options`

The distinct values to populate each dropdown. The lists **cascade**: pass the
filters already chosen and each column's options narrow to what's still
reachable (a column is never narrowed by its own selection), so picking a county
shrinks the district/prefix lists.

```bash
curl 'http://127.0.0.1:8000/coverage-metrics/filter-options?constituent_country=Wales'
```

## Design notes

- `gateway/app/query.py` holds **pure** `(sql, params)` builders — no FastAPI,
  no DB handle — so the whole filter/sort/paginate surface is unit-tested
  without Postgres (`tests/gateway/test_query.py`), the same way the mart's
  aggregation SQL is.
- Column identifiers are whitelisted against the schema; request values are
  always bound parameters. No request string ever reaches the SQL text.
- Connections come from a `psycopg_pool` pool opened in the app lifespan.
