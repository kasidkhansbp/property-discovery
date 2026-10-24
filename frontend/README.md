# Frontend — Coverage Dashboard

A React + Vite + TypeScript UI over the [gateway](../gateway) API. It shows one
screen: **UPRN coverage per area**, read from `mart_uprn_coverage_metrics` via
the gateway's read-only endpoints.

## Features

- **Filtering** on the four address components (country / county / district /
  postcode prefix) with cascading, multi-select dropdowns backed by
  `GET /coverage-metrics/filter-options`.
- **Sorting** on any column (click a header; click again to flip direction).
- **Pagination at 100 rows per page** — the gateway's `DEFAULT_LIMIT`.
- **Prefetch ahead:** while you view a page, the next
  `PREFETCH_AHEAD` (= 4, within the requested 3–5) pages are fetched in the
  background and cached, so paging forward is instant. See
  [`src/hooks/useCoverage.ts`](src/hooks/useCoverage.ts).

## Run it

Start the gateway first (from the repo root, with `POSTGRES_DSN` set):

```bash
uvicorn gateway.app.main:app --reload   # serves http://127.0.0.1:8000
```

Then, from this `frontend/` directory:

```bash
npm install
cp .env.example .env      # optional; defaults to http://127.0.0.1:8000
npm run dev               # serves http://127.0.0.1:5173
```

`npm run build` type-checks and produces a production bundle in `dist/`;
`npm run typecheck` runs the type checker alone.

### Pointing at the API

`VITE_API_BASE_URL` sets the gateway origin (default `http://127.0.0.1:8000`).
Set it to `/api` to route through the Vite dev proxy
([`vite.config.ts`](vite.config.ts)) instead of relying on the gateway's CORS
config.

## Layout

| Path                              | Responsibility                                           |
| --------------------------------- | -------------------------------------------------------- |
| `src/api/client.ts`               | `fetch` wrapper: base URL, typed errors, JSON parsing.   |
| `src/api/coverage.ts`             | Typed endpoint calls + types mirroring the gateway.      |
| `src/hooks/useCoverage.ts`        | Paged query + **prefetch-ahead** + cascading options.    |
| `src/components/`                 | `FilterBar`, `MultiSelect`, `CoverageTable`, `Pagination`. |
| `src/pages/CoverageDashboard.tsx` | Composes the screen; owns filter/sort/page state.        |
