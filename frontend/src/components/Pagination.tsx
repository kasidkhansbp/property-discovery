// Page controls for the 100-row pages: a "showing X–Y of N" caption plus
// first/prev/next/last. The dashboard owns the page index; this is presentation.

import { PAGE_SIZE } from "../hooks/useCoverage";

interface PaginationProps {
  page: number; // zero-based
  total: number;
  onPageChange: (page: number) => void;
  busy?: boolean;
}

const numberFmt = new Intl.NumberFormat("en-GB");

export function Pagination({ page, total, onPageChange, busy }: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const clampedPage = Math.min(page, pageCount - 1);
  const first = total === 0 ? 0 : clampedPage * PAGE_SIZE + 1;
  const last = Math.min(total, (clampedPage + 1) * PAGE_SIZE);

  const atStart = clampedPage <= 0;
  const atEnd = clampedPage >= pageCount - 1;

  return (
    <div className="pagination">
      <div className="pagination__caption">
        {total === 0 ? (
          "No rows"
        ) : (
          <>
            Showing <strong>{numberFmt.format(first)}</strong>–
            <strong>{numberFmt.format(last)}</strong> of{" "}
            <strong>{numberFmt.format(total)}</strong>
          </>
        )}
        {busy && <span className="pagination__busy"> · updating…</span>}
      </div>
      <div className="pagination__controls">
        <button type="button" onClick={() => onPageChange(0)} disabled={atStart}>
          « First
        </button>
        <button
          type="button"
          onClick={() => onPageChange(clampedPage - 1)}
          disabled={atStart}
        >
          ‹ Prev
        </button>
        <span className="pagination__page">
          Page {numberFmt.format(clampedPage + 1)} of {numberFmt.format(pageCount)}
        </span>
        <button
          type="button"
          onClick={() => onPageChange(clampedPage + 1)}
          disabled={atEnd}
        >
          Next ›
        </button>
        <button
          type="button"
          onClick={() => onPageChange(pageCount - 1)}
          disabled={atEnd}
        >
          Last »
        </button>
      </div>
    </div>
  );
}
