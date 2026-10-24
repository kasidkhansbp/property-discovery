// The results grid. Headers are clickable to sort (click a sorted column to flip
// direction); the coverage metric gets a small inline bar. NULL dimension buckets
// (sales whose postcode was too short to derive an area) render as an em dash.

import {
  COLUMN_LABELS,
  SORTABLE_COLUMNS,
  type CoverageRow,
  type SortColumn,
  type SortDir,
} from "../api/coverage";

interface CoverageTableProps {
  rows: CoverageRow[];
  sortBy: SortColumn;
  sortDir: SortDir;
  onSort: (column: SortColumn) => void;
  stale?: boolean;
}

const NUMERIC_COLUMNS = new Set<SortColumn>([
  "total_land_registry_sales",
  "matched_uprn_count",
  "coverage_percentage",
]);

const integerFmt = new Intl.NumberFormat("en-GB");

function dash(value: string | null) {
  return value && value.length > 0 ? value : "—";
}

export function CoverageTable({ rows, sortBy, sortDir, onSort, stale }: CoverageTableProps) {
  return (
    <div className={`table-wrap${stale ? " table-wrap--stale" : ""}`}>
      <table className="coverage-table">
        <thead>
          <tr>
            {SORTABLE_COLUMNS.map((column) => {
              const active = column === sortBy;
              return (
                <th
                  key={column}
                  className={NUMERIC_COLUMNS.has(column) ? "num" : undefined}
                  aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <button type="button" className="th-sort" onClick={() => onSort(column)}>
                    {COLUMN_LABELS[column]}
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
          {rows.map((row, index) => (
            <tr key={`${row.constituent_country}-${row.county}-${row.district}-${row.postcode_prefix}-${index}`}>
              <td>{dash(row.constituent_country)}</td>
              <td>{dash(row.county)}</td>
              <td>{dash(row.district)}</td>
              <td>{dash(row.postcode_prefix)}</td>
              <td className="num">{integerFmt.format(row.total_land_registry_sales)}</td>
              <td className="num">{integerFmt.format(row.matched_uprn_count)}</td>
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

function CoverageCell({ pct }: { pct: number }) {
  const clamped = Math.max(0, Math.min(100, pct));
  // Red (low) → green (high); hue 0..120 scaled by coverage.
  const hue = Math.round((clamped / 100) * 120);
  return (
    <div className="coverage-cell">
      <span className="coverage-cell__value">{pct.toFixed(2)}%</span>
      <span className="coverage-cell__bar" aria-hidden>
        <span
          className="coverage-cell__fill"
          style={{ width: `${clamped}%`, backgroundColor: `hsl(${hue} 65% 45%)` }}
        />
      </span>
    </div>
  );
}
