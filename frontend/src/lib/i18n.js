import { reactive } from "vue";

export const LANGUAGES = { en: "English", ru: "Русский" };
const SOURCE_LANG = "en";
const LANG_STORAGE_KEY = "bababui-lang";
const SERVER_MARKER = /\[\[([a-z0-9_]+)(?:\|(\{.*?\}))?\]\]/g;

export const i18n = reactive({ lang: SOURCE_LANG, messages: {}, source: {} });

function savedLang() {
  try {
    const lang = localStorage.getItem(LANG_STORAGE_KEY);
    return lang in LANGUAGES ? lang : SOURCE_LANG;
  } catch {
    return SOURCE_LANG;
  }
}

async function fetchLocale(lang) {
  const response = await fetch(`${import.meta.env.BASE_URL}locales/${lang}.json`);
  if (!response.ok) throw new Error(`locale ${lang}: ${response.status}`);
  return response.json();
}

function lookup(key, params) {
  const keys = [key];
  if (typeof params.count === "number") {
    const form = new Intl.PluralRules(i18n.lang).select(params.count);
    keys.unshift(`${key}_${form}`, `${key}_other`);
  }
  for (const table of [i18n.messages, i18n.source]) {
    for (const item of keys) {
      if (item in table) return table[item];
    }
  }
  return key;
}

export function t(key, params = {}) {
  return lookup(key, params).replace(/\{(\w+)\}/g, (match, name) => (name in params ? params[name] : match));
}

/* Текст с бэкенда: маркеры становятся переводом, вывод Xray и speedtest остаётся как есть. */
export function tMsg(text) {
  return String(text ?? "").replace(SERVER_MARKER, (match, key, json) => {
    const fullKey = `server.${key}`;
    if (!(fullKey in i18n.source)) return match;
    try {
      return t(fullKey, json ? JSON.parse(json) : {});
    } catch {
      return match;
    }
  });
}

export async function setLang(lang) {
  i18n.messages = lang === SOURCE_LANG ? i18n.source : await fetchLocale(lang);
  i18n.lang = lang;
  try {
    localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    /* выбор языка просто не запомнится */
  }
  document.documentElement.lang = lang;
}

export async function initI18n() {
  i18n.source = await fetchLocale(SOURCE_LANG);
  i18n.messages = i18n.source;
  const lang = savedLang();
  if (lang !== SOURCE_LANG) {
    try {
      i18n.messages = await fetchLocale(lang);
      i18n.lang = lang;
    } catch {
      i18n.messages = i18n.source;
    }
  }
  document.documentElement.lang = i18n.lang;
}
