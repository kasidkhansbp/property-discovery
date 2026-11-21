// The properties screen: a search box on top, and below it either the search
// results (while a query is submitted) or the full `properties` table (one row
// per UPRN), 50 rows a page.
//
// Table paging is keyset: `cursors` is the list of cursors visited so far
// (null = first page) and the current page uses the last one. Next pushes the
// page's next_after_uprn, Prev pops, First resets — so every page, however
// deep, is one fast index seek, and going back is served from cache. The
// cursors survive a search, so clearing it returns to the same table page.

import { useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import { ApiError } from "../api/client";
import { CursorPagination } from "../components/CursorPagination";
import { PropertiesTable } from "../components/PropertiesTable";
import { PropertySearchBar } from "../components/PropertySearchBar";
import { PropertySearchResults } from "../components/PropertySearchResults";
import { PROPERTIES_PAGE_SIZE, usePropertiesPage } from "../hooks/useProperties";
import {
  SEARCH_MAX_LIMIT,
  SEARCH_PAGE_SIZE,
  usePropertySearch,
} from "../hooks/usePropertySearch";

export function PropertiesDashboard() {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchLimit, setSearchLimit] = useState(SEARCH_PAGE_SIZE);
  const search = usePropertySearch(searchQuery, searchLimit);
  const searching = searchQuery.length > 0;
  // Owned here, not by the table, so a search (which unmounts the table)
  // doesn't lose the page you were on.
  const [cursors, setCursors] = useState<Cursors>([null]);

  function runSearch(q: string) {
    setSearchQuery(q);
    setSearchLimit(SEARCH_PAGE_SIZE);
  }

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>Properties</h1>
          <p className="dashboard__subtitle">
            One row per UPRN: OS coordinates plus the address from the latest EPC
            certificate
          </p>
        </div>
      </header>

      <PropertySearchBar value={searchQuery} onSearch={runSearch} busy={search.isFetching} />

      {searching ? (
        <SearchSection
          search={search}
          canShowMore={searchLimit < SEARCH_MAX_LIMIT}
          onShowMore={() => setSearchLimit(SEARCH_MAX_LIMIT)}
          onClear={() => runSearch("")}
        />
      ) : (
        <AllProperties cursors={cursors} setCursors={setCursors} />
      )}
    </div>
  );
}

function SearchSection({
  search,
  canShowMore,
  onShowMore,
  onClear,
}: {
  search: ReturnType<typeof usePropertySearch>;
  canShowMore: boolean;
  onShowMore: () => void;
  onClear: () => void;
}) {
  const back = (
    <button type="button" className="link-button" onClick={onClear}>
      ← Back to all properties
    </button>
  );

  return (
    <>
      <div className="results__back">{back}</div>
      <SearchBody search={search} canShowMore={canShowMore} onShowMore={onShowMore} back={back} />
    </>
  );
}

function SearchBody({
  search,
  canShowMore,
  onShowMore,
  back,
}: {
  search: ReturnType<typeof usePropertySearch>;
  canShowMore: boolean;
  onShowMore: () => void;
  back: ReactNode;
}) {
  if (search.isError) {
    const err = search.error;
    // 4xx: the query can't be used as typed (too short, too broad). The message
    // says what to type instead, so show it as guidance, not as a failure.
    if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
      return (
        <div className="results">
          <p className="results__tip results__tip--warn">{err.message}</p>
        </div>
      );
    }
    return (
      <div className="banner banner--error" role="alert">
        <strong>Search failed.</strong>{" "}
        {err instanceof ApiError ? `${err.message} (HTTP ${err.status})` : String(err)}
        <button type="button" onClick={() => search.refetch()}>
          Retry
        </button>
      </div>
    );
  }

  if (!search.data) {
    return <div className="results results__summary">Searching…</div>;
  }

  return (
    <>
      <PropertySearchResults
        result={search.data}
        stale={search.isPlaceholderData || search.isFetching}
        onShowMore={canShowMore ? onShowMore : undefined}
      />
      {/* Repeat the top link after a long list, so it's in reach at the end. */}
      {search.data.items.length > 5 && back}
    </>
  );
}

type Cursors = (number | null)[];

function AllProperties({
  cursors,
  setCursors,
}: {
  cursors: Cursors;
  setCursors: Dispatch<SetStateAction<Cursors>>;
}) {
  const page = cursors.length - 1;
  const properties = usePropertiesPage(cursors[page]);

  const data = properties.data;
  const stale = properties.isPlaceholderData || properties.isFetching;
  // While showing the previous page's rows as a placeholder, its cursor would be wrong.
  const nextCursor = properties.isPlaceholderData ? null : (data?.next_after_uprn ?? null);

  function goNext() {
    if (nextCursor != null) setCursors((c) => [...c, nextCursor]);
  }

  function goPrev() {
    setCursors((c) => (c.length > 1 ? c.slice(0, -1) : c));
  }

  function goFirst() {
    setCursors([null]);
  }

  return (
    <>
      <p className="results__summary">All properties · ordered by UPRN</p>

      {properties.isError && (
        <div className="banner banner--error" role="alert">
          <strong>Couldn’t load properties.</strong>{" "}
          {properties.error instanceof ApiError
            ? `${properties.error.message} (HTTP ${properties.error.status})`
            : String(properties.error)}
          <button type="button" onClick={() => properties.refetch()}>
            Retry
          </button>
        </div>
      )}

      {properties.isLoading && !data ? (
        <div className="banner">Loading properties…</div>
      ) : (
        data && (
          <>
            <PropertiesTable rows={data.items} stale={stale} />
            <CursorPagination
              page={page}
              pageSize={PROPERTIES_PAGE_SIZE}
              rowsOnPage={data.items.length}
              estimatedTotal={data.total}
              hasNext={nextCursor != null}
              onFirst={goFirst}
              onPrev={goPrev}
              onNext={goNext}
              busy={stale}
            />
          </>
        )
      )}
    </>
  );
}
