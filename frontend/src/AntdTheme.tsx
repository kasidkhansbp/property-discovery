// Ant Design theme for the screens built with it (the Properties tab, for now).
//
// It mirrors TPMguild's design system, the same tokens as the :root block in
// styles.css: warm paper, near-black ink, one electric-blue accent, sharp 4px
// corners, Arial, light only. Keep the two in step when a colour changes.
//
// Brand colour rule: the blue accent means brand and action only (the Search
// button, primary buttons, the logo tile, focus and "you are here" markers).
// Links and everything decorative are ink, so the blue stands out.
//
// No antd reset stylesheet is loaded, so plain-CSS tabs are unaffected. Kept
// out of App.tsx so antd loads only with the screens that use it (they are
// lazy-loaded routes).

import { ConfigProvider, type ThemeConfig } from "antd";
import type { ReactNode } from "react";

// TPMguild tokens (names in comments).
const PAPER = "#fafaf7"; // paper
const PAPER_2 = "#f3f2ec"; // paper-2
const PAPER_3 = "#eceae2"; // paper-3
const INK = "#131218"; // ink
const INK_2 = "#2a2830"; // ink-2
const INK_3 = "#55525e"; // ink-3
const INK_4 = "#8a8690"; // ink-4
const LINE = "#e8e6df"; // line
const LINE_2 = "#d6d3ca"; // line-2
const ACCENT = "#2e3be6"; // accent
const ACCENT_2 = "#2431bf"; // accent-2
const ACCENT_WASH = "#2e3be614"; // accent-wash

export const BRAND = {
  accent: ACCENT,
  accentWash: ACCENT_WASH,
  ink2: INK_2,
  paper3: PAPER_3,
  verified: "#2f7a4f",
  verifiedWash: "#2f7a4f1a",
  warn: "#b8621f",
  danger: "#a8322c",
  ink: INK,
  paper: PAPER,
} as const;

const TPM_THEME: ThemeConfig = {
  token: {
    colorPrimary: ACCENT,
    colorPrimaryHover: ACCENT_2,
    colorPrimaryActive: ACCENT_2,
    colorInfo: ACCENT,
    // Links are ink, not blue: blue is reserved for brand and action.
    colorLink: INK,
    colorLinkHover: INK_2,
    colorLinkActive: INK,
    colorSuccess: BRAND.verified,
    colorWarning: BRAND.warn,
    colorError: BRAND.danger,

    colorText: INK,
    colorTextSecondary: INK_3,
    colorTextTertiary: INK_4,
    colorTextQuaternary: INK_4,
    colorTextHeading: INK,

    colorBgLayout: PAPER,
    colorBgContainer: PAPER,
    colorBgElevated: PAPER,
    colorFillAlter: PAPER_2,
    colorFillSecondary: PAPER_2,
    colorFillTertiary: PAPER_2,
    colorBorder: LINE_2,
    colorBorderSecondary: LINE,
    colorSplit: LINE,

    borderRadius: 4,
    borderRadiusSM: 2,
    borderRadiusLG: 4,
    borderRadiusXS: 2,

    fontFamily: "Arial, Helvetica, sans-serif",
    fontFamilyCode: '"Courier New", Courier, ui-monospace, SFMono-Regular, monospace',

    boxShadow: "0 8px 32px #1312181f, 0 2px 6px #1312180d",
    boxShadowSecondary: "0 8px 32px #1312181f, 0 2px 6px #1312180d",
    boxShadowTertiary: "0 1px 2px #1312180a, 0 4px 12px #1312180f",

    // Focus ring: the pale brand-blue wash.
    controlOutline: ACCENT_WASH,
  },
  components: {
    Button: {
      primaryShadow: "none",
      defaultShadow: "none",
      dangerShadow: "none",
      fontWeight: 500,
      defaultBorderColor: LINE_2,
      defaultColor: INK,
      defaultHoverBg: PAPER_2,
      defaultHoverBorderColor: INK_3,
      defaultHoverColor: INK,
      textHoverBg: LINE,
    },
    Table: {
      headerBg: PAPER_2,
      headerColor: INK_3,
      headerSplitColor: "transparent",
      rowHoverBg: PAPER_2,
      rowExpandedBg: PAPER_2,
      borderColor: LINE,
    },
    Card: {
      colorBorderSecondary: LINE,
    },
    Tag: {
      defaultBg: PAPER_2,
      defaultColor: INK_2,
    },
    Input: {
      activeBorderColor: ACCENT,
      hoverBorderColor: INK_3,
      activeShadow: `0 0 0 3px ${ACCENT_WASH}`,
    },
    Collapse: {
      headerBg: PAPER,
    },
    Timeline: {
      tailColor: LINE,
      dotBg: PAPER,
    },
    Statistic: {
      titleFontSize: 12,
    },
  },
};

export function AntdTheme({ children }: { children: ReactNode }) {
  return <ConfigProvider theme={TPM_THEME}>{children}</ConfigProvider>;
}
