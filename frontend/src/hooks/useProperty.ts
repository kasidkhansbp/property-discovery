// Data hook for one property's row (the header of the property screen).
//
// When the screen is opened from a list, the tapped row comes along in the
// navigation state and seeds the cache, so the header renders instantly with
// no request. Opened from a shared link or a reload, it is fetched.

import { useQuery } from "@tanstack/react-query";

import { fetchProperty, type PropertyRow } from "../api/properties";

const STALE_TIME_MS = 5 * 60 * 1000;

export function useProperty(uprn: number | null, seed?: PropertyRow) {
  return useQuery({
    queryKey: ["property", uprn] as const,
    queryFn: ({ signal }) => fetchProperty(uprn as number, signal),
    enabled: uprn != null,
    initialData: seed && seed.uprn === uprn ? seed : undefined,
    staleTime: STALE_TIME_MS,
  });
}
