// One property's history as a timeline: every Land Registry sale and EPC
// certificate, newest first, one sub-row each. Shown under an expanded row in
// the properties table and under a search result.
//
// Columns are shared by both kinds of event: date, a kind badge, the headline
// (price for a sale, energy rating for a certificate), details, and a last
// column saying how much to trust the link (match type for a sale, certificate
// number for an EPC).

import type { EpcEvent, HistoryEvent, SaleEvent } from "../api/properties";
import { ApiError } from "../api/client";
import { usePropertyHistory } from "../hooks/usePropertyHistory";

const priceFmt = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  maximumFractionDigits: 0,
});

const dateFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

// Land Registry Price Paid codes.
const LR_PROPERTY_TYPE: Record<string, string> = {
  D: "Detached",
  S: "Semi-detached",
  T: "Terraced",
  F: "Flat / maisonette",
  O: "Other",
};
const LR_DURATION: Record<string, string> = { F: "Freehold", L: "Leasehold" };

function formatDate(iso: string | null) {
  if (!iso) return "Undated";
  // Dates arrive as YYYY-MM-DD; parse as UTC so the day never shifts.
  return dateFmt.format(new Date(`${iso}T00:00:00Z`));
}

function join(parts: (string | null | undefined | false)[], sep = " · ") {
  return parts.filter(Boolean).join(sep);
}

function saleAddress(e: SaleEvent) {
  return join([e.saon, join([e.paon, e.street], " "), e.postcode], ", ");
}

function epcAddress(e: EpcEvent) {
  return join([e.address1, e.address2, e.address3, e.postcode], ", ");
}

// "England and Wales: 1900-1929" -> "built 1900-1929"
function ageBand(band: string | null) {
  return band ? band.replace(/^England and Wales:\s*/i, "built ") : null;
}

function Rating({ band }: { band: string | null }) {
  if (!band) return <span className="epc-band epc-band--none">?</span>;
  const b = band.toUpperCase();
  return <span className={`epc-band epc-band--${b.toLowerCase()}`}>{b}</span>;
}

function SaleCells({ e }: { e: SaleEvent }) {
  const details = join([
    e.property_type && (LR_PROPERTY_TYPE[e.property_type] ?? e.property_type),
    e.duration && (LR_DURATION[e.duration] ?? e.duration),
    e.old_new === "Y" && "New build",
    e.ppd_category === "B" && "Non-standard sale",
  ]);
  const fuzzy = e.match_type !== "EXACT";
  return (
    <>
      <td className="num history__headline">
        {e.price != null ? priceFmt.format(e.price) : "—"}
      </td>
      <td className="history__details">
        <div>{details || "—"}</div>
        <div className="history__address">{saleAddress(e)}</div>
      </td>
      <td>
        <span
          className={`match-badge${fuzzy ? " match-badge--fuzzy" : ""}`}
          title={`Linked to this UPRN by ${e.match_type.toLowerCase()} match (score ${e.match_score.toFixed(2)})`}
        >
          {fuzzy ? `${e.match_type.toLowerCase()} ${e.match_score.toFixed(2)}` : "exact"}
        </span>
      </td>
    </>
  );
}

function EpcCells({ e }: { e: EpcEvent }) {
  const details = join([
    e.total_floor_area != null && `${Math.round(e.total_floor_area)} m²`,
    join([e.property_type, e.built_form], ", "),
    ageBand(e.construction_age_band),
    e.tenure,
    e.transaction_type,
  ]);
  return (
    <>
      <td className="num history__headline">
        <span className="history__rating">
          <Rating band={e.current_energy_rating} />
          <span className="history__arrow">→</span>
          <Rating band={e.potential_energy_rating} />
        </span>
        <div className="history__score">
          {e.current_energy_efficiency ?? "?"} → {e.potential_energy_efficiency ?? "?"}
        </div>
      </td>
      <td className="history__details">
        <div>{details || "—"}</div>
        <div className="history__address">{epcAddress(e)}</div>
      </td>
      <td className="history__ref" title="Certificate number">
        {e.certificate_number}
      </td>
    </>
  );
}

function EventRow({ e }: { e: HistoryEvent }) {
  return (
    <tr className={`history__row history__row--${e.kind}`}>
      <td className="history__date">{formatDate(e.date)}</td>
      <td>
        <span className={`kind-badge kind-badge--${e.kind}`}>
          {e.kind === "sale" ? "Sale" : "EPC"}
        </span>
      </td>
      {e.kind === "sale" ? <SaleCells e={e} /> : <EpcCells e={e} />}
    </tr>
  );
}

function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`;
}

function errorMessage(err: unknown) {
  if (err instanceof ApiError) {
    return `Couldn't load history: ${err.message} (HTTP ${err.status}).`;
  }
  // fetch() rejects with a TypeError when no response arrived at all: the
  // gateway is down, the URL is wrong, or the network dropped.
  if (err instanceof TypeError) {
    return "Couldn't reach the gateway to load history. Check that it is running, then retry.";
  }
  return `Couldn't load history: ${String(err)}.`;
}

export function PropertyHistory({ uprn }: { uprn: number }) {
  const history = usePropertyHistory(uprn);

  if (history.isPending) {
    return <div className="history history__status">Loading history…</div>;
  }

  if (history.isError) {
    // A failed request says nothing about the house, so it is never shown as
    // "no data": that would claim a property was never sold when the gateway
    // simply didn't answer.
    return (
      <div className="history history__status history__status--error" role="alert">
        {errorMessage(history.error)}{" "}
        <button type="button" className="link-button" onClick={() => history.refetch()}>
          Retry
        </button>
      </div>
    );
  }

  const { events, sale_count, epc_count } = history.data;

  if (events.length === 0) {
    return (
      <div className="history history__status history__status--empty">
        <strong>No sales or EPC data available for this property.</strong> It has never
        been sold (no Land Registry sale is linked to this UPRN) and has no EPC
        certificate.
      </div>
    );
  }

  return (
    <div className="history">
      <p className="history__summary">
        {sale_count > 0 ? plural(sale_count, "sale", "sales") : <strong>Never sold</strong>}
        {" · "}
        {epc_count > 0 ? (
          plural(epc_count, "EPC certificate", "EPC certificates")
        ) : (
          <strong>No EPC data available</strong>
        )}
        {sale_count === 0 && " · no Land Registry sale is linked to this UPRN"}
      </p>
      <table className="history__table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Event</th>
            <th className="num">Price / rating</th>
            <th>Details</th>
            <th>Link / reference</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <EventRow key={e.kind === "sale" ? e.transaction_id : e.certificate_number} e={e} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
