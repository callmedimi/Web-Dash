/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        ink: "var(--ink)",
        "ink-2": "var(--ink-2)",
        line: "var(--line)",
        signal: "var(--signal)",
        ok: "var(--ok)",
        warn: "var(--warn)",
        fault: "var(--fault)",
        "info-muted": "var(--info-muted)",
      },
      borderRadius: {
        control: "3px",
        dialog: "6px",
      },
      fontFamily: {
        sans: [
          '"IBM Plex Sans"',
          '"Vazirmatn"',
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          "Roboto",
          "sans-serif",
        ],
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        xs: ["12px", { lineHeight: "16px" }],
        sm: ["13px", { lineHeight: "18px" }],
        base: ["14px", { lineHeight: "20px" }],
        md: ["16px", { lineHeight: "22px" }],
        lg: ["20px", { lineHeight: "26px" }],
        xl: ["24px", { lineHeight: "30px" }],
      },
      transitionDuration: {
        DEFAULT: "120ms",
      },
      transitionTimingFunction: {
        DEFAULT: "ease-out",
      },
    },
  },
  plugins: [],
};
