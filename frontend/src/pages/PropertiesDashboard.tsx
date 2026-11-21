// The properties screen: the `properties` table (one row per UPRN), 50 rows a
// page. Paging is keyset: `cursors` is the list of cursors visited so far
// (null = first page) and the current page uses the last one. Next pushes the
// page's next_after_uprn, Prev pops, First resets — so every page, however
// deep, is one fast index seek, and going back is served from cache.

import { useState } from "react";

import { ApiError } from "../api/client";
import { CursorPagination } from "../components/CursorPagination";
import { PropertiesTable } from "../components/PropertiesTable";
import { PROPERTIES_PAGE_SIZE, usePropertiesPage } from "../hooks/useProperties";

export function PropertiesDashboard() {
  const [cursors, setCursors] = useState<(number | null)[]>([null]);
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
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1>Properties</h1>
          <p className="dashboard__subtitle">
            One row per UPRN: OS coordinates plus the address from the latest EPC
            certificate · ordered by UPRN
          </p>
        </div>
      </header>

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
    </div>
  );
}
