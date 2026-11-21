// The properties grid: one row per UPRN. Address fields are NULL for UPRNs with
// no EPC certificate (about half of them) and render as an em dash.
//
// Clicking a row expands it: a full-width sub-row underneath shows the
// property's sales and EPC certificates as one timeline (PropertyHistory).
// Several rows can be open at once; history is fetched on first open only.

import { Fragment, useState } from "react";

import type { PropertyRow } from "../api/properties";
import { PropertyHistory } from "./PropertyHistory";

interface PropertiesTableProps {
  rows: PropertyRow[];
  stale?: boolean;
}

const COLUMN_COUNT = 10;

const coordFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 5,
  maximumFractionDigits: 5,
});

function dash(value: string | null) {
  return value && value.length > 0 ? value : "—";
}

function coord(value: number | null) {
  return value == null ? "—" : coordFmt.format(value);
}

export function PropertiesTable({ rows, stale }: PropertiesTableProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set());

  function toggle(uprn: number) {
    // Don't toggle when the click ended a text selection (copying a UPRN).
    if (window.getSelection()?.toString()) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(uprn)) next.add(uprn);
      return next;
    });
  }

  return (
    <div className={`table-wrap${stale ? " table-wrap--stale" : ""}`}>
      <table className="coverage-table properties-table">
        <thead>
          <tr>
            <th className="num">UPRN</th>
            <th>Address</th>
            <th>Town</th>
            <th>Postcode</th>
            <th>Property type</th>
            <th>Built form</th>
            <th>Country</th>
            <th className="num">Latitude</th>
            <th className="num">Longitude</th>
            <th>Address source</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={COLUMN_COUNT} className="properties-empty">
                No properties
              </td>
            </tr>
          ) : (
            rows.map((row) => {
              const open = expanded.has(row.uprn);
              const historyId = `history-${row.uprn}`;
              return (
                <Fragment key={row.uprn}>
                  <tr
                    className={`property-row${open ? " property-row--open" : ""}`}
                    onClick={() => toggle(row.uprn)}
                  >
                    <td className="num">
                      {/* The button makes the row keyboard-operable; its click
                          bubbles to the row's handler. */}
                      <button
                        type="button"
                        className="row-toggle"
                        aria-expanded={open}
                        aria-controls={open ? historyId : undefined}
                        aria-label={`${open ? "Hide" : "Show"} sales and EPC history for UPRN ${row.uprn}`}
                      >
                        {open ? "▾" : "▸"}
                      </button>
                      {/* UPRNs are identifiers: no thousands separators. */}
                      {row.uprn}
                    </td>
                    <td>{dash(row.address_line_1)}</td>
                    <td>{dash(row.posttown)}</td>
                    <td>{dash(row.postcode)}</td>
                    <td>{dash(row.property_type)}</td>
                    <td>{dash(row.built_form)}</td>
                    <td>{dash(row.country)}</td>
                    <td className="num">{coord(row.latitude)}</td>
                    <td className="num">{coord(row.longitude)}</td>
                    <td>{dash(row.address_source)}</td>
                  </tr>
                  {open && (
                    <tr className="history-subrow" id={historyId}>
                      <td colSpan={COLUMN_COUNT}>
                        <PropertyHistory uprn={row.uprn} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
