// Data hook over GET /properties/search. Idle (no request) until there is a
// submitted query. A 4xx means the query itself is unusable (too short, too
// broad), so it isn't retried: retrying would give the same answer.

import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { fetchPropertySearch } from "../api/properties";

// Match DEFAULT_SEARCH_LIMIT / MAX_SEARCH_LIMIT in gateway/app/properties_query.py.
export const SEARCH_PAGE_SIZE = 20;
export const SEARCH_MAX_LIMIT = 100;

const STALE_TIME_MS = 5 * 60 * 1000;

export function usePropertySearch(q: string, limit: number) {
  const query = q.trim();
  return useQuery({
    queryKey: ["property-search", query, limit] as const,
    queryFn: ({ signal }) => fetchPropertySearch(query, limit, signal),
    enabled: query.length > 0,
    staleTime: STALE_TIME_MS,
    // "Show more" keeps the current results on screen while the longer list loads.
    placeholderData: keepPreviousData,
    retry: (failures, error) =>
      !(error instanceof ApiError && error.status >= 400 && error.status < 500) &&
      failures < 1,
  });
}
