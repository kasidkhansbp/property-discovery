// The "EPC UPRN → sales" view of the UPRN Coverage tab, over mart_epc_uprn_coverage:
// of the UPRNs on EPC certificates, how many are linked to at least one Land
// Registry sale — headline split by property type, then a filterable table of
// the finer groups, biggest gaps first. The mart is rebuilt monthly; the header
// shows which snapshot is on screen.

import { useState } from "react";

import { ApiError } from "../api/client";
import {
  EPC_COLUMN_LABELS,
  EPC_FILTER_COLUMNS,
  type EpcFilters,
  type EpcSortColumn,
  type SortDir,
} from "../api/epcCoverage";
import { EpcCoverageCards } from "../components/EpcCoverageCards";
import { EpcCoverageTable } from "../components/EpcCoverageTable";
import { FilterBar } from "../components/FilterBar";
import { Pagination } from "../components/Pagination";
import { useEpcFilterOptions, useEpcRows, useEpcSummary } from "../hooks/useEpcCoverage";

const dateFmt = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" });

const COUNT_COLUMNS = new Set<EpcSortColumn>([
  "epc_uprns",
  "uprns_with_transaction",
  "uprns_without_transaction",
]);

function errorText(error: unknown) {
  return error instanceof ApiError ? `${error.message} (HTTP ${error.status})` : String(error);
}

export function EpcCoverageView() {
  const [filters, setFilters] = useState<EpcFilters>({});
  const [sortBy, setSortBy] = useState<EpcSortColumn>("uprns_without_transaction");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(0);

  // The cards always list every property type (so one can be added or removed
  // by clicking), so their totals ignore the property-type filter itself but
  // honour the others.
  const { property_type: selectedTypes = [], ...otherFilters } = filters;
  const summary = useEpcSummary(otherFilters, "property_type");
  const options = useEpcFilterOptions(filters);
  const rows = useEpcRows({ filters, sortBy, sortDir, page });

  function changeFilters(next: EpcFilters) {
    setFilters(next);
    setPage(0);
  }

  function toggleType(type: string) {
    const nextTypes = selectedTypes.includes(type)
      ? selectedTypes.filter((t) => t !== type)
      : [...selectedTypes, type];
    const next: EpcFilters = { ...filters };
    if (nextTypes.length) next.property_type = nextTypes;
    else delete next.property_type;
    changeFilters(next);
  }

  function changeSort(column: EpcSortColumn) {
    if (column === sortBy) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(column);
      // Counts read best biggest-first; coverage worst-first; text columns A→Z.
      setSortDir(COUNT_COLUMNS.has(column) ? "desc" : "asc");
    }
    setPage(0);
  }

  const builtAt = summary.data?.built_at;
  const neverBuilt = summary.isSuccess && !builtAt;
  const rowsStale = rows.isPlaceholderData || rows.isFetching;

  return (
    <>
      <p className="dashboard__subtitle">
        Share of UPRNs on EPC certificates that are linked to at least one Land
        Registry sale, by property type.
        {builtAt && <> Data as of {dateFmt.format(new Date(builtAt))}.</>}
      </p>

      {summary.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load the summary.</strong> {errorText(summary.error)}
          <button type="button" onClick={() => summary.refetch()}>
            Retry
          </button>
        </div>
      )}

      {neverBuilt ? (
        <div className="banner">
          No data yet — the monthly <code>mart_epc_uprn_coverage</code> build hasn’t run.
        </div>
      ) : (
        <>
          {summary.isLoading ? (
            <div className="banner">Loading summary…</div>
          ) : (
            summary.data && (
              <EpcCoverageCards
                items={summary.data.items}
                selected={selectedTypes}
                onToggle={toggleType}
                stale={summary.isPlaceholderData}
              />
            )
          )}

          <FilterBar
            columns={EPC_FILTER_COLUMNS}
            labels={EPC_COLUMN_LABELS}
            filters={filters}
            options={options.data}
            optionsLoading={options.isLoading}
            onChange={changeFilters}
          />

          {rows.isError && (
            <div className="banner banner--error" role="alert">
              <strong>Couldn’t load coverage rows.</strong> {errorText(rows.error)}
              <button type="button" onClick={() => rows.refetch()}>
                Retry
              </button>
            </div>
          )}

          {rows.isLoading && !rows.data ? (
            <div className="banner">Loading coverage…</div>
          ) : (
            <>
              <EpcCoverageTable
                rows={rows.data?.items ?? []}
                sortBy={sortBy}
                sortDir={sortDir}
                onSort={changeSort}
                stale={rowsStale}
              />
              <Pagination
                page={page}
                total={rows.data?.total ?? 0}
                onPageChange={setPage}
                busy={rowsStale}
              />
            </>
          )}
        </>
      )}
    </>
  );
}
