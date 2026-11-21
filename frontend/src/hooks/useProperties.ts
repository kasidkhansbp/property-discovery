// Data hook over GET /properties. A page is identified by its cursor (the uprn
// it starts after; null = first page). Once a page arrives we know the next
// page's cursor, so we prefetch it — pressing Next is then served from cache.

import { useEffect } from "react";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchPropertiesPage } from "../api/properties";

// Matches the gateway's DEFAULT_LIMIT (gateway/app/properties_query.py).
export const PROPERTIES_PAGE_SIZE = 50;

const STALE_TIME_MS = 5 * 60 * 1000;

function propertiesKey(afterUprn: number | null) {
  return ["properties", PROPERTIES_PAGE_SIZE, afterUprn] as const;
}

export function usePropertiesPage(afterUprn: number | null) {
  const client = useQueryClient();

  const query = useQuery({
    queryKey: propertiesKey(afterUprn),
    queryFn: ({ signal }) => fetchPropertiesPage(afterUprn, PROPERTIES_PAGE_SIZE, signal),
    staleTime: STALE_TIME_MS,
    // Keep showing the current rows while the next page loads, instead of a blank table.
    placeholderData: keepPreviousData,
  });

  const nextCursor = query.isPlaceholderData ? null : (query.data?.next_after_uprn ?? null);

  useEffect(() => {
    if (nextCursor == null) return;
    client.prefetchQuery({
      queryKey: propertiesKey(nextCursor),
      queryFn: ({ signal }) => fetchPropertiesPage(nextCursor, PROPERTIES_PAGE_SIZE, signal),
      staleTime: STALE_TIME_MS,
    });
  }, [client, nextCursor]);

  return query;
}
