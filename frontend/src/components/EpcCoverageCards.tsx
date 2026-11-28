// Headline cards for the EPC UPRN -> sales view: one per property type plus a
// total. Each type card shows the share of that type's EPC UPRNs that have at
// least one linked sale; clicking it toggles that type in the property-type
// filter (selected cards are outlined). The total reflects the selected types,
// or all of them when none is selected.

import type { EpcSummaryRow } from "../api/epcCoverage";
import { CoverageCell } from "./CoverageTable";

interface EpcCoverageCardsProps {
  items: EpcSummaryRow[];
  selected: string[];
  onToggle: (propertyType: string) => void;
  stale?: boolean;
}

const integerFmt = new Intl.NumberFormat("en-GB");

function sum(rows: EpcSummaryRow[]) {
  const n = rows.reduce((acc, r) => acc + r.epc_uprns, 0);
  const w = rows.reduce((acc, r) => acc + r.uprns_with_transaction, 0);
  return { n, w, pct: n ? (w * 100) / n : 0 };
}

export function EpcCoverageCards({ items, selected, onToggle, stale }: EpcCoverageCardsProps) {
  const chosen = selected.length ? items.filter((i) => selected.includes(i.value ?? "")) : items;
  const total = sum(chosen);

  return (
    <div className={`summary-strip epc-cards${stale ? " table-wrap--stale" : ""}`}>
      <div className="summary-card epc-card epc-card--total">
        <div className="summary-card__label">
          {selected.length ? "Selected types" : "All EPC UPRNs"}
        </div>
        <div className="summary-card__value">{total.pct.toFixed(1)}%</div>
        <div className="summary-card__sub">
          {integerFmt.format(total.w)} of {integerFmt.format(total.n)} have a sale ·{" "}
          {integerFmt.format(total.n - total.w)} without
        </div>
      </div>

      {items.map((item) => {
        const type = item.value ?? "Unknown";
        const active = selected.includes(type);
        return (
          <button
            type="button"
            key={type}
            className={`summary-card epc-card${active ? " epc-card--active" : ""}`}
            aria-pressed={active}
            onClick={() => onToggle(type)}
            title={active ? `Remove ${type} filter` : `Show only ${type}`}
          >
            <div className="summary-card__label">{type}</div>
            <div className="epc-card__bar">
              <CoverageCell pct={item.coverage_percentage ?? 0} />
            </div>
            <div className="summary-card__sub">
              {integerFmt.format(item.uprns_without_transaction)} of{" "}
              {integerFmt.format(item.epc_uprns)} without a sale
            </div>
          </button>
        );
      })}
    </div>
  );
}
