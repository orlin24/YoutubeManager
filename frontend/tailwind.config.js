/** @type {import('tailwindcss').Config} */
// Material 3 (dark) design tokens: zinc = M3 surface/outline scales,
// brand = M3 primary tonal palette (seed #6750A4).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#F6EDFF",
          100: "#EADDFF", // onPrimaryContainer
          200: "#E0CFFF",
          300: "#D0BCFF", // primary (light)
          400: "#D0BCFF",
          500: "#C5A9FF",
          600: "#D0BCFF", // primary (filled buttons)
          700: "#4F378B", // primaryContainer
          800: "#4F378B",
          900: "#381E72", // onPrimary (dark)
          950: "#381E72",
        },
        zinc: {
          50: "#F7F2FA",
          100: "#E6E0E9", // onSurface
          200: "#E6E0E9",
          300: "#E6E0E9",
          400: "#CAC4D0", // onSurfaceVariant
          500: "#CAC4D0",
          600: "#49454F", // outlineVariant
          700: "#49454F", // outline
          800: "#2B2930", // surfaceContainerHigh
          900: "#211F26", // surfaceContainer
          950: "#141218", // surface
        },
        surface: {
          DEFAULT: "#141218",
          container: "#211F26",
          high: "#2B2930",
          highest: "#36343B",
        },
        outline: {
          DEFAULT: "#938F99",
          variant: "#49454F",
        },
        onsurface: {
          DEFAULT: "#E6E0E9",
          variant: "#CAC4D0",
        },
        m3error: {
          DEFAULT: "#F2B8B5",
          on: "#601410",
          container: "#8C1D18",
        },
      },
      fontFamily: {
        sans: [
          "Roboto",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
      },
      boxShadow: {
        "m3-1": "0 1px 2px rgba(0,0,0,0.30), 0 1px 3px 1px rgba(0,0,0,0.15)",
        "m3-2": "0 1px 2px rgba(0,0,0,0.30), 0 2px 6px 2px rgba(0,0,0,0.15)",
        "m3-3": "0 4px 8px 3px rgba(0,0,0,0.15), 0 1px 3px rgba(0,0,0,0.30)",
      },
    },
  },
  plugins: [],
};
