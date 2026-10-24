// Data hooks over the data-quality API. The quality tables are tiny (one row per
// source column, rebuilt monthly), so there's no paging or prefetch here — just
// a cached fetch per table plus the cross-table summary.

import { useQuery } from "@tanstack/react-query";

import {
  fetchQualitySummary,
  fetchQualityTable,
  type QualityTableName,
} from "../api/quality";

// Keep fetched data fresh for 5 minutes (matching the coverage hooks); the
// quality snapshots only change when the monthly jobs run.
const STALE_TIME_MS = 5 * 60 * 1000;

/** Headline coverage for every profiled table (GET /quality). */
export function useQualitySummary() {
  return useQuery({
    queryKey: ["quality-summary"],
    queryFn: ({ signal }) => fetchQualitySummary(signal),
    staleTime: STALE_TIME_MS,
  });
}

/** Per-column coverage of one table (GET /quality/{source_table}). */
export function useQualityTable(sourceTable: QualityTableName) {
  return useQuery({
    queryKey: ["quality-table", sourceTable],
    queryFn: ({ signal }) => fetchQualityTable(sourceTable, signal),
    staleTime: STALE_TIME_MS,
  });
}
