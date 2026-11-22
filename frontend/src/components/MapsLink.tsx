// "Open in Google Maps" for a property. Renders nothing when the UPRN has no
// coordinates. Clicks don't bubble, so it can sit inside a clickable row.
//
//   variant "link"   - an inline text link (desktop rows and results):
//                      underlined, with a map pin and an external-link arrow
//                      so it reads as "opens Google Maps in a new tab".
//   variant "button" - a full-width button (the mobile property screen).
//
// Ink, not blue: blue is reserved for brand and action (see AntdTheme.tsx).

import { EnvironmentOutlined, ExportOutlined } from "@ant-design/icons";
import { Button } from "antd";
import type { MouseEvent } from "react";

import type { PropertyRow } from "../api/properties";
import { googleMapsUrl } from "../routes";

const stop = (e: MouseEvent) => e.stopPropagation();

export function MapsLink({
  row,
  variant = "link",
}: {
  row: Pick<PropertyRow, "latitude" | "longitude">;
  variant?: "link" | "button";
}) {
  const href = googleMapsUrl(row);
  if (!href) return null;

  if (variant === "button") {
    return (
      <Button
        block
        size="large"
        icon={<EnvironmentOutlined />}
        href={href}
        target="_blank"
        rel="noreferrer"
        onClick={stop}
      >
        Open in Google Maps <ExportOutlined className="maps-link__external" aria-hidden />
      </Button>
    );
  }

  return (
    <a className="maps-link" href={href} target="_blank" rel="noreferrer" onClick={stop}>
      <EnvironmentOutlined aria-hidden />
      <span className="maps-link__text">Open in Google Maps</span>
      <ExportOutlined className="maps-link__external" aria-hidden />
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}
