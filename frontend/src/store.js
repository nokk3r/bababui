import { reactive } from "vue";
import { toast } from "vue-sonner";
import { api, loginOpen } from "./lib/api.js";
import { t } from "./lib/i18n.js";

const VIEWS = ["overview", "subscription", "history", "settings"];
const POLL_RUNNING_MS = 2000;
const POLL_IDLE_MS = 12000;

export const COLUMN_KEYS = [
  "protocol",
  "latency_ms",
  "download_bps",
  "upload_bps",
  "avg_latency_ms",
  "avg_download_bps",
  "avg_upload_bps",
  "spark",
  "action",
];

function loadColumns() {
  const columns = Object.fromEntries(COLUMN_KEYS.map((key) => [key, true]));
  try {
    const saved = JSON.parse(localStorage.getItem("bababui-columns") || "{}");
    for (const key of COLUMN_KEYS) {
      if (typeof saved[key] === "boolean") columns[key] = saved[key];
    }
  } catch {
    /* битая запись в браузере не должна ломать таблицу */
  }
  return columns;
}

export const state = reactive({
  nodes: [],
  series: new Map(),
  runs: [],
  remote: {},
  settings: null,
  view: "overview",
  sortKey: "download_bps",
  sortDir: "desc",
  query: "",
  protocol: "all",
  showInactive: false,
  subQuery: "",
  columns: loadColumns(),
  dialog: null,
  settingsPane: "general",
  lastDone: -1,
  tick: 0,
});

let nextPollAt = 0;
let polling = false;
let seenRun;

export { toast };

/* Общая обработка: на 401 уже открыта страница входа, остальное показываем тостом. */
export function reportError(error) {
  if (!error.unauthorized) toast(error.message);
}

export function setView(name) {
  const view = VIEWS.includes(name) ? name : "overview";
  state.view = view;
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
}

export function openSettings(pane) {
  state.settingsPane = pane;
  setView("settings");
}

function runKey(remote) {
  const run = remote.last_run;
  return run ? `${run.id}:${run.status}` : "";
}

export function pollSoon() {
  nextPollAt = 0;
}

export async function reloadAll() {
  const [remote, nodes, series, runs, settings] = await Promise.all([
    api("/api/state"),
    api("/api/nodes"),
    api("/api/series?hours=48"),
    api("/api/runs?limit=30"),
    api("/api/settings"),
  ]);
  const grouped = new Map();
  for (const row of series) {
    if (!grouped.has(row.node_id)) grouped.set(row.node_id, []);
    grouped.get(row.node_id).push(row);
  }
  seenRun = runKey(remote);
  state.remote = remote;
  state.nodes = nodes;
  state.runs = runs;
  state.settings = settings;
  state.series = grouped;
}

async function poll() {
  polling = true;
  try {
    const remote = await api("/api/state");
    const done = remote.running ? remote.running.done : -1;
    state.remote = remote;
    if (remote.running && done !== state.lastDone) {
      state.lastDone = done;
      state.nodes = await api("/api/nodes");
    }
    /* Короткая проверка может начаться и закончиться между двумя опросами. */
    if (!remote.running && runKey(remote) !== seenRun) {
      state.lastDone = -1;
      await reloadAll();
    }
  } catch {
    /* временный сбой опроса не должен забивать экран */
  } finally {
    polling = false;
    /* Запас в полтакта: иначе срок чуть опаздывает к тику и опрос сдвигается на секунду. */
    nextPollAt = Date.now() + (state.remote.running ? POLL_RUNNING_MS : POLL_IDLE_MS) - 500;
  }
}

function tick() {
  state.tick += 1;
  if (document.hidden || loginOpen.value || polling || Date.now() < nextPollAt) return;
  poll();
}

export async function startRun(body) {
  try {
    await api("/api/runs", { method: "POST", json: body });
    state.remote = await api("/api/state");
    pollSoon();
  } catch (error) {
    reportError(error);
  }
}

export async function stopRun() {
  try {
    await api("/api/runs/cancel", { method: "POST" });
    pollSoon();
  } catch (error) {
    reportError(error);
  }
}

export async function openNode(id) {
  const node = state.nodes.find((item) => item.id === id);
  if (!node) return;
  try {
    const history = await api(`/api/nodes/${encodeURIComponent(id)}/history?limit=500`);
    state.dialog = { node, history };
  } catch (error) {
    reportError(error);
  }
}

export async function boot() {
  setView((location.hash || "#overview").slice(1));
  window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollSoon();
  });
  try {
    const health = await fetch("/api/health").then((response) => response.json());
    if (health.auth && !sessionStorage.getItem("token")) {
      loginOpen.value = true;
    } else {
      await reloadAll();
    }
  } catch (error) {
    if (!error.unauthorized) {
      toast(error.message || t("error.noConnection"));
    }
  }
  setInterval(tick, 1000);
}
