import { reactive } from "vue";
import { toast } from "vue-sonner";
import { api, loginOpen } from "./lib/api.js";
import { t } from "./lib/i18n.js";
import { readStored, writeStored } from "./lib/storage.js";

const VIEWS = ["overview", "subscription", "history", "settings"];
const POLL_RUNNING_MS = 2000;
const POLL_IDLE_MS = 12000;
/* Столько последних проверок показывает полоска узла: длиннее она не читается и растягивает таблицу. */
export const RECENT_CHECKS = 24;
const COLUMNS_KEY = "bababui-columns";
const SORT_KEY = "bababui-sort";
const DEFAULT_SORT = { key: "download_bps", dir: "desc" };

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
    const saved = JSON.parse(readStored(COLUMNS_KEY) || "{}");
    for (const key of COLUMN_KEYS) {
      if (typeof saved[key] === "boolean") columns[key] = saved[key];
    }
  } catch {
    /* битая запись в браузере не должна ломать таблицу */
  }
  return columns;
}

/* По этим полям таблицу можно сортировать: имя узла и первые семь колонок. */
export const SORT_KEYS = ["name", ...COLUMN_KEYS.slice(0, 7)];

/* Выбор сортировки переживает перезагрузку. Пустой ключ значит «без сортировки». */
function loadSort() {
  try {
    const saved = JSON.parse(readStored(SORT_KEY) || "null");
    if (saved && saved.key === null && saved.dir === null) return saved;
    if (saved && SORT_KEYS.includes(saved.key) && ["asc", "desc"].includes(saved.dir)) return saved;
  } catch {
    /* битая запись в браузере не должна ломать таблицу */
  }
  return DEFAULT_SORT;
}

export function setSort(key, dir) {
  state.sortKey = key;
  state.sortDir = dir;
  writeStored(SORT_KEY, JSON.stringify({ key, dir }));
}

export function setColumn(key, visible) {
  state.columns[key] = visible;
  writeStored(COLUMNS_KEY, JSON.stringify(state.columns));
}

const initialSort = loadSort();

export const state = reactive({
  nodes: [],
  series: new Map(),
  recent: new Map(),
  runs: [],
  remote: {},
  settings: null,
  view: "overview",
  sortKey: initialSort.key,
  sortDir: initialSort.dir,
  query: "",
  protocol: "all",
  status: "all",
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

/* Переход по меню пишется в историю браузера, чтобы работала кнопка «Назад».
   При загрузке и при самой кнопке «Назад» адрес только выравнивается, без новой записи. */
export function setView(name, { replace = false } = {}) {
  const view = VIEWS.includes(name) ? name : "overview";
  const changed = state.view !== view;
  state.view = view;
  if (location.hash === `#${view}`) return;
  if (replace) {
    history.replaceState(null, "", `#${view}`);
  } else {
    history.pushState(null, "", `#${view}`);
    if (changed) window.scrollTo(0, 0);
  }
}

/* Этап узла, который сейчас проверяется: null, если узел не в работе. */
export function checkingStage(nodeId) {
  const run = state.remote.running;
  const index = (run?.current_ids || []).indexOf(nodeId);
  if (index < 0) return null;
  return run.current_stages?.[index] || "";
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

function byNode(rows) {
  const grouped = new Map();
  for (const row of rows) {
    if (!grouped.has(row.node_id)) grouped.set(row.node_id, []);
    grouped.get(row.node_id).push(row);
  }
  return grouped;
}

export async function reloadAll() {
  const [remote, nodes, series, recent, runs, settings] = await Promise.all([
    api("/api/state"),
    api("/api/nodes"),
    api("/api/series?hours=48"),
    api(`/api/recent?per_node=${RECENT_CHECKS}`),
    api("/api/runs?limit=30"),
    api("/api/settings"),
  ]);
  seenRun = runKey(remote);
  state.remote = remote;
  state.nodes = nodes;
  state.runs = runs;
  state.settings = settings;
  state.series = byNode(series);
  state.recent = byNode(recent);
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
  setView((location.hash || "#overview").slice(1), { replace: true });
  window.addEventListener("hashchange", () => setView(location.hash.slice(1), { replace: true }));
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
