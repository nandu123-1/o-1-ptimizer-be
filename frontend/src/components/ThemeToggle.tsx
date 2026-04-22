"use client";

import { setTheme, useTheme } from "@/lib/useTheme";

export default function ThemeToggle() {
  const theme = useTheme();
  const toggle = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  const label =
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  const display = theme === "dark" ? "Light" : "Dark";
  const icon = theme === "dark" ? "☀" : "◐";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={label}
      title={label}
    >
      <span className="theme-toggle-icon" aria-hidden="true">
        {icon}
      </span>
      <span>{display}</span>
    </button>
  );
}
