// One property's history: every Land Registry sale and EPC certificate,
// newest first. Nothing is capped or truncated. Two layouts of the same data:
//
//   "table"    - desktop. A compact antd Table (date, kind, price / rating,
//                details, link / reference), shown inline under an expanded
//                property.
//   "timeline" - mobile. An antd Timeline with one Card per event, shown on the
//                full-screen property screen. A sale card leads with the price
//                and the change since the previous sale; an EPC card with the
//                current -> potential rating. Trust in a sale's link to this
//                UPRN is spelled out in words on fuzzy matches (no tooltips:
//                they never show on touch screens).

import { Alert, Button, Card, Flex, Skeleton, Table, Tag, Timeline, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import { BRAND } from "../AntdTheme";
import type { EpcEvent, HistoryEvent, SaleEvent } from "../api/properties";
import { ApiError } from "../api/client";
import { usePropertyHistory } from "../hooks/usePropertyHistory";

const { Text } = Typography;

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

// One colour per kind, shared by the chips and the timeline dots: neutral ink
// for sales (blue is reserved for brand and action), TPMguild's "verified"
// green for certificates.
const KIND_COLOR = { sale: BRAND.ink2, epc: BRAND.verified } as const;
const KIND_WASH = { sale: BRAND.paper3, epc: BRAND.verifiedWash } as const;

/** A TPMguild-style chip: pale wash of the kind's colour, coloured text, pill. */
function KindTag({ kind, label }: { kind: HistoryEvent["kind"]; label: string }) {
  return (
    <Tag
      bordered={false}
      className="kind-chip"
      style={{ background: KIND_WASH[kind], color: KIND_COLOR[kind] }}
    >
      {label}
    </Tag>
  );
}

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

/** An EPC band in the official green-to-red colours (custom: antd has no such scale). */
export function Rating({ band, size }: { band: string | null; size?: "lg" }) {
  const cls = `epc-band${size ? ` epc-band--${size}` : ""}`;
  if (!band) return <span className={`${cls} epc-band--none`}>?</span>;
  const b = band.toUpperCase();
  return <span className={`${cls} epc-band--${b.toLowerCase()}`}>{b}</span>;
}

function RatingChange({ e }: { e: EpcEvent }) {
  return (
    <Flex align="center" gap={4} component="span">
      <Rating band={e.current_energy_rating} />
      <Text type="secondary" aria-label="could reach">
        →
      </Text>
      <Rating band={e.potential_energy_rating} />
    </Flex>
  );
}

// ---- Desktop: table ---------------------------------------------------------

const TABLE_COLUMNS: ColumnsType<HistoryEvent> = [
  {
    title: "Date",
    key: "date",
    width: 100,
    render: (_, e) => <span className="nowrap">{formatDate(e.date)}</span>,
  },
  {
    title: "Event",
    key: "kind",
    width: 68,
    render: (_, e) => <KindTag kind={e.kind} label={e.kind === "sale" ? "Sale" : "EPC"} />,
  },
  {
    title: "Price / rating",
    key: "headline",
    align: "right",
    width: 112,
    render: (_, e) =>
      e.kind === "sale" ? (
        <Text strong className="nowrap">
          {e.price != null ? priceFmt.format(e.price) : "—"}
        </Text>
      ) : (
        <Flex vertical align="flex-end">
          <RatingChange e={e} />
          <Text type="secondary" style={{ fontSize: 11 }}>
            {e.current_energy_efficiency ?? "?"} → {e.potential_energy_efficiency ?? "?"}
          </Text>
        </Flex>
      ),
  },
  {
    title: "Details",
    key: "details",
    render: (_, e) => (
      <>
        <div>{(e.kind === "sale" ? saleDetails(e) : epcDetails(e)) || "—"}</div>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {e.kind === "sale" ? saleAddress(e) : epcAddress(e)}
        </Text>
      </>
    ),
  },
  {
    title: "Link / reference",
    key: "ref",
    width: 132,
    render: (_, e) => {
      if (e.kind === "epc") {
        return (
          <Tooltip title="Certificate number">
            <Text type="secondary" className="mono" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
              {e.certificate_number}
            </Text>
          </Tooltip>
        );
      }
      const fuzzy = e.match_type !== "EXACT";
      return (
        <Tooltip
          title={`Linked to this UPRN by ${e.match_type.toLowerCase()} match (score ${e.match_score.toFixed(2)})`}
        >
          <Tag color={fuzzy ? "warning" : undefined} bordered>
            {fuzzy ? `${e.match_type.toLowerCase()} ${e.match_score.toFixed(2)}` : "exact"}
          </Tag>
        </Tooltip>
      );
    },
  },
];

function HistoryTable({ events }: { events: HistoryEvent[] }) {
  return (
    <Table<HistoryEvent>
      size="small"
      bordered
      columns={TABLE_COLUMNS}
      dataSource={events}
      rowKey={eventKey}
      pagination={false}
      // Fixed layout at 100% width: Details takes what the fixed columns leave
      // and wraps, so the whole table fits without a horizontal scrollbar.
      tableLayout="fixed"
    />
  );
}

// ---- Mobile: timeline -------------------------------------------------------

/** "+£42,000 (+18%) since 2014", or null when either price is missing. */
function priceChange(e: SaleEvent, prev: SaleEvent | undefined) {
  if (!prev || e.price == null || prev.price == null || prev.price <= 0) return null;
  const diff = e.price - prev.price;
  const pct = Math.round((diff / prev.price) * 100);
  const sign = diff > 0 ? "+" : diff < 0 ? "−" : "±";
  const since = prev.date ? ` since ${prev.date.slice(0, 4)}` : "";
  return {
    type: diff > 0 ? ("success" as const) : diff < 0 ? ("danger" as const) : ("secondary" as const),
    text: `${sign}${priceFmt.format(Math.abs(diff))} (${sign}${Math.abs(pct)}%)${since}`,
  };
}

function SaleBody({ e, prev }: { e: SaleEvent; prev: SaleEvent | undefined }) {
  const details = saleDetails(e);
  const change = priceChange(e, prev);
  return (
    <Flex vertical gap={2}>
      <Text strong className="timeline-headline">
        {e.price != null ? priceFmt.format(e.price) : "Price not recorded"}
      </Text>
      {change && (
        <Text type={change.type} strong style={{ fontSize: 13 }}>
          {change.text}
        </Text>
      )}
      {details && <Text>{details}</Text>}
      {e.match_type !== "EXACT" && (
        // A non-exact link is a judgement call: show the address the sale was
        // recorded under, so it can be checked against this property.
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 6 }}
          message={`Approximate match (${e.match_type.toLowerCase()}, score ${e.match_score.toFixed(2)})`}
          description={`Recorded as: ${saleAddress(e) || "no address"}`}
        />
      )}
    </Flex>
  );
}

