// One property's history: every Land Registry sale and EPC certificate,
// newest first. Nothing is capped or truncated. Two layouts of the same data:
//
//   "table"    - desktop. Compact rows (date, kind, price / rating, details,
//                link / reference), shown inline under an expanded property.
//   "timeline" - mobile. One card per event on a vertical rail, shown on the
//                full-screen property screen. A sale card leads with the price
//                and the change since the previous sale; an EPC card with the
//                current -> potential rating. Trust in a sale's link to this
//                UPRN is spelled out in words on fuzzy matches (no tooltips:
//                they never show on touch screens).

import type { EpcEvent, HistoryEvent, SaleEvent } from "../api/properties";
import { ApiError } from "../api/client";
import { usePropertyHistory } from "../hooks/usePropertyHistory";

export const priceFmt = new Intl.NumberFormat("en-GB", {
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

export function formatDate(iso: string | null) {
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

function saleDetails(e: SaleEvent) {
  return join([
    e.property_type && (LR_PROPERTY_TYPE[e.property_type] ?? e.property_type),
    e.duration && (LR_DURATION[e.duration] ?? e.duration),
    e.old_new === "Y" && "New build",
    e.ppd_category === "B" && "Non-standard sale",
  ]);
}

function epcDetails(e: EpcEvent) {
  return join([
    e.total_floor_area != null && `${Math.round(e.total_floor_area)} m²`,
    join([e.property_type, e.built_form], ", "),
    ageBand(e.construction_age_band),
    e.tenure,
    e.transaction_type,
  ]);
}

function eventKey(e: HistoryEvent) {
  return e.kind === "sale" ? `sale-${e.transaction_id}` : `epc-${e.certificate_number}`;
}

export function Rating({ band, size }: { band: string | null; size?: "lg" }) {
  const cls = `epc-band${size ? ` epc-band--${size}` : ""}`;
  if (!band) return <span className={`${cls} epc-band--none`}>?</span>;
  const b = band.toUpperCase();
  return <span className={`${cls} epc-band--${b.toLowerCase()}`}>{b}</span>;
}

// ---- Desktop: table rows ----------------------------------------------------

function SaleCells({ e }: { e: SaleEvent }) {
  const fuzzy = e.match_type !== "EXACT";
  return (
    <>
      <td className="num history__headline">
        {e.price != null ? priceFmt.format(e.price) : "—"}
      </td>
      <td className="history__details">
        <div>{saleDetails(e) || "—"}</div>
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
        <div>{epcDetails(e) || "—"}</div>
        <div className="history__address">{epcAddress(e)}</div>
      </td>
      <td className="history__ref" title="Certificate number">
        {e.certificate_number}
      </td>
    </>
  );
}

function HistoryTable({ events }: { events: HistoryEvent[] }) {
  return (
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
          <tr key={eventKey(e)} className={`history__row history__row--${e.kind}`}>
            <td className="history__date">{formatDate(e.date)}</td>
            <td>
              <span className={`kind-badge kind-badge--${e.kind}`}>
                {e.kind === "sale" ? "Sale" : "EPC"}
              </span>
            </td>
            {e.kind === "sale" ? <SaleCells e={e} /> : <EpcCells e={e} />}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---- Mobile: timeline cards -------------------------------------------------

/** "+£42,000 (+18%) since 2014", or null when either price is missing. */
function priceChange(e: SaleEvent, prev: SaleEvent | undefined) {
  if (!prev || e.price == null || prev.price == null || prev.price <= 0) return null;
  const diff = e.price - prev.price;
  const pct = Math.round((diff / prev.price) * 100);
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  const since = prev.date ? ` since ${prev.date.slice(0, 4)}` : "";
  return {
    dir: diff > 0 ? "up" : diff < 0 ? "down" : "flat",
    text: `${sign}${priceFmt.format(Math.abs(diff))} (${sign}${Math.abs(pct)}%)${since}`,
  };
}

function SaleBody({ e, prev }: { e: SaleEvent; prev: SaleEvent | undefined }) {
  const details = saleDetails(e);
  const change = priceChange(e, prev);
  const exact = e.match_type === "EXACT";
  return (
    <>
      <div className="timeline__headline">
        {e.price != null ? priceFmt.format(e.price) : "Price not recorded"}
      </div>
      {change && (
        <div className={`timeline__change timeline__change--${change.dir}`}>{change.text}</div>
      )}
      {details && <div className="timeline__details">{details}</div>}
      {!exact && (
        // A non-exact link is a judgement call: show the address the sale was
        // recorded under, so it can be checked against this property.
        <div className="timeline__note">
          <strong>
            Approximate match ({e.match_type.toLowerCase()}, score {e.match_score.toFixed(2)})
          </strong>
          <span>Recorded as: {saleAddress(e) || "no address"}</span>
        </div>
      )}
    </>
  );
}

function EpcBody({ e }: { e: EpcEvent }) {
  const details = epcDetails(e);
  return (
    <>
      <div className="timeline__headline timeline__rating">
        <Rating band={e.current_energy_rating} />
        <span className="timeline__arrow" aria-label="could reach">
          →
        </span>
        <Rating band={e.potential_energy_rating} />
        <span className="timeline__score">
          {e.current_energy_efficiency ?? "?"} → {e.potential_energy_efficiency ?? "?"}
        </span>
      </div>
      {details && <div className="timeline__details">{details}</div>}
      <div className="timeline__ref">Certificate {e.certificate_number}</div>
    </>
  );
}

function HistoryTimeline({ events }: { events: HistoryEvent[] }) {
  // Events are newest first, so each sale's previous sale is the next one down.
  const sales = events.filter((e): e is SaleEvent => e.kind === "sale");
  const previousSale = new Map(sales.map((s, i) => [s.transaction_id, sales[i + 1]]));

  return (
    <ol className="timeline">
      {events.map((e) => (
        <li key={eventKey(e)} className={`timeline__item timeline__item--${e.kind}`}>
          <div className="timeline__card">
            <div className="timeline__meta">
              <span className={`kind-badge kind-badge--${e.kind}`}>
                {e.kind === "sale" ? "Sold" : "EPC"}
              </span>
              <time dateTime={e.date ?? undefined}>{formatDate(e.date)}</time>
            </div>
            {e.kind === "sale" ? (
              <SaleBody e={e} prev={previousSale.get(e.transaction_id)} />
            ) : (
              <EpcBody e={e} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

// ---- Shared: loading, error, empty, summary ---------------------------------

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

export type HistoryVariant = "table" | "timeline";

export function PropertyHistory({ uprn, variant }: { uprn: number; variant: HistoryVariant }) {
  const history = usePropertyHistory(uprn);
  const cls = `history history--${variant}`;

  if (history.isPending) {
    return variant === "timeline" ? (
      <div className={cls} aria-busy="true">
        <p className="history__status">Loading history…</p>
        <div className="skeleton skeleton--card" />
        <div className="skeleton skeleton--card" />
      </div>
    ) : (
      <div className={`${cls} history__status`}>Loading history…</div>
    );
  }

  if (history.isError) {
    // A failed request says nothing about the house, so it is never shown as
    // "no data": that would claim a property was never sold when the gateway
    // simply didn't answer.
    return (
      <div className={`${cls} history__status history__status--error`} role="alert">
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
      <div className={`${cls} history__status history__status--empty`}>
        <strong>No sales or EPC data available for this property.</strong> It may not
        have been sold since Land Registry records began in 1995, or a sale may exist
        that hasn't been matched to this UPRN. No EPC certificate was found for it
        either.
      </div>
    );
  }

  return (
    <div className={cls}>
      <p className="history__summary">
        {sale_count > 0 ? plural(sale_count, "sale", "sales") : <strong>No recorded sales</strong>}
        {" · "}
        {epc_count > 0 ? (
          plural(epc_count, "EPC certificate", "EPC certificates")
        ) : (
          <strong>No EPC data available</strong>
        )}
        {sale_count === 0 &&
          " · possibly not sold since 1995, or a sale hasn't been matched to this UPRN"}
      </p>
      {variant === "timeline" ? (
        <HistoryTimeline events={events} />
      ) : (
        <HistoryTable events={events} />
      )}
    </div>
  );
}
