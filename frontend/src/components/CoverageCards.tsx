// Headline coverage cards, shared by both coverage views: one card per group
// (property type) plus a total. Each group card shows its coverage bar and how
// many items lack a link; clicking it toggles that group in the filter (selected
// cards are outlined). The total reflects the selected groups, or all of them
// when none is selected.
//
// The views differ only in what is counted ("EPC UPRNs" with "a sale" vs "LR
// sales" with "a UPRN"), so they pass normalised rows plus the wording.

import { CoverageCell } from "./CoverageTable";

export interface CoverageCardItem {
  value: string | null;
  total: number;
  matched: number;
}

export interface CoverageCardsWording {
  /** Total card label when nothing is selected, e.g. "All EPC UPRNs". */
  allLabel: string;
  /** What a matched item has, e.g. "a sale" / "a UPRN". */
  linkNoun: string;
}

interface CoverageCardsProps {
  items: CoverageCardItem[];
  selected: string[];
  onToggle: (value: string) => void;
  wording: CoverageCardsWording;
  stale?: boolean;
}

const integerFmt = new Intl.NumberFormat("en-GB");

function sum(rows: CoverageCardItem[]) {
  const n = rows.reduce((acc, r) => acc + r.total, 0);
  const w = rows.reduce((acc, r) => acc + r.matched, 0);
  return { n, w, pct: n ? (w * 100) / n : 0 };
}

export function CoverageCards({ items, selected, onToggle, wording, stale }: CoverageCardsProps) {
  const chosen = selected.length ? items.filter((i) => selected.includes(i.value ?? "")) : items;
  const total = sum(chosen);

  return (
    <div className={`summary-strip epc-cards${stale ? " table-wrap--stale" : ""}`}>
      <div className="summary-card epc-card epc-card--total">
        <div className="summary-card__label">
          {selected.length ? "Selected types" : wording.allLabel}
        </div>
        <div className="summary-card__value">{total.pct.toFixed(1)}%</div>
        <div className="summary-card__sub">
          {integerFmt.format(total.w)} of {integerFmt.format(total.n)} have {wording.linkNoun} ·{" "}
          {integerFmt.format(total.n - total.w)} without
        </div>
      </div>

      {items.map((item) => {
        const type = item.value ?? "Unknown";
        const active = selected.includes(type);
        const pct = item.total ? (item.matched * 100) / item.total : 0;
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
              <CoverageCell pct={pct} />
            </div>
            <div className="summary-card__sub">
              {integerFmt.format(item.total - item.matched)} of{" "}
              {integerFmt.format(item.total)} without {wording.linkNoun}
            </div>
          </button>
        );
      })}
    </div>
  );
}
