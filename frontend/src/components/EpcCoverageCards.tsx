// Headline cards for the EPC UPRN -> sales view: one per property type plus a
// total — the share of each type's EPC UPRNs that have at least one linked sale.
// A thin adapter over the shared CoverageCards.

import type { EpcSummaryRow } from "../api/epcCoverage";
import { CoverageCards } from "./CoverageCards";

interface EpcCoverageCardsProps {
  items: EpcSummaryRow[];
  selected: string[];
  onToggle: (propertyType: string) => void;
  stale?: boolean;
}

const WORDING = { allLabel: "All EPC UPRNs", linkNoun: "a sale" };

export function EpcCoverageCards({ items, selected, onToggle, stale }: EpcCoverageCardsProps) {
  return (
    <CoverageCards
      items={items.map((i) => ({
        value: i.value,
        total: i.epc_uprns,
        matched: i.uprns_with_transaction,
      }))}
      selected={selected}
      onToggle={onToggle}
      wording={WORDING}
      stale={stale}
    />
  );
}
