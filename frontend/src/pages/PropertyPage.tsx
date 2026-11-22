// The property screen (/property/:uprn): one house, full screen. Built from
// Ant Design components.
//
// Built for a phone first: a top bar with Back and Share, then a hero card
// (address, key facts, last sale, latest EPC), then the full timeline, then
// the technical fields tucked into "Data & provenance". On wide screens the
// hero and provenance sit in a left column beside the timeline.

import { LeftOutlined, LinkOutlined, ShareAltOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Flex,
  Result,
  Row,
  Skeleton,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import type { EpcEvent, PropertyRow, SaleEvent } from "../api/properties";
import { MapsLink } from "../components/MapsLink";
import { formatDate, priceFmt, PropertyHistory, Rating } from "../components/PropertyHistory";
import { useProperty } from "../hooks/useProperty";
import { usePropertyHistory } from "../hooks/usePropertyHistory";
import { DEFAULT_TITLE, setLastViewedUprn, type PropertyLinkState } from "../routes";

const { Text, Title } = Typography;

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
    if (uprn != null) setLastViewedUprn(uprn);
  }, [uprn]);

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
      {/* antd has no mobile top bar, so this one is ours, with antd buttons. */}
      <header className="detail-bar">
        <Button type="text" size="large" icon={<LeftOutlined />} onClick={goBack} className="detail-bar__btn">
          Back
        </Button>
        <Text strong ellipsis className="detail-bar__title">
          {row ? headline(row) : ""}
        </Text>
        {row ? <ShareButton title={headline(row)} /> : <span className="detail-bar__spacer" />}
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
        <Alert
          type="error"
          showIcon
          message="Couldn’t load this property."
          description={err instanceof ApiError ? `${err.message} (HTTP ${err.status})` : String(err)}
          action={
            <Button size="small" danger onClick={() => property.refetch()}>
              Retry
            </Button>
          }
        />
      </div>
    );
  }

  if (property.data === null) {
    return <NotFound text={`There is no property with UPRN ${uprn}.`} />;
  }

  const row = property.data;

  return (
    <div className="property-page__body">
      {row ? (
        <Hero row={row} />
      ) : (
        <Card className="property-hero">
          <Skeleton active paragraph={{ rows: 5 }} />
        </Card>
      )}

      <section className="property-page__timeline" aria-labelledby="timeline-heading">
        <h2 id="timeline-heading" className="eyebrow section-eyebrow">
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
  const facts = [row.property_type, row.built_form, row.country].filter(Boolean) as string[];
  // While history loads, the stats show a skeleton; if it failed, a dash (the
  // timeline below shows the error and a Retry).
  const lastSoldValue: number | string = history.isError
    ? "—"
    : lastSale
      ? (lastSale.price ?? "—")
      : "No sales";
  const epcFallback = history.isError ? "—" : "No EPC";

  return (
    <Card className="property-hero" aria-label="Property summary">
      <Title level={3} style={{ margin: 0 }} type={row.address_line_1 ? undefined : "secondary"} italic={!row.address_line_1}>
        {headline(row)}
      </Title>
      {place && (
        <Text type="secondary" style={{ fontSize: 15 }}>
          {place}
        </Text>
      )}

      {facts.length > 0 && (
        <Flex wrap gap={6} style={{ marginTop: 14 }} aria-label="Key facts">
          {facts.map((f) => (
            <Tag key={f} style={{ marginInlineEnd: 0 }}>
              {f}
            </Tag>
          ))}
        </Flex>
      )}

      <Row gutter={10} style={{ marginTop: 16 }}>
        <Col span={12}>
          <Card size="small" className="property-stat">
            <Statistic
              title={<span className="eyebrow">Last sold</span>}
              loading={history.isPending}
              value={lastSoldValue}
              formatter={(v) => (typeof v === "number" ? priceFmt.format(v) : v)}
              valueStyle={typeof lastSoldValue === "number" ? undefined : { fontSize: 15 }}
            />
            {lastSale && <Text type="secondary" style={{ fontSize: 12 }}>{formatDate(lastSale.date)}</Text>}
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" className="property-stat">
            <Statistic
              title={<span className="eyebrow">Energy rating</span>}
              loading={history.isPending}
              value={latestEpc ? " " : epcFallback}
              valueRender={(node) =>
                latestEpc ? <Rating band={latestEpc.current_energy_rating} size="lg" /> : node
              }
              valueStyle={latestEpc ? undefined : { fontSize: 15 }}
            />
            {latestEpc && <Text type="secondary" style={{ fontSize: 12 }}>{formatDate(latestEpc.date)}</Text>}
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: 14 }}>
        <MapsLink row={row} variant="button" />
      </div>
    </Card>
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
    <Collapse
      className="provenance"
      items={[
        {
          key: "provenance",
          label: <span className="eyebrow">Data &amp; provenance</span>,
          children: (
            <Descriptions
              column={1}
              size="small"
              layout="vertical"
              colon={false}
              items={fields.map(([label, value]) => ({
                key: label,
                label,
                children: <span style={{ overflowWrap: "anywhere" }}>{value ?? "—"}</span>,
              }))}
            />
          ),
        },
      ]}
    />
  );
}

function ShareButton({ title }: { title: string }) {
  const [copied, setCopied] = useState(false);
  const canShare = typeof navigator.share === "function";
  const canCopy = typeof navigator.clipboard?.writeText === "function";
  if (!canShare && !canCopy) return <span className="detail-bar__spacer" />;

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
    <Button
      type="text"
      size="large"
      className="detail-bar__btn"
      icon={canShare ? <ShareAltOutlined /> : <LinkOutlined />}
      onClick={share}
    >
      {canShare ? "Share" : copied ? "Copied" : "Copy link"}
    </Button>
  );
}

function NotFound({ text }: { text: string }) {
  return (
    <div className="property-page__body">
      <Result
        status="404"
        title="Property not found"
        subTitle={text}
        extra={
          <Link to="/properties">
            <Button type="primary">Search properties</Button>
          </Link>
        }
      />
    </div>
  );
}
