/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/renderer/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        terminal: {
          bg: "rgba(15, 23, 42, 0.72)",
          card: "rgba(30, 41, 59, 0.55)",
          border: "rgba(71, 85, 105, 0.4)",
          text: "#e2e8f0",
          muted: "#94a3b8",
          accent: "#38bdf8",
        },
        valuation: {
          low: "#22c55e",
          normal: "#eab308",
          high: "#ef4444",
          lowBg: "rgba(34, 197, 94, 0.15)",
          normalBg: "rgba(234, 179, 8, 0.15)",
          highBg: "rgba(239, 68, 68, 0.15)",
        },
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        sans: [
          "Inter",
          "PingFang SC",
          "Microsoft YaHei",
          "sans-serif",
        ],
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};
