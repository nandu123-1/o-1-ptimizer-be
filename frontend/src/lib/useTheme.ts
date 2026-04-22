"use client";

import { useSyncExternalStore } from "react";

export type ThemeName = "light" | "dark";

const STORAGE_KEY = "dsa-tutor-theme";

function readTheme(): ThemeName {
  if (typeof document === "undefined") {
    return "light";
  }
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr === "dark" || attr === "light") {
    return attr;
  }
  if (typeof window !== "undefined" && window.matchMedia) {
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }
  return "light";
}

function subscribe(notify: () => void): () => void {
  if (typeof document === "undefined") {
    return () => {};
  }
  const observer = new MutationObserver(notify);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

function getServerSnapshot(): ThemeName {
  return "light";
}

export function useTheme(): ThemeName {
  return useSyncExternalStore(subscribe, readTheme, getServerSnapshot);
}

export function setTheme(theme: ThemeName): void {
  if (typeof document === "undefined") {
    return;
  }
  document.documentElement.setAttribute("data-theme", theme);
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // localStorage may be disabled; silently ignore.
  }
}
