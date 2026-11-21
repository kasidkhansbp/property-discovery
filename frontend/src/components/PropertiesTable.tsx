// The properties grid: one row per UPRN. Address fields are NULL for UPRNs with
// no EPC certificate (about half of them) and render as an em dash.

import type { PropertyRow } from "../api/properties";

interface PropertiesTableProps {
  rows: PropertyRow[];
  stale?: boolean;
}

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
  return (
    <div className={`table-wrap${stale ? " table-wrap--stale" : ""}`}>
      <table className="coverage-table">
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
              <td colSpan={10} className="properties-empty">
                No properties
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.uprn}>
                {/* UPRNs are identifiers: no thousands separators. */}
                <td className="num">{row.uprn}</td>
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
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
