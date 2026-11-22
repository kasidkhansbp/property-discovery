// The properties grid: one row per UPRN. Address fields are NULL for UPRNs with
// no EPC certificate (about half of them) and render as an em dash.
//
// Clicking a row does different things per experience (see useIsDesktop):
//   desktop - the row expands: a full-width sub-row underneath shows the
//             property's sales and EPC certificates (PropertyHistory, table
//             layout). Several rows can be open at once; history is fetched on
//             first open only.
//   mobile  - the row opens the full-screen property screen (/property/:uprn).
//             Only UPRN, address and postcode show (.col-opt is hidden).

import { Fragment, useState, type MouseEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { PropertyRow } from "../api/properties";
import { useIsDesktop } from "../hooks/useIsDesktop";
import { propertyLinkState, propertyPath } from "../routes";
import { MapsLink } from "./MapsLink";
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
  const isDesktop = useIsDesktop();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set());

  function onRowClick(e: MouseEvent, row: PropertyRow) {
    // Don't act when the click ended a text selection (copying a UPRN).
    if (window.getSelection()?.toString()) return;

    if (isDesktop) {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (!next.delete(row.uprn)) next.add(row.uprn);
        return next;
      });
      return;
    }

    // Mobile: the UPRN link navigates by itself; elsewhere in the row, do it here.
    if ((e.target as HTMLElement).closest("a")) return;
    navigate(propertyPath(row.uprn), { state: propertyLinkState(row) });
  }

  return (
    <div className={`table-wrap${stale ? " table-wrap--stale" : ""}`}>
      <table className="coverage-table properties-table">
        <thead>
          <tr>
            <th className="num">UPRN</th>
            <th>Address</th>
            <th className="col-opt">Town</th>
            <th>Postcode</th>
            <th className="col-opt">Property type</th>
            <th className="col-opt">Built form</th>
            <th className="col-opt">Country</th>
            <th className="num col-opt">Latitude</th>
            <th className="num col-opt">Longitude</th>
            <th className="col-opt">Address source</th>
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
              const open = isDesktop && expanded.has(row.uprn);
              const historyId = `history-${row.uprn}`;
              return (
                <Fragment key={row.uprn}>
                  <tr
                    className={`property-row${open ? " property-row--open" : ""}`}
                    onClick={(e) => onRowClick(e, row)}
                  >
                    <td className="num">
                      {isDesktop ? (
                        <>
                          {/* The button makes the row keyboard-operable; its
                              click bubbles to the row's handler. */}
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
                        </>
                      ) : (
                        <Link to={propertyPath(row.uprn)} state={propertyLinkState(row)}>
                          {row.uprn}
                        </Link>
                      )}
                    </td>
                    <td className="properties-table__address">{dash(row.address_line_1)}</td>
                    <td className="col-opt">{dash(row.posttown)}</td>
                    <td>{dash(row.postcode)}</td>
                    <td className="col-opt">{dash(row.property_type)}</td>
                    <td className="col-opt">{dash(row.built_form)}</td>
                    <td className="col-opt">{dash(row.country)}</td>
                    <td className="num col-opt">{coord(row.latitude)}</td>
                    <td className="num col-opt">{coord(row.longitude)}</td>
                    <td className="col-opt">{dash(row.address_source)}</td>
                  </tr>
                  {open && (
                    <tr className="history-subrow" id={historyId}>
                      <td colSpan={COLUMN_COUNT}>
                        <div className="history-subrow__actions">
                          <MapsLink row={row} />
                        </div>
                        <PropertyHistory uprn={row.uprn} variant="table" />
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
