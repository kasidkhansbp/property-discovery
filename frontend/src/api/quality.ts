// Typed access to the data-quality endpoints. Mirrors the gateway's quality
// schemas (gateway/app/schemas.py) and the /quality routes
// (gateway/app/routers/quality.py), so the UI and API stay in lock-step. These
// build the request and return parsed JSON; caching lives in the hook layer
// (src/hooks/useQuality.ts).

import { apiGet } from "./client";

// The four profiled source tables, in display order. Mirrors the backend's
// QUALITY_SOURCES (services/ingestion/data_quality/schema.py); the /quality
// summary returns exactly these.
export const QUALITY_TABLES = [
  "land_registry_sales",
  "epc_domestic_certificates",
  "os_open_uprn",
  "property_uprn_mapping",
] as const;
export type QualityTableName = (typeof QUALITY_TABLES)[number];

// Human labels for the table headings.
export const TABLE_LABELS: Record<QualityTableName, string> = {
  land_registry_sales: "Land Registry sales",
  epc_domestic_certificates: "EPC domestic certificates",
  os_open_uprn: "OS Open UPRN",
  property_uprn_mapping: "Property ↔ UPRN mapping",
};

// One row per source column: how populated that column is.
export interface QualityColumnRow {
  column_name: string;
  data_type: string;
  column_position: number;
  total_rows: number;
  populated_count: number;
  null_count: number;
  empty_string_count: number;
  coverage_pct: number | null;
  checked_at: string;
}

// Every profiled column of one table, plus table-level context.
export interface QualityTable {
  source_table: string;
  quality_table: string;
  total_rows: number;
  checked_at: string | null;
  columns: QualityColumnRow[];
}

// One table's headline coverage, for the summary strip.
export interface QualitySummaryRow {
  source_table: string;
  quality_table: string;
  total_rows: number;
  columns_profiled: number;
  average_coverage_pct: number | null;
  worst_coverage_pct: number | null;
  checked_at: string | null;
}

export interface QualitySummary {
  items: QualitySummaryRow[];
}

/** Headline coverage for every profiled table (GET /quality). */
export function fetchQualitySummary(signal?: AbortSignal): Promise<QualitySummary> {
  return apiGet<QualitySummary>("/quality", undefined, signal);
}

/** Every profiled column of one table (GET /quality/{source_table}). */
export function fetchQualityTable(
  sourceTable: QualityTableName,
  signal?: AbortSignal,
): Promise<QualityTable> {
  return apiGet<QualityTable>(`/quality/${sourceTable}`, undefined, signal);
}
