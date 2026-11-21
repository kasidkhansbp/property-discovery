// Typed access to GET /properties. Mirrors PropertyRow / PropertiesPage in
// gateway/app/schemas.py. Paging is keyset-only: pass the previous page's
// `next_after_uprn` as `afterUprn` to get the next page (no offset, so every
// page costs the same however deep you go).

import { apiGet } from "./client";

export interface PropertyRow {
  uprn: number;
  full_address: string | null;
  address_line_1: string | null;
  posttown: string | null;
  postcode: string | null;
  postcode_clean: string | null;
  country: string | null;
  property_type: string | null;
  built_form: string | null;
  uprn_source: string | null;
  address_source: string | null;
  latitude: number | null;
  longitude: number | null;
  x_coordinate: number | null;
  y_coordinate: number | null;
  updated_at: string;
}

export interface PropertiesPage {
  total: number; // planner estimate, see total_is_estimate
  total_is_estimate: boolean;
  limit: number;
  after_uprn: number | null;
  next_after_uprn: number | null; // null on the last page
  items: PropertyRow[];
}

/** One page of properties ordered by uprn (GET /properties). */
export function fetchPropertiesPage(
  afterUprn: number | null,
  limit: number,
  signal?: AbortSignal,
): Promise<PropertiesPage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (afterUprn != null) params.set("after_uprn", String(afterUprn));
  return apiGet<PropertiesPage>("/properties", params, signal);
}
