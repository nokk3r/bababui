import { i18n, t } from "./i18n.js";

const PROTOCOL_LABEL = {
  vless: "VLESS",
  vmess: "VMess",
  trojan: "Trojan",
  shadowsocks: "Shadowsocks",
  hysteria2: "Hysteria2",
  wireguard: "WireGuard",
};

export function mbps(bps) {
  if (bps == null || Number.isNaN(Number(bps))) return "—";
  const value = (Number(bps) * 8) / 1e6;
  if (value >= 100) return value.toFixed(0);
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(2);
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

export function nextLabel(remote) {
  if (!remote || remote.running) return t("next.running");
  if (!remote.scheduler_enabled || !remote.next_run_at) return t("next.off");
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
  if (!node.supported) return "bad";
  if (node.last_ok == null) return "idle";
  return resultDot(node.last_ok, node.last_alive);
}
