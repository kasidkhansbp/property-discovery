import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CoverageDashboard } from "./pages/CoverageDashboard";
import { QualityDashboard } from "./pages/QualityDashboard";

// One client for the app. Defaults suit a read-only dashboard: don't refetch on
// window focus (the data changes on a pipeline cadence, not per click), and give
// a failed request a single retry.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

type View = "coverage" | "quality";

const VIEWS: { id: View; label: string }[] = [
  { id: "coverage", label: "UPRN Coverage" },
  { id: "quality", label: "Data Quality" },
];

export function App() {
  const [view, setView] = useState<View>("coverage");

  return (
    <QueryClientProvider client={queryClient}>
      <nav className="appnav">
        <div className="appnav__inner">
          <span className="appnav__brand">Property Discovery</span>
          <div className="appnav__tabs">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                className={`appnav__tab${view === v.id ? " appnav__tab--active" : ""}`}
                aria-current={view === v.id ? "page" : undefined}
                onClick={() => setView(v.id)}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {view === "coverage" ? <CoverageDashboard /> : <QualityDashboard />}
    </QueryClientProvider>
  );
}
