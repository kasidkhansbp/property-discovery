// Search results as a list, web-search style: a summary line, then per property
// a small "UPRN · postcode" line, the address as the title, and a line of
// details. Words from the query are bolded where they start a word in the
// address.

import { Fragment, type ReactNode } from "react";

import type { PropertyRow, PropertySearchResult, SearchMode } from "../api/properties";

const MODE_LABEL: Record<SearchMode, string> = {
  uprn: "UPRN",
  postcode: "postcode",
  postcode_and_text: "address within a postcode",
  text: "address text",
};

const coordFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 5,
  maximumFractionDigits: 5,
});

function escapeRegExp(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Bold each query word where it starts a word in `text` (case-insensitive). */
function highlight(text: string, q: string): ReactNode {
  const words = q.toUpperCase().match(/[A-Z0-9]+/g);
  if (!words) return text;
  // Longest first, so 'BAKERS' wins over 'BAKER' at the same position.
  const alternatives = [...new Set(words)]
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  const parts = text.split(new RegExp(`(?<![A-Za-z0-9])(${alternatives})`, "i"));
  // split() with one capture group alternates: plain, match, plain, match...
  return parts.map((part, i) =>
    i % 2 === 1 ? <b key={i}>{part}</b> : <Fragment key={i}>{part}</Fragment>,
  );
}

function title(row: PropertyRow) {
  // Without an EPC certificate a UPRN has no address, only coordinates.
  if (!row.address_line_1) return "No address on record";
  return [row.address_line_1, row.posttown].filter(Boolean).join(", ");
}

function details(row: PropertyRow) {
  const parts = [row.property_type, row.built_form, row.country].filter(Boolean);
  if (row.latitude != null && row.longitude != null) {
    parts.push(`${coordFmt.format(row.latitude)}, ${coordFmt.format(row.longitude)}`);
  }
  if (row.address_source) parts.push(`address from ${row.address_source}`);
  return parts.join(" · ");
}

interface PropertySearchResultsProps {
  result: PropertySearchResult;
  stale?: boolean;
  /** Present when a longer list can be requested. */
  onShowMore?: () => void;
}

export function PropertySearchResults({ result, stale, onShowMore }: PropertySearchResultsProps) {
  const { items, q, mode, has_more } = result;

  if (items.length === 0) {
    return (
      <div className="results">
        <p className="results__summary">
          No properties match <strong>{q}</strong> (searched as {MODE_LABEL[mode]}).
        </p>
        <p className="results__tip">
          Check the spelling, try fewer words, or search by postcode. About half of all
          UPRNs have no address on record yet, so they can only be found by UPRN.
        </p>
      </div>
    );
  }

  return (
    <div className={`results${stale ? " results--stale" : ""}`}>
      <p className="results__summary">
        {has_more ? `Top ${items.length}` : items.length}{" "}
        {items.length === 1 ? "result" : "results"} · searched as {MODE_LABEL[mode]}
      </p>

      <ol className="results__list">
        {items.map((row) => (
          <li key={row.uprn} className="result">
            <div className="result__crumb">
              {/* UPRNs are identifiers: no thousands separators. */}
              <span>UPRN {row.uprn}</span>
              {row.postcode && <span> · {highlight(row.postcode, q)}</span>}
            </div>
            <h3 className={`result__title${row.address_line_1 ? "" : " result__title--none"}`}>
              {row.address_line_1 ? highlight(title(row), q) : title(row)}
            </h3>
            <div className="result__details">{details(row)}</div>
          </li>
        ))}
      </ol>

      {has_more && (
        <div className="results__more">
          {onShowMore ? (
            <button type="button" onClick={onShowMore} disabled={stale}>
              Show more results
            </button>
          ) : (
            <span>More properties match. Add a postcode or more of the address to narrow it down.</span>
          )}
        </div>
      )}
    </div>
  );
}
