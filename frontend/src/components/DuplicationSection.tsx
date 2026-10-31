// The key-duplication / fan-out section: one compact table, one row per check
// (property_uprn_mapping.uprn, land_registry_sales.transaction_id,
// epc_domestic_certificates.uprn). Reuses the coverage table + section styles.
// Each row answers "how multiply-mapped is this table's key" — distinct keys,
// how many of them repeat, and the average / max rows per key.

import { ApiError } from "../api/client";
import { TABLE_LABELS, type DuplicationRow } from "../api/quality";
import { useDuplication } from "../hooks/useQuality";

const integerFmt = new Intl.NumberFormat("en-GB");

// Share of distinct keys that are duplicated — the headline "how duplicated".
function duplicateShare(row: DuplicationRow): number | null {
  if (row.distinct_keys === 0) return null;
  return (row.keys_with_duplicates / row.distinct_keys) * 100;
}

export function DuplicationSection() {
  const query = useDuplication();
  const rows = query.data?.items ?? [];
  const checkedAt = rows[0]?.checked_at;

  return (
    <section className="quality-section">
      <div className="quality-section__head">
        <h2 className="quality-section__title">Key duplication &amp; fan-out</h2>
        <span className="quality-section__meta">
          <code>key_duplication_quality</code>
          {rows.length > 0 && (
            <>
              {" · "}
              {rows.length} checks
              {checkedAt && (
                <> · checked {new Date(checkedAt).toLocaleString("en-GB")}</>
              )}
            </>
          )}
        </span>
      </div>

      {query.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load key duplication.</strong>{" "}
          {query.error instanceof ApiError
            ? `${query.error.message} (HTTP ${query.error.status})`
            : String(query.error)}
          <button type="button" onClick={() => query.refetch()}>
            Retry
          </button>
        </div>
      )}

      {query.isLoading && rows.length === 0 ? (
        <div className="banner">Loading key duplication…</div>
      ) : rows.length === 0 ? (
        <div className="banner">
          Not built yet — run the <code>key_duplication_quality</code> job.
        </div>
      ) : (
        <div className="table-wrap">
          <table className="coverage-table">
            <thead>
              <tr>
                <th>Table</th>
                <th>Key</th>
                <th className="num">Total rows</th>
                <th className="num">Distinct keys</th>
                <th className="num">Keys with dupes</th>
                <th className="num">% keys duped</th>
                <th className="num">Avg / key</th>
                <th className="num">Max / key</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <DuplicationTableRow key={`${row.source_table}.${row.key_column}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function DuplicationTableRow({ row }: { row: DuplicationRow }) {
  const share = duplicateShare(row);
  return (
    <tr>
      <td>{TABLE_LABELS[row.source_table as keyof typeof TABLE_LABELS] ?? row.source_table}</td>
      <td>
        <code>{row.key_column}</code>
      </td>
      <td className="num">{integerFmt.format(row.total_rows)}</td>
      <td className="num">{integerFmt.format(row.distinct_keys)}</td>
      <td className="num">{integerFmt.format(row.keys_with_duplicates)}</td>
      <td className="num">{share != null ? `${share.toFixed(1)}%` : "—"}</td>
      <td className="num">{row.avg_rows_per_key != null ? row.avg_rows_per_key.toFixed(2) : "—"}</td>
      <td className="num">{integerFmt.format(row.max_rows_per_key)}</td>
    </tr>
  );
}
