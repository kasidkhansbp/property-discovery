// Which experience to give: desktop or mobile.
//
// The two differ in behaviour, not just layout, so CSS alone can't decide:
//   desktop - clicking a property expands its history inline, under the row
//   mobile  - tapping a property opens the full-screen /property/:uprn screen
//
// The breakpoint is antd's `md` (768px), which styles.css also uses, so
// the behaviour and the layout always switch together. It updates live when
// the window is resized or a tablet is rotated.

import { useSyncExternalStore } from "react";

export const DESKTOP_MEDIA_QUERY = "(min-width: 768px)";

function subscribe(onChange: () => void) {
  const mql = window.matchMedia(DESKTOP_MEDIA_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

function getSnapshot() {
  return window.matchMedia(DESKTOP_MEDIA_QUERY).matches;
}

export function useIsDesktop() {
  return useSyncExternalStore(subscribe, getSnapshot);
}
