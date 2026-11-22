// Search results as an antd List, web-search style: a summary line, then per
// property a small "UPRN · postcode" line, the address as the title, and a
// line of details. Words from the query are bolded where they start a word in
// the address.
//
// What a result does depends on the experience (see useIsDesktop):
//   desktop - a "Show sales & EPC history" toggle expands the history inline,
//             next to a Maps link.
//   mobile  - the whole result is one tap target that opens the property
//             screen, and the details line drops coordinates and sources
//             (they are on that screen, under "Data & provenance").

import { DownOutlined, RightOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, List, Typography } from "antd";
import { Fragment, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import type { PropertyRow, PropertySearchResult, SearchMode } from "../api/properties";
import { useIsDesktop } from "../hooks/useIsDesktop";
import { getLastViewedUprn, propertyLinkState, propertyPath } from "../routes";
import { MapsLink } from "./MapsLink";
import { PropertyHistory } from "./PropertyHistory";

const { Text } = Typography;

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

function details(row: PropertyRow, full: boolean) {
  const parts = [row.property_type, row.built_form, row.country].filter(Boolean);
  if (full) {
    if (row.latitude != null && row.longitude != null) {
      parts.push(`${coordFmt.format(row.latitude)}, ${coordFmt.format(row.longitude)}`);
    }
    if (row.address_source) parts.push(`address from ${row.address_source}`);
  }
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
  const isDesktop = useIsDesktop();
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(() => new Set());
  // Read once per mount: the result you just came back from (mobile).
  const [lastViewed] = useState(getLastViewedUprn);

  function toggle(uprn: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (!next.delete(uprn)) next.add(uprn);
      return next;
    });
  }

  if (items.length === 0) {
    return (
      <div className="results">
        <Alert
          type="info"
          showIcon
          message={
            <>
              No properties match <strong>{q}</strong> (searched as {MODE_LABEL[mode]}).
            </>
          }
          description="Check the spelling, try fewer words, or search by postcode. About half of all UPRNs have no address on record yet, so they can only be found by UPRN."
        />
      </div>
    );
  }

  function summary(row: PropertyRow) {
    return (
      <Flex vertical gap={2}>
        <Text type="secondary" className="mono" style={{ fontSize: 12 }}>
          {/* UPRNs are identifiers: no thousands separators. */}
          UPRN {row.uprn}
          {row.postcode && <> · {highlight(row.postcode, q)}</>}
        </Text>
        <Typography.Title
          level={5}
          className={`result__title${row.address_line_1 ? "" : " result__title--none"}`}
        >
          {row.address_line_1 ? highlight(title(row), q) : title(row)}
        </Typography.Title>
        <Text>{details(row, isDesktop)}</Text>
      </Flex>
    );
  }

  return (
    <div className="results">
      <Text className="results__summary eyebrow">
        {has_more ? `Top ${items.length}` : items.length}{" "}
        {items.length === 1 ? "result" : "results"} · searched as {MODE_LABEL[mode]}
      </Text>

      <List<PropertyRow>
        className="results__list"
        dataSource={items}
        loading={stale}
        rowKey="uprn"
        renderItem={(row) => {
          if (!isDesktop) {
            return (
              <List.Item
                className={`result result--mobile${row.uprn === lastViewed ? " result--last-viewed" : ""}`}
              >
                <Link
                  to={propertyPath(row.uprn)}
                  state={propertyLinkState(row)}
                  className="result__link"
                >
                  {summary(row)}
                  <RightOutlined className="result__chevron" aria-hidden />
                </Link>
              </List.Item>
            );
          }

          const open = expanded.has(row.uprn);
          const historyId = `search-history-${row.uprn}`;
          return (
            <List.Item className={`result${open ? " result--open" : ""}`}>
              <Flex vertical gap={6} style={{ width: "100%" }}>
                {summary(row)}
                <Flex wrap align="center" gap="4px 20px">
                  <Button
                    type="text"
                    size="small"
                    className="result__history-toggle"
                    icon={open ? <DownOutlined /> : <RightOutlined />}
                    aria-expanded={open}
                    aria-controls={open ? historyId : undefined}
                    onClick={() => toggle(row.uprn)}
                  >
                    {open ? "Hide sales & EPC history" : "Show sales & EPC history"}
                  </Button>
                  <MapsLink row={row} />
                </Flex>
                {open && (
                  <div id={historyId}>
                    <PropertyHistory uprn={row.uprn} variant="table" />
                  </div>
                )}
              </Flex>
            </List.Item>
          );
        }}
      />

      {has_more && (
        <div className="results__more">
          {onShowMore ? (
            <Button shape="round" onClick={onShowMore} disabled={stale}>
              Show more results
            </Button>
          ) : (
            <Text type="secondary">
              More properties match. Add a postcode or more of the address to narrow it down.
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
