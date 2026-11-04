import { i18n, t } from "./i18n.js";
import { SPEED_UNITS, units } from "./units.js";

const PROTOCOL_LABEL = {
  vless: "VLESS",
  vmess: "VMess",
  trojan: "Trojan",
  shadowsocks: "Shadowsocks",
  hysteria2: "Hysteria2",
  wireguard: "WireGuard",
};

export function speedUnit() {
  return SPEED_UNITS[units.speed].label;
}

export function toSpeed(bytes) {
  if (bytes == null || Number.isNaN(Number(bytes))) return null;
  return Number(bytes) * SPEED_UNITS[units.speed].perByte;
}

export function roundSpeed(value) {
  if (value >= 100) return value.toFixed(0);
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function formatSpeed(bytes) {
  const value = toSpeed(bytes);
  return value == null ? "—" : roundSpeed(value);
}

/* Ошибки Xray и Hysteria приходят как строки лога: цветовые коды терминала и метки времени в интерфейсе только мешают. */
const TERMINAL_COLOR = /\x1b?\[[0-9;]*m/g;
const LOG_TIMESTAMP = /\b\d{4}-\d{2}-\d{2}T[\d:.]+Z\s*/g;

export function cleanError(text) {
  return String(text ?? "").replace(TERMINAL_COLOR, "").replace(LOG_TIMESTAMP, "").replace(/\s+/g, " ").trim();
}

export function formatMs(value) {
  if (value == null) return "—";
  return `${Math.round(Number(value))} ${t("unit.ms")}`;
}

export function formatBytes(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1000 ** 2) return `${Math.round(size / 1000)} ${t("unit.kb")}`;
  if (size < 1000 ** 3) return `${(size / 1000 ** 2).toFixed(size >= 10 * 1000 ** 2 ? 0 : 1)} ${t("unit.mb")}`;
  return `${(size / 1000 ** 3).toFixed(2)} ${t("unit.gb")}`;
}

export function formatTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(i18n.lang, {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

function countdown(iso) {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "";
  const minutes = Math.floor(diff / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return t("next.hoursMinutes", { hours, minutes: minutes % 60 });
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/* «Через сколько» для срока: пусто, если срок уже наступил. Для строк источников и бокового меню. */
export function timeUntil(iso) {
  return iso ? countdown(iso) : "";
}

/* Как часто проверяется источник: «раз в час», «каждые 6 часов», «каждые 30 минут» или cron. */
export function scheduleSummary(source) {
  if (!source.schedule_enabled) return t("source.scheduleOff");
  if (source.schedule_mode === "cron") return t("source.cronSummary", { expr: source.cron_expression });
  const minutes = Number(source.interval_minutes) || 0;
  if (minutes === 1) return t("source.everyMinute");
  if (minutes === 60) return t("source.hourly");
  if (minutes === 1440) return t("source.daily");
  if (minutes % 60 === 0) return t("source.everyHours", { count: minutes / 60 });
  return t("source.everyMinutes", { count: minutes });
}

export function nextLabel(remote) {
  if (!remote || remote.running) return t("next.running");
  if (!remote.next_run_at) return t("next.off");
  const value = countdown(remote.next_run_at);
  return value ? t("next.in", { time: value }) : t("next.now");
}

export function mean(values) {
  const nums = values.filter((value) => value != null && Number(value) > 0).map(Number);
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

export function protocolName(protocol) {
  return PROTOCOL_LABEL[protocol] || protocol;
}

export function statusLabel(status) {
  return ["running", "done", "cancelled", "failed"].includes(status) ? t(`runStatus.${status}`) : status;
}

export function resultDot(ok, alive) {
  if (ok) return "ok";
  return alive ? "warn" : "bad";
}

export function nodeDot(node) {
  if (!node.supported) return "unsupported";
  if (node.last_ok == null) return "idle";
  return resultDot(node.last_ok, node.last_alive);
}
