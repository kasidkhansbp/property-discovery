// Typed access to the /epc-uprn-coverage endpoints. Mirrors gateway/app/schemas.py
// (EpcCoverage*) and the filter/sort contract in gateway/app/epc_coverage_query.py.
// Caching lives in the hook layer (src/hooks/useEpcCoverage.ts).

import { apiGet } from "./client";

// The six filterable dimensions, in the mart's order (property type leads).
export const EPC_FILTER_COLUMNS = [
  "property_type",
  "built_form",
  "tenure",
  "uprn_source",
  "constituent_country",
  "postcode_prefix",
] as const;
export type EpcFilterColumn = (typeof EPC_FILTER_COLUMNS)[number];
export type EpcFilters = Partial<Record<EpcFilterColumn, string[]>>;

export const EPC_SORTABLE_COLUMNS = [
  ...EPC_FILTER_COLUMNS,
  "epc_uprns",
  "uprns_with_transaction",
  "uprns_without_transaction",
  "coverage_percentage",
] as const;
export type EpcSortColumn = (typeof EPC_SORTABLE_COLUMNS)[number];
export type SortDir = "asc" | "desc";

export const EPC_COLUMN_LABELS: Record<EpcSortColumn, string> = {
  property_type: "Property type",
  built_form: "Built form",
  tenure: "Tenure",
  uprn_source: "UPRN source",
  constituent_country: "Country",
  postcode_prefix: "Postcode",
  epc_uprns: "EPC UPRNs",
  uprns_with_transaction: "With sale",
  uprns_without_transaction: "Without sale",
  coverage_percentage: "Coverage %",
};

export interface EpcCoverageRow {
  property_type: string;
  built_form: string;
  tenure: string;
  uprn_source: string;
  constituent_country: string;
  postcode_prefix: string | null;
  epc_uprns: number;
  uprns_with_transaction: number;
  uprns_without_transaction: number;
  coverage_percentage: number;
}

export interface EpcCoveragePage {
  total: number;
  limit: number;
  offset: number;
  items: EpcCoverageRow[];
}

export interface EpcSummaryRow {
  value: string | null;
  epc_uprns: number;
  uprns_with_transaction: number;
  uprns_without_transaction: number;
  coverage_percentage: number | null;
}

export interface EpcSummary {
  group_by: EpcFilterColumn;
  built_at: string | null;
  total: EpcSummaryRow;
  items: EpcSummaryRow[];
}

export type EpcFilterOptions = Record<EpcFilterColumn, string[]>;

export interface EpcRowsQuery {
  filters: EpcFilters;
  sortBy: EpcSortColumn;
  sortDir: SortDir;
  limit: number;
  offset: number;
}

function filtersToParams(filters: EpcFilters): URLSearchParams {
  const params = new URLSearchParams();
  for (const column of EPC_FILTER_COLUMNS) {
    for (const value of filters[column] ?? []) params.append(column, value);
  }
  return params;
}

/** Totals grouped by one dimension (GET /epc-uprn-coverage/summary). */
export function fetchEpcSummary(
  filters: EpcFilters,
  groupBy: EpcFilterColumn,
  signal?: AbortSignal,
): Promise<EpcSummary> {
  const params = filtersToParams(filters);
  params.set("group_by", groupBy);
  return apiGet<EpcSummary>("/epc-uprn-coverage/summary", params, signal);
}

/** One filtered/sorted/paginated page of mart rows (GET /epc-uprn-coverage). */
export function fetchEpcRows(
  query: EpcRowsQuery,
  signal?: AbortSignal,
): Promise<EpcCoveragePage> {
  const params = filtersToParams(query.filters);
  params.set("sort_by", query.sortBy);
  params.set("sort_dir", query.sortDir);
  params.set("limit", String(query.limit));
  params.set("offset", String(query.offset));
  return apiGet<EpcCoveragePage>("/epc-uprn-coverage", params, signal);
}

/** Cascading dropdown values (GET /epc-uprn-coverage/filter-options). */
export function fetchEpcFilterOptions(
  filters: EpcFilters,
  signal?: AbortSignal,
): Promise<EpcFilterOptions> {
  return apiGet<EpcFilterOptions>(
    "/epc-uprn-coverage/filter-options",
    filtersToParams(filters),
    signal,
  );
}
