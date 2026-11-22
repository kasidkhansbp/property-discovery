// "Open in Google Maps" for a property. Renders nothing when the UPRN has no
// coordinates. Clicks don't bubble, so it can sit inside a clickable row.

import type { PropertyRow } from "../api/properties";
import { googleMapsUrl } from "../routes";

export function MapsLink({
  row,
  className = "maps-link",
}: {
  row: Pick<PropertyRow, "latitude" | "longitude">;
  className?: string;
}) {
  const href = googleMapsUrl(row);
  if (!href) return null;
  return (
    <a
      className={className}
      href={href}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
    >
      Open in Google Maps ↗
    </a>
  );
}
