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

/**
 * One property by UPRN, or null if there is no such UPRN. There is no
 * GET /properties/{uprn}: the search endpoint's UPRN mode is an exact
 * `WHERE uprn = ...` lookup, so it serves the same purpose.
 */
export async function fetchProperty(
  uprn: number,
  signal?: AbortSignal,
): Promise<PropertyRow | null> {
  const result = await fetchPropertySearch(String(uprn), 1, signal);
  return result.items.find((row) => row.uprn === uprn) ?? null;
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

// --- One property's history (GET /properties/{uprn}/history) ---------------
// Mirrors SaleEvent / EpcEvent / PropertyHistory in gateway/app/schemas.py.

/** A Land Registry sale linked to the UPRN by reconciliation. */
export interface SaleEvent {
  kind: "sale";
  date: string | null; // transfer_date, YYYY-MM-DD
  transaction_id: string;
  price: number | null;
  property_type: string | null; // D / S / T / F / O
  old_new: string | null; // Y = new build
  duration: string | null; // F = freehold, L = leasehold
  saon: string | null;
  paon: string | null;
  street: string | null;
  locality: string | null;
  town_city: string | null;
  postcode: string | null;
  ppd_category: string | null; // A = standard, B = additional
  match_type: string; // EXACT / FUZZY
  match_score: number;
}

/** An EPC certificate lodged for the UPRN. */
export interface EpcEvent {
  kind: "epc";
  date: string | null; // lodgement_date, YYYY-MM-DD
  certificate_number: string;
  inspection_date: string | null;
  current_energy_rating: string | null;
  potential_energy_rating: string | null;
  current_energy_efficiency: number | null;
  potential_energy_efficiency: number | null;
  property_type: string | null;
  built_form: string | null;
  total_floor_area: number | null;
  construction_age_band: string | null;
  tenure: string | null;
  transaction_type: string | null;
  co2_emissions_current: number | null;
  address1: string | null;
  address2: string | null;
  address3: string | null;
  postcode: string | null;
}

export type HistoryEvent = SaleEvent | EpcEvent;

export interface PropertyHistory {
  uprn: number;
  sale_count: number;
  epc_count: number;
  events: HistoryEvent[]; // every sale and certificate, newest first (no cap)
}

/** Every sale and EPC certificate for one UPRN, merged newest first. */
export function fetchPropertyHistory(
  uprn: number,
  signal?: AbortSignal,
): Promise<PropertyHistory> {
  return apiGet<PropertyHistory>(`/properties/${uprn}/history`, undefined, signal);
}
