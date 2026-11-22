// The properties grid (antd Table): one row per UPRN. Address fields are NULL
// for UPRNs with no EPC certificate (about half of them) and render as "—".
//
// Clicking a row does different things per experience (see useIsDesktop):
//   desktop - the row expands: underneath, the property's sales and EPC
//             certificates (PropertyHistory, table layout) and a Maps link.
//             Several rows can be open at once; history is fetched on first
//             open only.
//   mobile  - the row opens the full-screen property screen (/property/:uprn).
//             Only UPRN, address and postcode show (the other columns are
//             `responsive: ["md"]`, i.e. 768px and up).

import { Flex, Table } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState, type MouseEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import type { PropertyRow } from "../api/properties";
import { useIsDesktop } from "../hooks/useIsDesktop";
import { getLastViewedUprn, propertyLinkState, propertyPath } from "../routes";
import { MapsLink } from "./MapsLink";
import { PropertyHistory } from "./PropertyHistory";

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

const DESKTOP_ONLY = ["md" as const];

function columns(isDesktop: boolean): ColumnsType<PropertyRow> {
  return [
    {
      title: "UPRN",
      dataIndex: "uprn",
      align: "right",
      // UPRNs are identifiers: no thousands separators. On mobile it's also a
      // real link, so the row can be opened from the keyboard.
      render: (uprn: number, row) =>
        isDesktop ? (
          <span className="mono">{uprn}</span>
        ) : (
          <Link to={propertyPath(uprn)} state={propertyLinkState(row)} className="mono">
            {uprn}
          </Link>
        ),
    },
    { title: "Address", dataIndex: "address_line_1", render: dash },
    { title: "Town", dataIndex: "posttown", render: dash, responsive: DESKTOP_ONLY },
    { title: "Postcode", dataIndex: "postcode", render: dash, className: "nowrap" },
    { title: "Property type", dataIndex: "property_type", render: dash, responsive: DESKTOP_ONLY },
    { title: "Built form", dataIndex: "built_form", render: dash, responsive: DESKTOP_ONLY },
    { title: "Country", dataIndex: "country", render: dash, responsive: DESKTOP_ONLY },
    { title: "Latitude", dataIndex: "latitude", align: "right", render: coord, responsive: DESKTOP_ONLY },
    { title: "Longitude", dataIndex: "longitude", align: "right", render: coord, responsive: DESKTOP_ONLY },
    { title: "Address source", dataIndex: "address_source", render: dash, responsive: DESKTOP_ONLY },
  ];
}

export function PropertiesTable({ rows, stale }: PropertiesTableProps) {
  const isDesktop = useIsDesktop();
  const navigate = useNavigate();
  const [expanded, setExpanded] = useState<readonly number[]>([]);
  // Read once per mount: the row you just came back from (mobile).
  const [lastViewed] = useState(getLastViewedUprn);

  function toggle(uprn: number) {
    setExpanded((prev) => (prev.includes(uprn) ? prev.filter((u) => u !== uprn) : [...prev, uprn]));
  }

  function onRowClick(e: MouseEvent, row: PropertyRow) {
    // Don't act when the click ended a text selection (copying a UPRN).
    if (window.getSelection()?.toString()) return;
    // Links (UPRN on mobile, Maps) and the expand icon handle their own clicks.
    if ((e.target as HTMLElement).closest("a, .ant-table-row-expand-icon")) return;

    if (isDesktop) toggle(row.uprn);
    else navigate(propertyPath(row.uprn), { state: propertyLinkState(row) });
  }

  return (
    <Table<PropertyRow>
      className="properties-table"
      columns={columns(isDesktop)}
      dataSource={rows}
      rowKey="uprn"
      size="middle"
      pagination={false}
      loading={stale}
      scroll={{ x: "max-content" }}
      locale={{ emptyText: "No properties" }}
      onRow={(row) => ({ onClick: (e) => onRowClick(e, row) })}
      // "You are here" (blue left edge): an expanded row on desktop, the row
      // you came back from on mobile.
      rowClassName={(row) =>
        [
          "property-row",
          isDesktop && expanded.includes(row.uprn) && "property-row--open",
          !isDesktop && row.uprn === lastViewed && "property-row--last-viewed",
        ]
          .filter(Boolean)
          .join(" ")
      }
      expandable={
        isDesktop
          ? {
              expandedRowKeys: expanded as number[],
              onExpand: (_open, row) => toggle(row.uprn),
              expandedRowRender: (row) => (
                <Flex vertical gap={8} className="history-subrow">
                  <MapsLink row={row} />
                  <PropertyHistory uprn={row.uprn} variant="table" />
                </Flex>
              ),
            }
          : undefined
      }
    />
  );
}
