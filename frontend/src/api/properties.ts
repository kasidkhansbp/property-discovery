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

/** How the gateway read the search box (see classify_search in properties_query.py). */
export type SearchMode = "uprn" | "postcode" | "postcode_and_text" | "text";

export interface PropertySearchResult {
  q: string;
  mode: SearchMode;
  limit: number;
  has_more: boolean; // more rows match than were returned
  items: PropertyRow[];
}

/**
 * Search properties (GET /properties/search): a UPRN, a full or partial
 * postcode, an address containing a postcode, or free text. Best matches first,
 * no paging. A query the gateway can't use (e.g. too short) is a 422 ApiError
 * whose message says what to type instead.
 */
export function fetchPropertySearch(
  q: string,
  limit: number,
  signal?: AbortSignal,
): Promise<PropertySearchResult> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return apiGet<PropertySearchResult>("/properties/search", params, signal);
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
