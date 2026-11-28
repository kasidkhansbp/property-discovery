// The UPRN Coverage tab. Two views, switched at the top and kept in the URL
// (?view=epc) so a link opens the right one:
//
//   * Sales → UPRN (default) — filters + sortable 100-row table + pagination over
//     mart_uprn_coverage_metrics: of the Land Registry sales, how many found a UPRN.
//   * EPC UPRN → sales — EpcCoverageView, over mart_epc_uprn_coverage: of the EPC
//     UPRNs, how many have a sale, by property type.
//
// SalesCoverageView holds its query state (filters, sort, page) and wires it to
// the data hooks; the hooks handle caching and prefetch-ahead.

import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  COLUMN_LABELS,
  FILTER_COLUMNS,
  type Filters,
  type SortColumn,
  type SortDir,
} from "../api/coverage";
import { ApiError } from "../api/client";
import { FilterBar } from "../components/FilterBar";
import { CoverageTable } from "../components/CoverageTable";
import { Pagination } from "../components/Pagination";
import { useCoveragePage, useFilterOptions, PREFETCH_AHEAD } from "../hooks/useCoverage";
import { EpcCoverageView } from "./EpcCoverageView";

const VIEWS = [
  { id: "sales", label: "Sales → UPRN" },
  { id: "epc", label: "EPC UPRN → sales" },
] as const;
type ViewId = (typeof VIEWS)[number]["id"];

export function CoverageDashboard() {
  const [params, setParams] = useSearchParams();
  const view: ViewId = params.get("view") === "epc" ? "epc" : "sales";

  function selectView(next: ViewId) {
    setParams(next === "sales" ? {} : { view: next }, { replace: true });
  }

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>UPRN Coverage</h1>
        <div className="segmented" role="tablist" aria-label="Coverage view">
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              role="tab"
              aria-selected={view === v.id}
              className={`segmented__item${view === v.id ? " segmented__item--active" : ""}`}
              onClick={() => selectView(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
      </header>

      {view === "epc" ? <EpcCoverageView /> : <SalesCoverageView />}
    </div>
  );
}

function SalesCoverageView() {
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
    <>
      <p className="dashboard__subtitle">
        Land Registry → UPRN match rate per area · {PREFETCH_AHEAD} pages
        prefetched ahead
      </p>

      <FilterBar
        columns={FILTER_COLUMNS}
        labels={COLUMN_LABELS}
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
    </>
  );
}