function EpcBody({ e }: { e: EpcEvent }) {
  const details = epcDetails(e);
  return (
    <Flex vertical gap={2}>
      <Flex align="center" gap={8} className="timeline-headline timeline-headline--rating">
        <RatingChange e={e} />
        <Text type="secondary" style={{ fontSize: 13 }}>
          {e.current_energy_efficiency ?? "?"} → {e.potential_energy_efficiency ?? "?"}
        </Text>
      </Flex>
      {details && <Text>{details}</Text>}
      <Text type="secondary" className="mono" style={{ fontSize: 12, overflowWrap: "anywhere" }}>
        Certificate {e.certificate_number}
      </Text>
    </Flex>
  );
}

function HistoryTimeline({ events }: { events: HistoryEvent[] }) {
  // Events are newest first, so each sale's previous sale is the next one down.
  const sales = events.filter((e): e is SaleEvent => e.kind === "sale");
  const previousSale = new Map(sales.map((s, i) => [s.transaction_id, sales[i + 1]]));

  return (
    <Timeline
      className="property-timeline"
      items={events.map((e) => ({
        key: eventKey(e),
        color: KIND_COLOR[e.kind],
        children: (
          <Card size="small">
            <Flex align="center" gap={8} style={{ marginBottom: 4 }}>
              <KindTag kind={e.kind} label={e.kind === "sale" ? "Sold" : "EPC"} />
              <Text type="secondary">
                <time dateTime={e.date ?? undefined}>{formatDate(e.date)}</time>
              </Text>
            </Flex>
            {e.kind === "sale" ? (
              <SaleBody e={e} prev={previousSale.get(e.transaction_id)} />
            ) : (
              <EpcBody e={e} />
            )}
          </Card>
        ),
      }))}
    />
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
    return (
      <div className={cls} aria-busy="true">
        <Skeleton active title={false} paragraph={{ rows: variant === "timeline" ? 6 : 3 }} />
      </div>
    );
  }

  if (history.isError) {
    // A failed request says nothing about the house, so it is never shown as
    // "no data": that would claim a property was never sold when the gateway
    // simply didn't answer.
    return (
      <div className={cls}>
        <Alert
          type="error"
          showIcon
          message={errorMessage(history.error)}
          action={
            <Button size="small" onClick={() => history.refetch()}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  const { events, sale_count, epc_count } = history.data;

  if (events.length === 0) {
    return (
      <div className={cls}>
        <Alert
          type="info"
          showIcon
          message="No sales or EPC data available for this property."
          description="It may not have been sold since Land Registry records began in 1995, or a sale may exist that hasn't been matched to this UPRN. No EPC certificate was found for it either."
        />
      </div>
    );
  }

  return (
    <div className={cls}>
      <Text type="secondary" className="history__summary">
        {sale_count > 0 ? plural(sale_count, "sale", "sales") : <Text strong>No recorded sales</Text>}
        {" · "}
        {epc_count > 0 ? (
          plural(epc_count, "EPC certificate", "EPC certificates")
        ) : (
          <Text strong>No EPC data available</Text>
        )}
        {sale_count === 0 &&
          " · possibly not sold since 1995, or a sale hasn't been matched to this UPRN"}
      </Text>
      {variant === "timeline" ? (
        <HistoryTimeline events={events} />
      ) : (
        <HistoryTable events={events} />
      )}
    </div>
  );
}
