// One profiled table rendered as a section: a heading with the source row count
// and snapshot time, then a per-column grid (column, type, total, populated,
// NULL, blank, coverage). Reuses the coverage table + coverage-cell styles. The
// coverage bar is colour-scaled red→green exactly like the coverage dashboard.

import { ApiError } from "../api/client";
import {
  TABLE_LABELS,
  type QualityColumnRow,
  type QualityTableName,
} from "../api/quality";
import { useQualityTable } from "../hooks/useQuality";

const integerFmt = new Intl.NumberFormat("en-GB");

interface QualityTableSectionProps {
  sourceTable: QualityTableName;
  /** When true, hide columns that are already 100% covered. */
  onlyProblems: boolean;
}

export function QualityTableSection({ sourceTable, onlyProblems }: QualityTableSectionProps) {
  const query = useQualityTable(sourceTable);
  const data = query.data;

  const allColumns = data?.columns ?? [];
  const columns = onlyProblems
    ? allColumns.filter((c) => c.coverage_pct != null && c.coverage_pct < 100)
    : allColumns;

  return (
    <section className="quality-section">
      <div className="quality-section__head">
        <h2 className="quality-section__title">{TABLE_LABELS[sourceTable]}</h2>
        <span className="quality-section__meta">
          <code>{sourceTable}</code>
          {data && (
            <>
              {" · "}
              {integerFmt.format(data.total_rows)} rows · {allColumns.length} columns
              {data.checked_at && (
                <> · checked {new Date(data.checked_at).toLocaleString("en-GB")}</>
              )}
            </>
          )}
        </span>
      </div>

      {query.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load {sourceTable}.</strong>{" "}
          {query.error instanceof ApiError
            ? `${query.error.message} (HTTP ${query.error.status})`
            : String(query.error)}
          <button type="button" onClick={() => query.refetch()}>
            Retry
          </button>
        </div>
      )}

      {query.isLoading && !data ? (
        <div className="banner">Loading {sourceTable}…</div>
      ) : columns.length === 0 ? (
        <div className="banner">
          {onlyProblems ? "Every column is 100% covered. 🎉" : "No columns profiled."}
        </div>
      ) : (
        <div className="table-wrap">
          <table className="coverage-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Type</th>
                <th className="num">Total rows</th>
                <th className="num">Populated</th>
                <th className="num">NULL</th>
                <th className="num">Blank</th>
                <th className="num">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((row) => (
                <QualityRow key={row.column_name} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function QualityRow({ row }: { row: QualityColumnRow }) {
  return (
    <tr>
      <td>
        <code>{row.column_name}</code>
      </td>
      <td className="quality-type">{row.data_type}</td>
      <td className="num">{integerFmt.format(row.total_rows)}</td>
      <td className="num">{integerFmt.format(row.populated_count)}</td>
      <td className="num">{integerFmt.format(row.null_count)}</td>
      <td className="num">{integerFmt.format(row.empty_string_count)}</td>
      <td className="num">
        <CoverageCell pct={row.coverage_pct} />
      </td>
    </tr>
  );
}

function CoverageCell({ pct }: { pct: number | null }) {
  if (pct == null) {
    return <span className="coverage-cell__value">—</span>;
  }
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
