// The property screen (/property/:uprn): one house, full screen.
//
// Built for a phone first: a top bar with Back and Share, then a hero card
// (address, key facts, last sale, latest EPC), then the full timeline, then
// the technical fields tucked into "Data & provenance". On wide screens the
// hero and provenance sit in a left column beside the timeline.

import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import type { EpcEvent, PropertyRow, SaleEvent } from "../api/properties";
import { MapsLink } from "../components/MapsLink";
import { formatDate, priceFmt, PropertyHistory, Rating } from "../components/PropertyHistory";
import { useProperty } from "../hooks/useProperty";
import { usePropertyHistory } from "../hooks/usePropertyHistory";
import { DEFAULT_TITLE, type PropertyLinkState } from "../routes";

const coordFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 5,
  maximumFractionDigits: 5,
});

function parseUprn(param: string | undefined) {
  return param && /^\d{1,12}$/.test(param) ? Number(param) : null;
}

function headline(row: PropertyRow | null | undefined) {
  return row?.address_line_1 || "No address on record";
}

export function PropertyPage() {
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const uprn = parseUprn(params.uprn);
  const seed = (location.state as PropertyLinkState | null)?.row;
  const property = useProperty(uprn, seed);
  const row = property.data;

  useEffect(() => {
    if (row) document.title = `${headline(row)} · ${DEFAULT_TITLE}`;
    return () => {
      document.title = DEFAULT_TITLE;
    };
  }, [row]);

  function goBack() {
    // idx > 0: we got here by navigating inside the app, so go back to that
    // exact list (scroll position included). Otherwise this is a shared link
    // or a fresh tab: there is nothing to go back to, so go to search.
    const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
    if (idx > 0) navigate(-1);
    else navigate("/properties");
  }

  return (
    <div className="property-page">
      <header className="detail-bar">
        <button type="button" className="detail-bar__back" onClick={goBack}>
          <span aria-hidden="true">‹</span> Back
        </button>
        <span className="detail-bar__title">{row ? headline(row) : ""}</span>
        {row && <ShareButton title={headline(row)} />}
      </header>

      <PageBody uprn={uprn} property={property} />
    </div>
  );
}

function PageBody({
  uprn,
  property,
}: {
  uprn: number | null;
  property: ReturnType<typeof useProperty>;
}) {
  if (uprn == null) {
    return <NotFound text="That isn’t a valid UPRN. A UPRN is a number of up to 12 digits." />;
  }

  if (property.isError) {
    const err = property.error;
    return (
      <div className="property-page__body">
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load this property.</strong>{" "}
          {err instanceof ApiError ? `${err.message} (HTTP ${err.status})` : String(err)}
          <button type="button" onClick={() => property.refetch()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (property.data === null) {
    return <NotFound text={`There is no property with UPRN ${uprn}.`} />;
  }

  const row = property.data;

  return (
    <div className="property-page__body">
      {row ? <Hero row={row} /> : <div className="property-hero skeleton skeleton--hero" />}

      <section className="property-page__timeline" aria-labelledby="timeline-heading">
        <h2 id="timeline-heading" className="section-heading">
          History
        </h2>
        <PropertyHistory uprn={uprn} variant="timeline" />
      </section>

      {row && <Provenance row={row} />}
    </div>
  );
}

function Hero({ row }: { row: PropertyRow }) {
  const history = usePropertyHistory(row.uprn);
  const events = history.data?.events ?? [];
  // Events are newest first, so the first of each kind is the latest.
  const lastSale = events.find((e): e is SaleEvent => e.kind === "sale");
  const latestEpc = events.find((e): e is EpcEvent => e.kind === "epc");
  const place = [row.posttown, row.postcode].filter(Boolean).join(" · ");
  const facts = [row.property_type, row.built_form, row.country].filter(Boolean);

  return (
    <section className="property-hero" aria-label="Property summary">
      <h1 className={`property-hero__title${row.address_line_1 ? "" : " property-hero__title--none"}`}>
        {headline(row)}
      </h1>
      {place && <p className="property-hero__place">{place}</p>}

      {facts.length > 0 && (
        <ul className="chips" aria-label="Key facts">
          {facts.map((f) => (
            <li key={f} className="chip">
              {f}
            </li>
          ))}
        </ul>
      )}

      <div className="stats">
        <div className="stat">
          <div className="stat__label">Last sold</div>
          {history.isPending ? (
            <div className="skeleton skeleton--line" />
          ) : lastSale ? (
            <>
              <div className="stat__value">
                {lastSale.price != null ? priceFmt.format(lastSale.price) : "—"}
              </div>
              <div className="stat__sub">{formatDate(lastSale.date)}</div>
            </>
          ) : (
            <div className="stat__value stat__value--none">{history.isError ? "—" : "No sales"}</div>
          )}
        </div>
        <div className="stat">
          <div className="stat__label">Energy rating</div>
          {history.isPending ? (
            <div className="skeleton skeleton--line" />
          ) : latestEpc ? (
            <>
              <div className="stat__value">
                <Rating band={latestEpc.current_energy_rating} size="lg" />
              </div>
              <div className="stat__sub">{formatDate(latestEpc.date)}</div>
            </>
          ) : (
            <div className="stat__value stat__value--none">{history.isError ? "—" : "No EPC"}</div>
          )}
        </div>
      </div>

      <MapsLink row={row} className="button-secondary property-hero__map" />
    </section>
  );
}

function Provenance({ row }: { row: PropertyRow }) {
  const fields: [string, string | number | null][] = [
    ["UPRN", row.uprn],
    ["Full address", row.full_address],
    ["Address source", row.address_source],
    ["UPRN source", row.uprn_source],
    [
      "Latitude, longitude",
      row.latitude != null && row.longitude != null
        ? `${coordFmt.format(row.latitude)}, ${coordFmt.format(row.longitude)}`
        : null,
    ],
    [
      "Easting, northing",
      row.x_coordinate != null && row.y_coordinate != null
        ? `${row.x_coordinate}, ${row.y_coordinate}`
        : null,
    ],
    ["Row updated", row.updated_at ? new Date(row.updated_at).toLocaleString("en-GB") : null],
  ];

  return (
    <details className="provenance">
      <summary>Data &amp; provenance</summary>
      <dl className="provenance__list">
        {fields.map(([label, value]) => (
          <div key={label} className="provenance__item">
            <dt>{label}</dt>
            <dd>{value ?? "—"}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);
  const canShare = typeof navigator.share === "function";
  const canCopy = typeof navigator.clipboard?.writeText === "function";
  if (!canShare && !canCopy) return null;

  async function share() {
    const url = window.location.href;
    if (canShare) {
      try {
        await navigator.share({ title, url });
      } catch {
        /* the user closed the share sheet */
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard permission denied: nothing useful to do */
    }
  }

  return (
    <button type="button" className="detail-bar__action" onClick={share}>
      {canShare ? "Share" : copied ? "Link copied" : "Copy link"}
    </button>
  );
}

function NotFound({ text }: { text: string }) {
  return (
    <div className="property-page__body">
      <div className="banner">
        <p>{text}</p>
        <Link to="/properties">Search properties</Link>
      </div>
    </div>
  );
}
