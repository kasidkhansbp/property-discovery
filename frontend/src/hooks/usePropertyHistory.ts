// Data hook over GET /properties/{uprn}/history. Only runs while a row is
// expanded; results are cached, so collapsing and reopening a row is instant.

import { useQuery } from "@tanstack/react-query";

import { fetchPropertyHistory } from "../api/properties";

const STALE_TIME_MS = 5 * 60 * 1000;

export function usePropertyHistory(uprn: number) {
  return useQuery({
    queryKey: ["property-history", uprn] as const,
    queryFn: ({ signal }) => fetchPropertyHistory(uprn, signal),
    staleTime: STALE_TIME_MS,
  });
}
