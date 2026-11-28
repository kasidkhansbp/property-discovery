// The UPRN Coverage tab. Two views, switched at the top and kept in the URL
// (?view=epc) so a link opens the right one:
//
//   * Sales → UPRN (default) — headline cards by property type, then filters +
//     sortable 100-row table + pagination over mart_uprn_coverage_metrics: of the
//     Land Registry sales, how many found a UPRN.
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
import { CoverageCards } from "../components/CoverageCards";
import { CoverageTable } from "../components/CoverageTable";
import { Pagination } from "../components/Pagination";
import { useCoveragePage, useCoverageSummary, useFilterOptions } from "../hooks/useCoverage";
import { EpcCoverageView } from "./EpcCoverageView";

const dateFmt = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });
const SALES_CARD_WORDING = { allLabel: "All LR sales", linkNoun: "a UPRN" };

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

  // The cards always list every property type (so one can be added or removed
  // by clicking), so their totals ignore the property-type filter itself but
  // honour the others.
  const { property_type: selectedTypes = [], ...otherFilters } = filters;
  const summary = useCoverageSummary(otherFilters, "property_type");
  const options = useFilterOptions(filters);
  const coverage = useCoveragePage({ filters, sortBy, sortDir, page });

  // Any change that alters the result set jumps back to the first page.
  function changeFilters(next: Filters) {
    setFilters(next);
    setPage(0);
  }

  function toggleType(type: string) {
    const nextTypes = selectedTypes.includes(type)
      ? selectedTypes.filter((t) => t !== type)
      : [...selectedTypes, type];
    const next: Filters = { ...filters };
    if (nextTypes.length) next.property_type = nextTypes;
    else delete next.property_type;
    changeFilters(next);
  }

  const builtAt = summary.data?.built_at;

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
        Share of Land Registry sales (transaction IDs) that are matched to a
        UPRN, by property type.
        {builtAt && <> Data as of {dateFmt.format(new Date(builtAt))}.</>}
      </p>

      {summary.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load the summary.</strong>{" "}
          {summary.error instanceof ApiError
            ? `${summary.error.message} (HTTP ${summary.error.status})`
            : String(summary.error)}
          <button type="button" onClick={() => summary.refetch()}>
            Retry
          </button>
        </div>
      )}

      {summary.isLoading ? (
        <div className="banner">Loading summary…</div>
      ) : (
        summary.data && (
          <CoverageCards
            items={summary.data.items.map((i) => ({
              value: i.value,
              total: i.total_land_registry_sales,
              matched: i.matched_uprn_count,
            }))}
            selected={selectedTypes}
            onToggle={toggleType}
            wording={SALES_CARD_WORDING}
            stale={summary.isPlaceholderData}
          />
        )
      )}

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
