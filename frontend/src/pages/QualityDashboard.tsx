// The data-quality screen: a summary strip across all four profiled tables,
// then each table's per-column coverage grid. A single toggle hides fully
// covered columns so the problem columns stand out. The quality tables are
// small, so everything loads at once — no filters or paging needed.

import { useState } from "react";

import { ApiError } from "../api/client";
import { QUALITY_TABLES, TABLE_LABELS, type QualitySummaryRow } from "../api/quality";
import { DuplicationSection } from "../components/DuplicationSection";
import { QualityTableSection } from "../components/QualityTableSection";
import { useQualitySummary } from "../hooks/useQuality";

const integerFmt = new Intl.NumberFormat("en-GB");

export function QualityDashboard() {
  const [onlyProblems, setOnlyProblems] = useState(false);
  const summary = useQualitySummary();

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>Data Quality</h1>
          <p className="dashboard__subtitle">
            Per-column coverage for every served table — how much of each column
            is actually populated — plus cross-table key duplication &amp; fan-out
          </p>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyProblems}
            onChange={(e) => setOnlyProblems(e.target.checked)}
          />
          Only columns below 100%
        </label>
      </header>

      {summary.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load the quality summary.</strong>{" "}
          {summary.error instanceof ApiError
            ? `${summary.error.message} (HTTP ${summary.error.status})`
            : String(summary.error)}
          <button type="button" onClick={() => summary.refetch()}>
            Retry
          </button>
        </div>
      )}

      {summary.data && <SummaryStrip rows={summary.data.items} />}

      <DuplicationSection />

      {QUALITY_TABLES.map((table) => (
        <QualityTableSection key={table} sourceTable={table} onlyProblems={onlyProblems} />
      ))}
    </div>
  );
}

function SummaryStrip({ rows }: { rows: QualitySummaryRow[] }) {
  // Order the cards to match the per-table sections below.
  const byName = new Map(rows.map((r) => [r.source_table, r]));
  const ordered = QUALITY_TABLES.map((t) => byName.get(t)).filter(
    (r): r is QualitySummaryRow => r != null,
  );

  return (
    <div className="summary-strip">
      {ordered.map((row) => {
        const avg = row.average_coverage_pct ?? 0;
        const hue = Math.round((Math.max(0, Math.min(100, avg)) / 100) * 120);
        return (
          <div className="summary-card" key={row.source_table}>
            <div className="summary-card__label">
              {TABLE_LABELS[row.source_table as keyof typeof TABLE_LABELS] ??
                row.source_table}
            </div>
            <div className="summary-card__value" style={{ color: `hsl(${hue} 65% 42%)` }}>
              {row.average_coverage_pct != null
                ? `${row.average_coverage_pct.toFixed(1)}%`
                : "—"}
            </div>
            <div className="summary-card__sub">
              avg coverage · worst{" "}
              {row.worst_coverage_pct != null
                ? `${row.worst_coverage_pct.toFixed(1)}%`
                : "—"}
            </div>
            <div className="summary-card__sub">
              {integerFmt.format(row.total_rows)} rows · {row.columns_profiled} cols
            </div>
          </div>
        );
      })}
    </div>
  );
}
