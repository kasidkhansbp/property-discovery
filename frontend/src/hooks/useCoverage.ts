// Data hooks over the coverage API.
//
// `useCoveragePage` returns the current page (100 rows) and, as a side effect,
// warms the cache for the next few pages so paging forward is instant. The
// prefetch is what the requirement calls "API calls made 3-5 pages ahead": while
// the user looks at page N, React Query quietly fetches N+1 .. N+PREFETCH_AHEAD
// and keeps them in cache, deduped against any real navigation.

import { useEffect } from "react";
import {
  keepPreviousData,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import {
  fetchCoveragePage,
  fetchFilterOptions,
  type CoverageQuery,
  type Filters,
  type SortColumn,
  type SortDir,
} from "../api/coverage";

// One page is 100 rows — the gateway's DEFAULT_LIMIT (query.py).
export const PAGE_SIZE = 100;

// How many pages ahead to prefetch. The brief asked for 3-5; 4 is the middle.
export const PREFETCH_AHEAD = 4;

// Keep fetched pages "fresh" for 5 minutes so a prefetched page isn't refetched
// the instant the user lands on it, while still picking up DB changes on reload.
const STALE_TIME_MS = 5 * 60 * 1000;

/**
 * React Query key for one page. Pages differ only by `offset`, so prefetched and
 * navigated-to pages share a key and are served from cache without a second call.
 * Filters go in as a value (not stringified) — React Query hashes it stably.
 */
function coverageKey(query: CoverageQuery) {
  return [
    "coverage",
    query.filters,
    query.sortBy,
    query.sortDir,
    query.limit,
    query.offset,
  ] as const;
}

function prefetchPage(client: QueryClient, query: CoverageQuery) {
  return client.prefetchQuery({
    queryKey: coverageKey(query),
    queryFn: ({ signal }) => fetchCoveragePage(query, signal),
    staleTime: STALE_TIME_MS,
  });
}

export interface UseCoveragePageArgs {
  filters: Filters;
  sortBy: SortColumn;
  sortDir: SortDir;
  /** Zero-based page index. */
  page: number;
}

export function useCoveragePage({ filters, sortBy, sortDir, page }: UseCoveragePageArgs) {
  const client = useQueryClient();
  const base = { filters, sortBy, sortDir, limit: PAGE_SIZE };

  const query = useQuery({
    queryKey: coverageKey({ ...base, offset: page * PAGE_SIZE }),
    queryFn: ({ signal }) => fetchCoveragePage({ ...base, offset: page * PAGE_SIZE }, signal),
    // Show the previous page's rows (greyed by the caller) while the next loads,
    // so the table doesn't blank out on every page change.
    placeholderData: keepPreviousData,
    staleTime: STALE_TIME_MS,
  });

  const total = query.data?.total;

  useEffect(() => {
    if (total == null) return;
    const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);
    for (let step = 1; step <= PREFETCH_AHEAD; step++) {
      const ahead = page + step;
      if (ahead > lastPage) break;
      void prefetchPage(client, { ...base, offset: ahead * PAGE_SIZE });
    }
    // `base` is rebuilt each render; depend on its primitive parts instead. The
    // filters object is compared by its stable JSON so new-but-equal objects
    // (e.g. a re-render) don't re-trigger prefetching.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, total, page, sortBy, sortDir, JSON.stringify(filters)]);

  return query;
}

/** Cascading dropdown values for the current filter selection. */
export function useFilterOptions(filters: Filters) {
  return useQuery({
    queryKey: ["filter-options", filters],
    queryFn: ({ signal }) => fetchFilterOptions(filters, signal),
    staleTime: STALE_TIME_MS,
  });
}
