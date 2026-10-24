// The one screen: filters + sortable 100-row table + pagination, over
// mart_uprn_coverage_metrics. Holds the query state (filters, sort, page) and
// wires it to the data hooks; the hooks handle caching and prefetch-ahead.

import { useState } from "react";

import type { Filters, SortColumn, SortDir } from "../api/coverage";
import { ApiError } from "../api/client";
import { FilterBar } from "../components/FilterBar";
import { CoverageTable } from "../components/CoverageTable";
import { Pagination } from "../components/Pagination";
import { useCoveragePage, useFilterOptions, PREFETCH_AHEAD } from "../hooks/useCoverage";

export function CoverageDashboard() {
  const [filters, setFilters] = useState<Filters>({});
  const [sortBy, setSortBy] = useState<SortColumn>("coverage_percentage");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(0);

  const options = useFilterOptions(filters);
  const coverage = useCoveragePage({ filters, sortBy, sortDir, page });

  // Any change that alters the result set jumps back to the first page.
  function changeFilters(next: Filters) {
    setFilters(next);
    setPage(0);
  }

  function changeSort(column: SortColumn) {
    if (column === sortBy) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      setSortDir("asc");
    }
    setPage(0);
  }

  const data = coverage.data;
  const total = data?.total ?? 0;
  // keepPreviousData means we may be showing the prior page's rows mid-fetch.
  const stale = coverage.isPlaceholderData || coverage.isFetching;

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>UPRN Coverage</h1>
          <p className="dashboard__subtitle">
            Land Registry → UPRN match rate per area · {PREFETCH_AHEAD} pages
            prefetched ahead
          </p>
        </div>
      </header>

      <FilterBar
        filters={filters}
        options={options.data}
        optionsLoading={options.isLoading}
        onChange={changeFilters}
      />

      {coverage.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load coverage.</strong>{" "}
          {coverage.error instanceof ApiError
            ? `${coverage.error.message} (HTTP ${coverage.error.status})`
            : String(coverage.error)}
          <button type="button" onClick={() => coverage.refetch()}>
            Retry
          </button>
        </div>
      )}

      {coverage.isLoading && !data ? (
        <div className="banner">Loading coverage…</div>
      ) : (
        <>
          <CoverageTable
            rows={data?.items ?? []}
            sortBy={sortBy}
            sortDir={sortDir}
            onSort={changeSort}
            stale={stale}
          />
          <Pagination page={page} total={total} onPageChange={setPage} busy={stale} />
        </>
      )}
    </div>
  );
}
