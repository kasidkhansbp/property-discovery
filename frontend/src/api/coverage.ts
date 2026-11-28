// Typed access to the coverage endpoints. Mirrors gateway/app/schemas.py and the
// filter/sort contract in gateway/app/query.py, so the UI and the API stay in
// lock-step. These functions build the request and return parsed JSON; caching
// and prefetch live in the hook layer (src/hooks/useCoverage.ts).

import { apiGet } from "./client";

// The five dimensions that can be filtered on — property type plus the four
// address components, exactly the mart's grouping columns
// (query.py:FILTER_COLUMNS / MART_GROUP_COLUMNS).
export const FILTER_COLUMNS = [
  "property_type",
  "constituent_country",
  "county",
  "district",
  "postcode_prefix",
] as const;
export type FilterColumn = (typeof FILTER_COLUMNS)[number];

// A multi-select per column maps to a repeated query param (?county=A&county=B).
export type Filters = Partial<Record<FilterColumn, string[]>>;

// Any mart column is sortable (query.py:SORTABLE_COLUMNS = MART_COLUMNS):
// the five dimensions plus the three coverage metrics.
export const SORTABLE_COLUMNS = [
  ...FILTER_COLUMNS,
  "total_land_registry_sales",
  "matched_uprn_count",
  "coverage_percentage",
] as const;
export type SortColumn = (typeof SORTABLE_COLUMNS)[number];
export type SortDir = "asc" | "desc";

// Human labels for the columns, used in table headers and filter captions.
export const COLUMN_LABELS: Record<SortColumn, string> = {
  property_type: "Property type",
  constituent_country: "Country",
  county: "County",
  district: "District",
  postcode_prefix: "Postcode",
  total_land_registry_sales: "LR sales",
  matched_uprn_count: "Matched UPRNs",
  coverage_percentage: "Coverage %",
};

export interface CoverageRow {
  property_type: string | null;
  constituent_country: string | null;
  county: string | null;
  district: string | null;
  postcode_prefix: string | null;
  total_land_registry_sales: number;
  matched_uprn_count: number;
  coverage_percentage: number;
}

export interface CoveragePage {
  total: number;
  limit: number;
  offset: number;
  items: CoverageRow[];
}

export type FilterOptions = Record<FilterColumn, string[]>;

export interface CoverageSummaryRow {
  value: string | null;
  total_land_registry_sales: number;
  matched_uprn_count: number;
  unmatched_count: number;
  coverage_percentage: number | null;
}

export interface CoverageSummary {
  group_by: FilterColumn;
  built_at: string | null;
  total: CoverageSummaryRow;
  items: CoverageSummaryRow[];
}

export interface CoverageQuery {
  filters: Filters;
  sortBy: SortColumn;
  sortDir: SortDir;
  limit: number;
  offset: number;
}

/** Repeated query params for the active (non-empty) filters, in a stable order. */
function filtersToParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  for (const column of FILTER_COLUMNS) {
    for (const value of filters[column] ?? []) params.append(column, value);
  }
  return params;
}

/** One filtered/sorted/paginated page of the mart (GET /coverage-metrics). */
export function fetchCoveragePage(
  query: CoverageQuery,
  signal?: AbortSignal,
): Promise<CoveragePage> {
  const params = filtersToParams(query.filters);
  params.set("sort_by", query.sortBy);
  params.set("sort_dir", query.sortDir);
  params.set("limit", String(query.limit));
  params.set("offset", String(query.offset));
  return apiGet<CoveragePage>("/coverage-metrics", params, signal);
}

/** Sale totals grouped by one dimension (GET /coverage-metrics/summary). */
export function fetchCoverageSummary(
  filters: Filters,
  groupBy: FilterColumn,
  signal?: AbortSignal,
): Promise<CoverageSummary> {
  const params = filtersToParams(filters);
  params.set("group_by", groupBy);
  return apiGet<CoverageSummary>("/coverage-metrics/summary", params, signal);
}

/** Cascading dropdown values (GET /coverage-metrics/filter-options). */
export function fetchFilterOptions(
  filters: Filters,
  signal?: AbortSignal,
): Promise<FilterOptions> {
  return apiGet<FilterOptions>(
    "/coverage-metrics/filter-options",
    filtersToParams(filters),
    signal,
  );
}
