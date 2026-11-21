import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        sidebar: "#F7F7F7",
        surface: "#FFFFFF",
        subtle: "#F9F9F9",
        hover: "#F3F3F3",
        selected: "#EEEEEE",
        primaryText: "#111827",
        secondaryText: "#4B5563",
        mutedText: "#6B7280",
        neutralBorder: "#E5E5E5",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "'Liberation Mono'",
          "'Courier New'",
          "monospace",
        ],
      },
      fontSize: {
        // AI Interview Studio Standard Typography Tokens
        "page-title": ["30px", { lineHeight: "38px", letterSpacing: "-0.025em", fontWeight: "700" }],
        "page-subtitle": ["14px", { lineHeight: "22px", letterSpacing: "normal", fontWeight: "400" }],
        "section-heading": ["20px", { lineHeight: "28px", letterSpacing: "-0.01em", fontWeight: "600" }],
        "card-heading": ["16px", { lineHeight: "24px", letterSpacing: "normal", fontWeight: "600" }],
        "body-default": ["14px", { lineHeight: "22px", letterSpacing: "normal", fontWeight: "400" }],
        "body-secondary": ["13px", { lineHeight: "20px", letterSpacing: "normal", fontWeight: "400" }],
        "sidebar-nav": ["14px", { lineHeight: "20px", letterSpacing: "normal", fontWeight: "500" }],
        "sidebar-label": ["12px", { lineHeight: "16px", letterSpacing: "normal", fontWeight: "500" }],
        "btn": ["14px", { lineHeight: "20px", letterSpacing: "normal", fontWeight: "600" }],
        "kpi-val": ["30px", { lineHeight: "36px", letterSpacing: "-0.02em", fontWeight: "700" }],
        "kpi-lbl": ["13px", { lineHeight: "18px", letterSpacing: "normal", fontWeight: "500" }],
        "meta": ["12px", { lineHeight: "16px", letterSpacing: "normal", fontWeight: "500" }],
        "meta-sm": ["11px", { lineHeight: "16px", letterSpacing: "normal", fontWeight: "500" }],
        "tab-item": ["14px", { lineHeight: "20px", letterSpacing: "normal", fontWeight: "500" }],
        "table-txt": ["13px", { lineHeight: "20px", letterSpacing: "normal", fontWeight: "400" }],
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
        subtle: "0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.02)",
      },
    },
  },
  plugins: [],
};
export default config;
