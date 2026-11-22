import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createBrowserRouter,
  Link,
  Navigate,
  Outlet,
  RouterProvider,
  ScrollRestoration,
  useLocation,
} from "react-router-dom";

import { BrowseCursorsProvider } from "./hooks/useBrowseCursors";
import { CoverageDashboard } from "./pages/CoverageDashboard";
import { PropertiesDashboard } from "./pages/PropertiesDashboard";
import { PropertyPage } from "./pages/PropertyPage";
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

// `prefixes` decides which tab is highlighted: a property screen belongs to
// the Properties tab.
const VIEWS = [
  { to: "/coverage", label: "UPRN Coverage", prefixes: ["/coverage"] },
  { to: "/quality", label: "Data Quality", prefixes: ["/quality"] },
  { to: "/properties", label: "Properties", prefixes: ["/properties", "/property/"] },
];

function Layout() {
  const { pathname } = useLocation();
  // A property screen is a full-screen detail view: on phones it brings its
  // own top bar (with Back) and the app nav steps aside (see styles.css).
  const detail = pathname.startsWith("/property/");

  return (
    <div className={`app${detail ? " app--detail" : ""}`}>
      <nav className="appnav">
        <div className="appnav__inner">
          <span className="appnav__brand">Property Discovery</span>
          <div className="appnav__tabs">
            {VIEWS.map((v) => {
              const active = v.prefixes.some((p) => pathname.startsWith(p));
              return (
                <Link
                  key={v.to}
                  to={v.to}
                  className={`appnav__tab${active ? " appnav__tab--active" : ""}`}
                  aria-current={active ? "page" : undefined}
                >
                  {v.label}
                </Link>
              );
            })}
          </div>
        </div>
      </nav>

      <Outlet />
      {/* Back restores the list's scroll position; a new screen starts at the top. */}
      <ScrollRestoration />
    </div>
  );
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/coverage" replace /> },
      { path: "coverage", element: <CoverageDashboard /> },
      { path: "quality", element: <QualityDashboard /> },
      { path: "properties", element: <PropertiesDashboard /> },
      { path: "property/:uprn", element: <PropertyPage /> },
      { path: "*", element: <Navigate to="/coverage" replace /> },
    ],
  },
]);

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowseCursorsProvider>
        <RouterProvider router={router} />
      </BrowseCursorsProvider>
    </QueryClientProvider>
  );
}
