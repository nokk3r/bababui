import { reactive } from "vue";
import { readStored, writeStored } from "./storage.js";

export const THEMES = ["system", "light", "dark"];
/* Тот же ключ читает скрипт в index.html, чтобы поставить тему до первой отрисовки. */
const STORAGE_KEY = "bababui-theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

export const theme = reactive({ mode: "system", dark: false });

function apply() {
  theme.dark = theme.mode === "dark" || (theme.mode === "system" && systemDark.matches);
  document.documentElement.classList.toggle("dark", theme.dark);
}

export function setTheme(mode) {
  theme.mode = mode;
  apply();
  writeStored(STORAGE_KEY, mode);
}

export function initTheme() {
  const saved = readStored(STORAGE_KEY);
  theme.mode = THEMES.includes(saved) ? saved : "system";
  apply();
  systemDark.addEventListener("change", apply);
}
