// Тема. MAX Bridge тему не передаёт (в документации её нет), поэтому по умолчанию
// следуем системной — WebView клиента наследует её. В «Профиле» можно
// выбрать тему вручную; «Как в MAX» = системная.
import { useSyncExternalStore } from "react";
import { config } from "./config";
import { load, save } from "./storage";

export type ThemePref = "system" | "light" | "dark";

const KEY = "theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();
let pref: ThemePref = (config.forcedTheme ?? load<ThemePref>(KEY) ?? "system") as ThemePref;

function apply() {
  const dark = pref === "dark" || (pref === "system" && media.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function initTheme() {
  apply();
  media.addEventListener("change", apply);
}

export function setThemePref(next: ThemePref) {
  pref = next;
  save(KEY, next);
  apply();
  listeners.forEach((l) => l());
}

export function useThemePref(): ThemePref {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => pref,
  );
}

export const THEME_LABELS: Record<ThemePref, string> = {
  system: "Как в MAX",
  light: "Светлая",
  dark: "Тёмная",
};
