// The EPC UPRN -> sales grid: one row per mart group (property type, built form,
// tenure, UPRN source, country, postcode prefix). Headers sort (click again to
// flip); the coverage column reuses the sales view's inline bar.

import {
  EPC_COLUMN_LABELS,
  EPC_SORTABLE_COLUMNS,
  type EpcCoverageRow,
  type EpcSortColumn,
  type SortDir,
} from "../api/epcCoverage";
import { CoverageCell } from "./CoverageTable";

interface EpcCoverageTableProps {
  rows: EpcCoverageRow[];
  sortBy: EpcSortColumn;
  sortDir: SortDir;
  onSort: (column: EpcSortColumn) => void;
  stale?: boolean;
}

const NUMERIC_COLUMNS = new Set<EpcSortColumn>([
  "epc_uprns",
  "uprns_with_transaction",
  "uprns_without_transaction",
  "coverage_percentage",
]);

const integerFmt = new Intl.NumberFormat("en-GB");

export function EpcCoverageTable({ rows, sortBy, sortDir, onSort, stale }: EpcCoverageTableProps) {
  return (
    <div className={`table-wrap${stale ? " table-wrap--stale" : ""}`}>
      <table className="coverage-table">
        <thead>
          <tr>
            {EPC_SORTABLE_COLUMNS.map((column) => {
              const active = column === sortBy;
              return (
                <th
                  key={column}
                  className={NUMERIC_COLUMNS.has(column) ? "num" : undefined}
                  aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <button type="button" className="th-sort" onClick={() => onSort(column)}>
                    {EPC_COLUMN_LABELS[column]}
                    <span className="th-sort__arrow">
                      {active ? (sortDir === "asc" ? "▲" : "▼") : ""}
                    </span>
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={EPC_SORTABLE_COLUMNS.length} className="coverage-table__empty">
                No rows match these filters.
              </td>
            </tr>
          )}
          {rows.map((row) => (
            <tr
              key={[
                row.property_type,
                row.built_form,
                row.tenure,
                row.uprn_source,
                row.constituent_country,
                row.postcode_prefix,
              ].join("|")}
            >
              <td>{row.property_type}</td>
              <td>{row.built_form}</td>
              <td>{row.tenure}</td>
              <td>{row.uprn_source}</td>
              <td>{row.constituent_country}</td>
              <td>{row.postcode_prefix ?? "—"}</td>
              <td className="num">{integerFmt.format(row.epc_uprns)}</td>
              <td className="num">{integerFmt.format(row.uprns_with_transaction)}</td>
              <td className="num">{integerFmt.format(row.uprns_without_transaction)}</td>
              <td className="num">
                <CoverageCell pct={row.coverage_percentage} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
