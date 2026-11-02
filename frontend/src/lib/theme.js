import { reactive } from "vue";

export const THEMES = ["system", "light", "dark"];
const STORAGE_KEY = "bababui-theme";
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");

export const theme = reactive({ mode: "system", dark: false });

function savedMode() {
  try {
    const mode = localStorage.getItem(STORAGE_KEY);
    return THEMES.includes(mode) ? mode : "system";
  } catch {
    return "system";
  }
}

function apply() {
  theme.dark = theme.mode === "dark" || (theme.mode === "system" && systemDark.matches);
  document.documentElement.classList.toggle("dark", theme.dark);
}

export function setTheme(mode) {
  theme.mode = mode;
  apply();
  try {
    localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    /* выбор темы просто не запомнится */
  }
}

export function initTheme() {
  theme.mode = savedMode();
  apply();
  systemDark.addEventListener("change", apply);
}
