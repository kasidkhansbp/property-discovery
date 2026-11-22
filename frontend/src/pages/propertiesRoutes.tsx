// The Properties screens as lazy route modules (see App.tsx). Everything they
// import, Ant Design included, lands in a separate chunk that loads on first
// visit to the Properties tab, so the other tabs don't download antd.

import { AntdTheme } from "../AntdTheme";
import { PropertiesDashboard } from "./PropertiesDashboard";
import { PropertyPage } from "./PropertyPage";

export function PropertiesRoute() {
  return (
    <AntdTheme>
      <PropertiesDashboard />
    </AntdTheme>
  );
}

export function PropertyRoute() {
  return (
    <AntdTheme>
      <PropertyPage />
    </AntdTheme>
  );
}
