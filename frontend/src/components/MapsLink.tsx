// "Open in Google Maps" for a property. Renders nothing when the UPRN has no
// coordinates. Clicks don't bubble, so it can sit inside a clickable row.
//
//   variant "link"   - an inline text link (desktop rows and results)
//   variant "button" - a full-width button (the mobile property screen)

import { EnvironmentOutlined } from "@ant-design/icons";
import { Button, Typography } from "antd";
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
      <Button block size="large" icon={<EnvironmentOutlined />} href={href} target="_blank" rel="noreferrer" onClick={stop}>
        Open in Google Maps
      </Button>
    );
  }

  return (
    <Typography.Link href={href} target="_blank" rel="noreferrer" onClick={stop}>
      <EnvironmentOutlined /> Open in Google Maps
    </Typography.Link>
  );
}
