// The "all properties" table's keyset cursors, held above the router.
//
// Opening a property navigates away and unmounts the table, so if the table
// owned its cursors, Back would always land on page 1. Held here, Back returns
// to the page you left (served from the query cache, so instantly).

import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

/** Cursors visited so far (null = first page); the current page uses the last one. */
export type Cursors = (number | null)[];

type CursorState = [Cursors, Dispatch<SetStateAction<Cursors>>];

const BrowseCursorsContext = createContext<CursorState | null>(null);

export function BrowseCursorsProvider({ children }: { children: ReactNode }) {
  const state = useState<Cursors>([null]);
  return <BrowseCursorsContext.Provider value={state}>{children}</BrowseCursorsContext.Provider>;
}

export function useBrowseCursors(): CursorState {
  const state = useContext(BrowseCursorsContext);
  if (!state) throw new Error("useBrowseCursors needs a BrowseCursorsProvider");
  return state;
}
