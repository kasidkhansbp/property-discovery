// Data hooks over the /epc-uprn-coverage API. Same caching rules as
// useCoverage.ts: the mart changes monthly, so results stay fresh for 5 minutes
// and paging keeps the previous rows on screen while the next page loads.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  fetchEpcFilterOptions,
  fetchEpcRows,
  fetchEpcSummary,
  type EpcFilterColumn,
  type EpcFilters,
  type EpcSortColumn,
  type SortDir,
} from "../api/epcCoverage";
import { PAGE_SIZE } from "./useCoverage";

const STALE_TIME_MS = 5 * 60 * 1000;

export function useEpcSummary(filters: EpcFilters, groupBy: EpcFilterColumn) {
  return useQuery({
    queryKey: ["epc-coverage-summary", filters, groupBy],
    queryFn: ({ signal }) => fetchEpcSummary(filters, groupBy, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
  });
}

export interface UseEpcRowsArgs {
  filters: EpcFilters;
  sortBy: EpcSortColumn;
  sortDir: SortDir;
  /** Zero-based page index. */
  page: number;
}

export function useEpcRows({ filters, sortBy, sortDir, page }: UseEpcRowsArgs) {
  const query = { filters, sortBy, sortDir, limit: PAGE_SIZE, offset: page * PAGE_SIZE };
  return useQuery({
    queryKey: ["epc-coverage-rows", filters, sortBy, sortDir, page],
    queryFn: ({ signal }) => fetchEpcRows(query, signal),
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
  });
}

export function useEpcFilterOptions(filters: EpcFilters) {
  return useQuery({
    queryKey: ["epc-coverage-filter-options", filters],
    queryFn: ({ signal }) => fetchEpcFilterOptions(filters, signal),
    staleTime: STALE_TIME_MS,
  });
}
