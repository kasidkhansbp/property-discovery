// Page controls for keyset paging: First / Prev / Next only. There's no Last or
// jump-to-page because the API has no offset (deep offsets are slow on ~42M
// rows). The total is a planner estimate, so it's shown with a "~".

interface CursorPaginationProps {
  page: number; // zero-based
  pageSize: number;
  rowsOnPage: number;
  estimatedTotal: number;
  hasNext: boolean;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  busy?: boolean;
}

const numberFmt = new Intl.NumberFormat("en-GB");

export function CursorPagination({
  page,
  pageSize,
  rowsOnPage,
  estimatedTotal,
  hasNext,
  onFirst,
  onPrev,
  onNext,
  busy,
}: CursorPaginationProps) {
  const first = page * pageSize + 1;
  const last = page * pageSize + rowsOnPage;
  const pageCount = Math.max(1, Math.ceil(estimatedTotal / pageSize));
  const atStart = page === 0;

  return (
    <div className="pagination">
      <div className="pagination__caption">
        {rowsOnPage === 0 ? (
          "No rows"
        ) : (
          <>
            Showing <strong>{numberFmt.format(first)}</strong>–
            <strong>{numberFmt.format(last)}</strong> of ~
            <strong>{numberFmt.format(estimatedTotal)}</strong>
          </>
        )}
        {busy && <span className="pagination__busy"> · updating…</span>}
      </div>
      <div className="pagination__controls">
        <button type="button" onClick={onFirst} disabled={atStart}>
          « First
        </button>
        <button type="button" onClick={onPrev} disabled={atStart}>
          ‹ Prev
        </button>
        <span className="pagination__page">
          Page {numberFmt.format(page + 1)} of ~{numberFmt.format(pageCount)}
        </span>
        <button type="button" onClick={onNext} disabled={!hasNext}>
          Next ›
        </button>
      </div>
    </div>
  );
}
