// Paths and navigation state shared by the screens that link to a property.

import type { PropertyRow } from "./api/properties";

export const DEFAULT_TITLE = "Property Discovery";

export function propertyPath(uprn: number) {
  return `/property/${uprn}`;
}

/**
 * Google Maps at the property's coordinates, or null without them. On a phone
 * the link opens the maps app; on desktop, Google Maps in a new tab.
 */
export function googleMapsUrl(row: Pick<PropertyRow, "latitude" | "longitude">) {
  if (row.latitude == null || row.longitude == null) return null;
  return `https://www.google.com/maps/search/?api=1&query=${row.latitude},${row.longitude}`;
}

/** Sent along when opening a property from a list, so its header needs no fetch. */
export interface PropertyLinkState {
  row?: PropertyRow;
}

export function propertyLinkState(row: PropertyRow): PropertyLinkState {
  return { row };
}
