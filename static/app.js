const PROTOCOL_LABEL = {
  vless: "VLESS",
  vmess: "VMess",
  trojan: "Trojan",
  shadowsocks: "Shadowsocks",
  hysteria2: "Hysteria2",
  wireguard: "WireGuard",
};

const state = {
  nodes: [],
  series: new Map(),
  runs: [],
  remote: {},
  settings: null,
  formDirty: false,
  sortKey: "download_bps",
  sortDir: "desc",
  query: "",
  protocol: "all",
  showInactive: false,
  subQuery: "",
  columns: null,
  lastDone: -1,
  tick: 0,
};

const COLUMN_KEYS = [
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

state.columns = loadColumns();

function applyColumns() {
  const table = $("nodes");
  if (!table) return;
  for (const key of COLUMN_KEYS) table.classList.toggle(`hide-${key}`, !state.columns[key]);
  document.querySelectorAll("#column-menu input").forEach((input) => {
    input.checked = state.columns[input.value] !== false;
  });
}

const $ = (id) => document.getElementById(id);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function authHeaders() {
  const headers = {};
  const token = sessionStorage.getItem("token");
  if (token) headers.Authorization = `Bearer ${encodeURIComponent(token)}`;
  return headers;
}

async function api(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  const request = { ...options, headers };
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    request.body = JSON.stringify(options.json);
  }
  const response = await fetch(path, request);
  if (response.status === 401) {
    showLogin();
    const error = new Error("unauthorized");
    error.unauthorized = true;
    throw error;
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch (_) {
      /* тело не JSON */
    }
    if (detail && typeof detail !== "string") detail = JSON.stringify(detail);
    throw new Error(detail || "запрос не выполнен");
  }
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return response.json();
  return response.text();
}

function dismissToast(item) {
  if (!item?.isConnected || item.dataset.leaving) return;
  item.dataset.leaving = "1";
  item.classList.add("is-out");
  const remove = () => item.remove();
  item.addEventListener("animationend", remove, { once: true });
  setTimeout(remove, 280);
}

function toast(message) {
  const stack = $("toast-stack");
  const item = document.createElement("div");
  item.className = "toast";
  item.textContent = message;
  stack.prepend(item);
  [...stack.children].slice(3).forEach(dismissToast);
  setTimeout(() => dismissToast(item), 4600);
}

function showLogin() {
  $("login").hidden = false;
  $("shell").hidden = true;
}

function showApp() {
  $("login").hidden = true;
  $("shell").hidden = false;
}

function setMbps(id, bps) {
  const el = $(id);
  const value = mbps(bps);
  el.replaceChildren(document.createTextNode(value));
  if (value === "—") return;
  const unit = document.createElement("small");
  unit.textContent = "Мбит/с";
  el.append(unit);
}

function mbps(bps) {
  if (bps == null || Number.isNaN(Number(bps))) return "—";
  const value = (Number(bps) * 8) / 1e6;
  if (value >= 100) return value.toFixed(0);
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function formatMs(value) {
  if (value == null) return "—";
  return `${Math.round(Number(value))} мс`;
}

function formatBytes(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1000 ** 2) return `${Math.round(size / 1000)} КБ`;
  if (size < 1000 ** 3) return `${(size / 1000 ** 2).toFixed(size >= 10 * 1000 ** 2 ? 0 : 1)} МБ`;
  return `${(size / 1000 ** 3).toFixed(2)} ГБ`;
}

function formatTime(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function nextLabel(remote) {
  if (!remote || remote.running) return "идёт";
  if (!remote.scheduler_enabled) return "выкл";
  const value = countdown(remote.next_run_at);
  if (value === "сейчас" || value === "выключена") return value === "выключена" ? "выкл" : "сейчас";
  return `через ${value}`;
}

function countdown(iso) {
  if (!iso) return "выключена";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "сейчас";
  const minutes = Math.floor(diff / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours} ч ${minutes % 60} мин`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function mean(values) {
  const nums = values.filter((value) => value != null && Number(value) > 0).map(Number);
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

function setMs(id, value) {
  const el = $(id);
  if (value == null || Number.isNaN(Number(value))) {
    el.textContent = "—";
    return;
  }
  el.replaceChildren(document.createTextNode(String(Math.round(value))));
  const unit = document.createElement("small");
  unit.textContent = "мс";
  el.append(unit);
}

function protocolName(protocol) {
  return PROTOCOL_LABEL[protocol] || protocol;
}

function statusLabel(status) {
  return { running: "идёт", done: "завершена", cancelled: "остановлена", failed: "ошибка" }[status] || status;
}

function spark(values) {
  const nums = values.filter((value) => value != null);
  if (!nums.length) return `<span class="muted">—</span>`;
  const width = 92;
  const height = 28;
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const step = values.length > 1 ? (width - 4) / (values.length - 1) : 0;
  let path = "";
  values.forEach((value, index) => {
    if (value == null) return;
    const x = 2 + index * step;
    const y = height - 3 - ((value - min) / span) * (height - 6);
    const command = path && values[index - 1] != null ? "L" : "M";
    path += `${command}${x.toFixed(1)} ${y.toFixed(1)} `;
  });
  return `<svg class="spark" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" aria-hidden="true"><path d="${path}" /></svg>`;
}

function visibleNodes() {
  const query = state.query.trim().toLowerCase();
  return state.nodes.filter((node) => {
    if (!node.active) return false;
    if (state.protocol !== "all" && node.protocol !== state.protocol) return false;
    if (!query) return true;
    return `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query);
  });
}

function sortNodes(nodes) {
  if (!state.sortKey || !state.sortDir) return nodes.slice();
  const direction = state.sortDir === "asc" ? 1 : -1;
  const key = state.sortKey;
  return nodes.slice().sort((a, b) => {
    if (key === "name" || key === "protocol") {
      const left = key === "name" ? a.name : protocolName(a.protocol);
      const right = key === "name" ? b.name : protocolName(b.protocol);
      const compared = left.localeCompare(right, "ru");
      return compared === 0 ? 0 : compared * direction;
    }
    if (key === "enabled") {
      const compared = Number(Boolean(a.enabled)) - Number(Boolean(b.enabled));
      return compared === 0 ? a.name.localeCompare(b.name, "ru") : compared * direction;
    }
    const left = a[key];
    const right = b[key];
    const leftEmpty = left == null || left === "";
    const rightEmpty = right == null || right === "";
    if (leftEmpty && rightEmpty) return a.name.localeCompare(b.name, "ru");
    if (leftEmpty) return 1;
    if (rightEmpty) return -1;
    const compared = Number(left) - Number(right);
    return compared === 0 ? a.name.localeCompare(b.name, "ru") : compared * direction;
  });
}

function renderOverview() {
  const active = state.nodes.filter((node) => node.active);
  const enabled = active.filter((node) => node.supported && node.enabled);
  $("stat-nodes").textContent = String(active.length);
  const samples = enabled.filter((node) => node.last_ok);
  setMs("stat-latency", mean(samples.map((node) => node.latency_ms)));
  setMbps("stat-down-avg", mean(samples.map((node) => node.download_bps)));
  setMbps("stat-up-avg", mean(samples.map((node) => node.upload_bps)));
  renderStatus();
  renderFilters();
  renderTable();
  renderSubscription();
}

function syncGroups() {
  document.querySelectorAll(".group[data-gate]").forEach((group) => {
    const gate = document.getElementById(group.dataset.gate);
    const enabled = Boolean(gate?.checked);
    group.classList.toggle("is-off", !enabled);
    group.querySelectorAll("input").forEach((input) => {
      if (input !== gate) input.disabled = !enabled;
    });
  });
}

function renderStatus() {
  const remote = state.remote || {};
  const running = remote.running;
  $("run-button").hidden = Boolean(running);
  $("stop-button").hidden = !running;
  $("refresh-button").disabled = Boolean(running);
  if (running) {
    $("progress").hidden = false;
    const total = running.total || 0;
    const done = running.done || 0;
    const width = total ? Math.min(100, Math.round((done / total) * 100)) : (running.phase === "проверка" ? 8 : 15);
    $("progress-bar").style.width = `${width}%`;
    const current = (running.current || []).join(", ");
    const phase = running.phase || "проверка";
    $("progress-label").textContent = current ? `${phase}: ${current}` : phase;
    $("progress-count").textContent = total ? `${done} / ${total}` : "";
    $("stat-next").textContent = "идёт";
  } else {
    $("progress").hidden = true;
    $("stat-next").textContent = nextLabel(remote);
  }
  const messages = [];
  if (remote.last_refresh_error) messages.push(remote.last_refresh_error);
  const versions = remote.versions || {};
  if (versions.xray && versions.xray.ok === false) messages.push(`Xray: ${versions.xray.text}`);
  if (versions.hysteria && versions.hysteria.ok === false) messages.push(`Hysteria2: ${versions.hysteria.text}`);
  if (versions.speedtest && versions.speedtest.ok === false) messages.push(`speedtest: ${versions.speedtest.text}`);
  $("banner").hidden = messages.length === 0;
  $("banner").textContent = messages.join(" ");
  const versionBits = [
    `bababui ${versions.app || "0.2.0"}`,
    versions.xray?.text,
    versions.hysteria?.text,
    versions.speedtest?.text,
  ].filter(Boolean);
  $("versions").textContent = versionBits.join("\n");
  const quota = remote.userinfo;
  if (quota && quota.total > 0) {
    const used = (quota.upload || 0) + (quota.download || 0);
    $("quota").textContent = `Трафик подписки: ${formatBytes(used)} из ${formatBytes(quota.total)}`;
  } else if (quota && quota.expire > 0) {
    $("quota").textContent = `Подписка до ${formatTime(new Date(quota.expire * 1000).toISOString())}`;
  } else {
    $("quota").textContent = "";
  }
  $("refreshed").textContent = remote.last_refresh_at ? `Список узлов: ${formatTime(remote.last_refresh_at)}` : "";
}

function renderFilters() {
  const select = $("protocol-filter");
  const protocols = [...new Set(state.nodes.map((node) => node.protocol))].sort();
  const signature = protocols.join("|");
  if (select.dataset.signature === signature) return;
  select.dataset.signature = signature;
  const current = state.protocol;
  const options = [`<option value="all">Все протоколы</option>`].concat(
    protocols.map((protocol) => `<option value="${esc(protocol)}">${esc(protocolName(protocol))}</option>`),
  );
  select.innerHTML = options.join("");
  select.value = protocols.includes(current) || current === "all" ? current : "all";
  state.protocol = select.value;
}

function withAverages(nodes) {
  return nodes.map((node) => {
    const history = state.series.get(node.id) || [];
    return {
      ...node,
      avg_latency_ms: mean(history.map((row) => (row.ok ? row.latency_ms : null))),
      avg_download_bps: mean(history.map((row) => (row.ok ? row.download_bps : null))),
      avg_upload_bps: mean(history.map((row) => (row.ok ? row.upload_bps : null))),
    };
  });
}

function resultDot(ok, alive) {
  if (ok) return "ok";
  return alive ? "warn" : "bad";
}

function nodeDot(node) {
  if (!node.supported) return "bad";
  if (node.last_ok == null) return "idle";
  return resultDot(node.last_ok, node.last_alive);
}

function renderTable() {
  const tbody = document.querySelector("#nodes tbody");
  applyColumns();
  const rows = sortNodes(withAverages(visibleNodes()));
  document.querySelectorAll("#nodes th[data-sort]").forEach((th) => {
    const active = th.dataset.sort === state.sortKey && Boolean(state.sortDir);
    th.classList.toggle("sorted", active);
    if (active) {
      th.dataset.dir = state.sortDir;
      th.setAttribute("aria-sort", state.sortDir === "asc" ? "ascending" : "descending");
    } else {
      delete th.dataset.dir;
      th.setAttribute("aria-sort", "none");
    }
  });
  if (!rows.length) {
    const waiting = !state.remote.last_refresh_at && !state.remote.last_refresh_error;
    const text = waiting ? "Загружаем подписку…" : "Нет узлов по текущему фильтру.";
    tbody.innerHTML = `<tr><td colspan="10" class="empty">${esc(text)}</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((node) => {
    const history = state.series.get(node.id) || [];
    const series = history.slice(-24).map((row) => row.download_bps);
    const dot = nodeDot(node);
    const tested = node.last_tested_at ? formatTime(node.last_tested_at) : "";
    return `<tr data-id="${esc(node.id)}" class="${node.enabled ? "" : "is-off"} ${node.active ? "" : "is-gone"}">
      <td data-col="name">
        <div class="name">
          <b><i class="dot ${dot}"></i>${esc(node.name)}</b>
          <span class="sub">${esc(tested)}</span>
        </div>
      </td>
      <td data-col="protocol"><span class="proto proto-${esc(node.protocol)}">${esc(protocolName(node.protocol))}</span></td>
      <td data-col="latency_ms" class="metric">${esc(formatMs(node.latency_ms))}</td>
      <td data-col="download_bps" class="metric">${esc(mbps(node.download_bps))}${node.download_bps != null ? "<small>Мбит/с</small>" : ""}</td>
      <td data-col="upload_bps" class="metric">${esc(mbps(node.upload_bps))}${node.upload_bps != null ? "<small>Мбит/с</small>" : ""}</td>
      <td data-col="avg_latency_ms" class="metric">${node.avg_latency_ms == null ? "—" : esc(formatMs(node.avg_latency_ms))}</td>
      <td data-col="avg_download_bps" class="metric">${esc(mbps(node.avg_download_bps))}${node.avg_download_bps != null ? "<small>Мбит/с</small>" : ""}</td>
      <td data-col="avg_upload_bps" class="metric">${esc(mbps(node.avg_upload_bps))}${node.avg_upload_bps != null ? "<small>Мбит/с</small>" : ""}</td>
      <td data-col="spark">${spark(series)}</td>
      <td data-col="action"><button type="button" class="ghost row-button" data-test="${esc(node.id)}" ${node.supported ? "" : "disabled"}>Проверить</button></td>
    </tr>`;
  }).join("");
}

function subscriptionNodes() {
  const query = state.subQuery.trim().toLowerCase();
  return state.nodes.filter((node) => {
    if (!state.showInactive && !node.active) return false;
    if (!query) return true;
    return `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query);
  }).sort((a, b) => a.name.localeCompare(b.name, "ru"));
}

function renderSubscription() {
  const tbody = document.querySelector("#subscription-nodes tbody");
  const rows = subscriptionNodes();
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="3" class="empty">Нет узлов по текущему фильтру.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map((node) => {
    const dot = nodeDot(node);
    const note = node.active ? `${node.address}:${node.port}` : "нет в подписке";
    return `<tr data-id="${esc(node.id)}" class="${node.enabled ? "" : "is-off"} ${node.active ? "" : "is-gone"}">
      <td>
        <div class="name">
          <b><i class="dot ${dot}"></i>${esc(node.name)}</b>
          <span class="sub">${esc(note)}</span>
        </div>
      </td>
      <td><span class="proto proto-${esc(node.protocol)}">${esc(protocolName(node.protocol))}</span></td>
      <td><label class="check"><input type="checkbox" data-enable="${esc(node.id)}" ${node.enabled ? "checked" : ""} ${node.supported ? "" : "disabled"}></label></td>
    </tr>`;
  }).join("");
}

function renderRuns() {
  const root = $("runs");
  if (!state.runs.length) {
    root.innerHTML = `<p class="empty">Проверок ещё не было.</p>`;
    return;
  }
  root.innerHTML = state.runs.map((run) => `
    <article class="run">
      <button type="button" data-open-run="${run.id}">
        <strong>${esc(formatTime(run.started_at))}</strong>
        <span>${run.trigger === "schedule" ? "по расписанию" : "вручную"}</span>
        <span class="status-${esc(run.status)}">${esc(statusLabel(run.status))}</span>
        <span>${esc(run.ok_count)} успешно, ${esc(run.fail_count)} с ошибкой${run.error ? ` · ${esc(run.error)}` : ""}</span>
      </button>
      <div class="run-detail" hidden></div>
    </article>
  `).join("");
}

function fillForm(settings) {
  if (!settings || state.formDirty) return;
  $("subscription_url").value = settings.subscription_url || "";
  $("subscription_insecure").checked = Boolean(settings.subscription_insecure);
  $("refresh_before_run").checked = Boolean(settings.refresh_before_run);
  $("tls_insecure_if_no_sni").checked = Boolean(settings.tls_insecure_if_no_sni);
  $("interval_minutes").value = settings.interval_minutes;
  $("concurrency").value = settings.concurrency;
  $("retention_days").value = settings.retention_days;
  $("scheduler_enabled").checked = Boolean(settings.scheduler_enabled);
  $("measure_download").checked = Boolean(settings.measure_download);
  $("measure_upload").checked = Boolean(settings.measure_upload);
  syncGroups();
  renderEstimate();
}

function collectForm() {
  return {
    subscription_url: $("subscription_url").value.trim(),
    subscription_insecure: $("subscription_insecure").checked,
    refresh_before_run: $("refresh_before_run").checked,
    tls_insecure_if_no_sni: $("tls_insecure_if_no_sni").checked,
    interval_minutes: Number($("interval_minutes").value),
    concurrency: Number($("concurrency").value),
    retention_days: Number($("retention_days").value),
    scheduler_enabled: $("scheduler_enabled").checked,
    measure_download: $("measure_download").checked,
    measure_upload: $("measure_upload").checked,
  };
}

function renderEstimate() {
  const enabled = state.nodes.filter((node) => node.active && node.supported && node.enabled).length;
  const parts = ["отклик"];
  if ($("measure_download").checked) parts.push("входящая");
  if ($("measure_upload").checked) parts.push("исходящая");
  const text = enabled
    ? `В замере: ${parts.join(", ")}. Объём за прогон зависит от скорости канала.`
    : "Нет включённых узлов.";
  document.querySelectorAll(".estimate").forEach((el) => {
    el.textContent = text;
  });
}

function setSettingsPane(name) {
  const panes = ["subscription", "schedule", "check"];
  const pane = panes.includes(name) ? name : "subscription";
  document.querySelectorAll("[data-settings-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.settingsNav === pane);
  });
  document.querySelectorAll("[data-settings-pane]").forEach((section) => {
    section.hidden = section.dataset.settingsPane !== pane;
  });
}

async function reloadAll() {
  const [remote, nodes, series, runs, settings] = await Promise.all([
    api("/api/state"),
    api("/api/nodes"),
    api("/api/series?hours=48"),
    api("/api/runs?limit=30"),
    api("/api/settings"),
  ]);
  state.remote = remote;
  state.nodes = nodes;
  state.runs = runs;
  state.settings = settings;
  state.series = new Map();
  for (const row of series) {
    if (!state.series.has(row.node_id)) state.series.set(row.node_id, []);
    state.series.get(row.node_id).push(row);
  }
  fillForm(settings);
  renderOverview();
  renderRuns();
}

async function tick() {
  state.tick += 1;
  if (state.remote && !state.remote.running) {
    $("stat-next").textContent = nextLabel(state.remote);
  }
  if (state.tick % 2 !== 0 || $("shell").hidden) return;
  try {
    const remote = await api("/api/state");
    const wasRunning = Boolean(state.remote.running);
    const done = remote.running ? remote.running.done : -1;
    state.remote = remote;
    renderStatus();
    if (remote.running && done !== state.lastDone) {
      state.lastDone = done;
      const nodes = await api("/api/nodes");
      state.nodes = nodes;
      renderOverview();
    }
    if (wasRunning && !remote.running) {
      state.lastDone = -1;
      await reloadAll();
    }
  } catch (error) {
    if (!error.unauthorized) {
      /* временный сбой опроса не должен забивать экран */
    }
  }
}

const PAGE_TITLES = {
  overview: "Узлы подписки",
  subscription: "Подписка",
  history: "История",
  settings: "Настройки",
};

function setView(name) {
  const view = ["overview", "subscription", "history", "settings"].includes(name) ? name : "overview";
  $("page-title").textContent = PAGE_TITLES[view];
  for (const item of ["overview", "subscription", "history", "settings"]) {
    $(`view-${item}`).hidden = item !== view;
  }
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  $("footnote").hidden = view !== "subscription";
  if (location.hash !== `#${view}`) history.replaceState(null, "", `#${view}`);
}

async function refreshSubscription() {
  $("refresh-button").disabled = true;
  try {
    const result = await api("/api/subscription/refresh", { method: "POST" });
    await reloadAll();
    toast(`Подписка обновлена: ${result.count} узлов`);
  } catch (error) {
    if (!error.unauthorized) toast(error.message);
  } finally {
    $("refresh-button").disabled = Boolean(state.remote.running);
  }
}

async function startRun(body) {
  try {
    await api("/api/runs", { method: "POST", json: body });
    const remote = await api("/api/state");
    state.remote = remote;
    renderStatus();
  } catch (error) {
    if (!error.unauthorized) toast(error.message);
  }
}

async function toggleNode(id, enabled, input) {
  try {
    await api(`/api/nodes/${id}/enabled`, { method: "POST", json: { enabled } });
    const node = state.nodes.find((item) => item.id === id);
    if (node) node.enabled = enabled;
    renderOverview();
    renderEstimate();
  } catch (error) {
    input.checked = !enabled;
    if (!error.unauthorized) toast(error.message);
  }
}

async function setAll(enabled) {
  try {
    await api("/api/nodes/enabled", { method: "POST", json: { enabled } });
    await reloadAll();
  } catch (error) {
    if (!error.unauthorized) toast(error.message);
  }
}

function cssColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function drawChart(canvas, rows) {
  const width = canvas.clientWidth || 640;
  const height = 220;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const points = rows.filter((row) => row.download_bps != null || row.upload_bps != null);
  if (!points.length) {
    ctx.fillStyle = cssColor("--muted", "#6e6e6e");
    ctx.font = "14px sans-serif";
    ctx.fillText("Пока нет измерений", 12, 28);
    return;
  }
  const pad = { left: 52, right: 12, top: 16, bottom: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = Math.max(
    1,
    ...points.flatMap((row) => [row.download_bps, row.upload_bps].filter((value) => value != null).map((value) => (value * 8) / 1e6)),
  );
  ctx.strokeStyle = cssColor("--line", "#e3e3e3");
  ctx.fillStyle = cssColor("--muted", "#6e6e6e");
  ctx.font = "11px ui-monospace, monospace";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const y = pad.top + (plotH * step) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText((max * (1 - step / 4)).toFixed(max >= 10 ? 0 : 1), 6, y + 4);
  }
  strokeSeries(ctx, points, "download_bps", cssColor("--ok", "#2f9e62"), pad, plotW, plotH, max);
  strokeSeries(ctx, points, "upload_bps", cssColor("--red", "#d14332"), pad, plotW, plotH, max);
  ctx.fillStyle = cssColor("--muted", "#6e6e6e");
  ctx.fillText(formatTime(points[0].tested_at), pad.left, height - 8);
  const lastLabel = formatTime(points[points.length - 1].tested_at);
  ctx.fillText(lastLabel, width - pad.right - ctx.measureText(lastLabel).width, height - 8);
}

function strokeSeries(ctx, points, key, color, pad, plotW, plotH, max) {
  const coords = [];
  points.forEach((row, index) => {
    if (row[key] == null) return;
    const x = pad.left + (points.length === 1 ? plotW / 2 : (plotW * index) / (points.length - 1));
    const y = pad.top + plotH - ((row[key] * 8) / 1e6 / max) * plotH;
    coords.push([x, y, index]);
  });
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  coords.forEach(([x, y, index], position) => {
    const previous = coords[position - 1];
    if (!previous || index !== previous[2] + 1) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = color;
  for (const [x, y] of coords) {
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

async function openNode(id) {
  const node = state.nodes.find((item) => item.id === id);
  if (!node) return;
  let history = [];
  try {
    history = await api(`/api/nodes/${encodeURIComponent(id)}/history?limit=500`);
  } catch (error) {
    if (!error.unauthorized) toast(error.message);
    return;
  }
  const dialog = $("node-dialog");
  const recent = history.slice(-8).reverse();
  dialog.innerHTML = `
    <div class="dialog-head">
      <div>
        <p class="eyebrow">${esc(protocolName(node.protocol))}</p>
        <h2>${esc(node.name)}</h2>
        <p class="muted">${esc(node.address)}:${esc(node.port)}</p>
      </div>
      <button type="button" class="ghost" data-close>Закрыть</button>
    </div>
    <p class="legend"><span><i class="down"></i>входящая</span><span><i class="up"></i>исходящая</span></p>
    <canvas></canvas>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Время</th><th>Отклик</th><th>Входящая</th><th>Исходящая</th><th>Итог</th></tr></thead>
        <tbody>
          ${recent.map((row) => `<tr>
            <td>${esc(formatTime(row.tested_at))}</td>
            <td class="metric">${esc(formatMs(row.latency_ms))}</td>
            <td class="metric">${esc(mbps(row.download_bps))}</td>
            <td class="metric">${esc(mbps(row.upload_bps))}</td>
            <td>${row.ok ? "ок" : esc(row.error || "ошибка")}</td>
          </tr>`).join("") || `<tr><td colspan="5" class="empty">Измерений нет</td></tr>`}
        </tbody>
      </table>
    </div>`;
  dialog.showModal();
  const stopBackgroundScroll = (event) => {
    if (!dialog.open || event.deltaY === 0) return;
    const box = dialog.getBoundingClientRect();
    const overDialog = event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
    const canScroll = dialog.scrollHeight > dialog.clientHeight + 1;
    const atTop = dialog.scrollTop <= 0;
    const atBottom = dialog.scrollTop + dialog.clientHeight >= dialog.scrollHeight - 1;
    const dialogTakesIt = overDialog && canScroll && !((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom));
    if (!dialogTakesIt) event.preventDefault();
  };
  document.addEventListener("wheel", stopBackgroundScroll, { passive: false });
  dialog.addEventListener("close", () => {
    document.removeEventListener("wheel", stopBackgroundScroll);
  }, { once: true });
  dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  const canvas = dialog.querySelector("canvas");
  requestAnimationFrame(() => drawChart(canvas, history));
}

async function openRun(id, article) {
  const detail = article.querySelector(".run-detail");
  if (detail.dataset.loaded === "1" && !detail.hidden) {
    detail.hidden = true;
    return;
  }
  try {
    const payload = await api(`/api/runs/${id}`);
    const rows = payload.results || [];
    detail.innerHTML = `<div class="table-wrap"><table>
      <thead><tr><th>Узел</th><th>Канал</th><th>Отклик</th><th>Входящая</th><th>Исходящая</th></tr></thead>
      <tbody>${rows.map((row) => `<tr>
        <td>
          <div class="name">
            <b><i class="dot ${resultDot(row.ok, row.alive)}"></i>${esc(row.name)}</b>
            <span class="sub">${esc(row.tested_at ? formatTime(row.tested_at) : "")}</span>
          </div>
        </td>
        <td><span class="proto proto-${esc(row.protocol)}">${esc(protocolName(row.protocol))}</span></td>
        <td class="metric">${esc(formatMs(row.latency_ms))}</td>
        <td class="metric">${esc(mbps(row.download_bps))}${row.download_bps != null ? "<small>Мбит/с</small>" : ""}</td>
        <td class="metric">${esc(mbps(row.upload_bps))}${row.upload_bps != null ? "<small>Мбит/с</small>" : ""}</td>
      </tr>`).join("") || `<tr><td colspan="5" class="empty">В этом прогоне нет результатов</td></tr>`}</tbody>
    </table></div>`;
    detail.dataset.loaded = "1";
    detail.hidden = false;
  } catch (error) {
    if (!error.unauthorized) toast(error.message);
  }
}

function bind() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
  $("search").addEventListener("input", (event) => {
    state.query = event.target.value;
    renderTable();
  });
  $("protocol-filter").addEventListener("change", (event) => {
    state.protocol = event.target.value;
    renderTable();
  });
  $("sub-search").addEventListener("input", (event) => {
    state.subQuery = event.target.value;
    renderSubscription();
  });
  $("show-inactive").addEventListener("change", (event) => {
    state.showInactive = event.target.checked;
    renderSubscription();
  });
  $("subscription-nodes").addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row?.dataset.id) return;
    if (event.target.closest("input, label, button")) return;
    openNode(row.dataset.id);
  });
  $("subscription-nodes").addEventListener("change", (event) => {
    const input = event.target.closest("[data-enable]");
    if (!input) return;
    toggleNode(input.dataset.enable, input.checked, input);
  });
  $("column-picker").addEventListener("click", () => {
    const menu = $("column-menu");
    const open = menu.hidden;
    menu.hidden = !open;
    $("column-picker").setAttribute("aria-expanded", String(open));
  });
  $("column-menu").addEventListener("change", (event) => {
    const input = event.target.closest("input");
    if (!input) return;
    state.columns[input.value] = input.checked;
    localStorage.setItem("bababui-columns", JSON.stringify(state.columns));
    applyColumns();
  });
  document.addEventListener("click", (event) => {
    if (event.target.closest("#column-picker, #column-menu")) return;
    $("column-menu").hidden = true;
    $("column-picker").setAttribute("aria-expanded", "false");
  });
  document.querySelector("#nodes thead").addEventListener("click", (event) => {
    const th = event.target.closest("[data-sort]");
    if (!th) return;
    if (state.sortKey !== th.dataset.sort || !state.sortDir) {
      state.sortKey = th.dataset.sort;
      state.sortDir = "asc";
    } else if (state.sortDir === "asc") {
      state.sortDir = "desc";
    } else {
      state.sortKey = null;
      state.sortDir = null;
    }
    renderTable();
  });
  $("nodes").addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row?.dataset.id) return;
    const test = event.target.closest("[data-test]");
    if (test) {
      startRun({ node_ids: [test.dataset.test], include_disabled: true });
      return;
    }
    if (event.target.closest("input, label, button")) return;
    openNode(row.dataset.id);
  });
  $("nodes").addEventListener("change", (event) => {
    const input = event.target.closest("[data-enable]");
    if (!input) return;
    toggleNode(input.dataset.enable, input.checked, input);
  });
  $("refresh-button").addEventListener("click", refreshSubscription);
  $("run-button").addEventListener("click", () => startRun({}));
  $("stop-button").addEventListener("click", async () => {
    try {
      await api("/api/runs/cancel", { method: "POST" });
    } catch (error) {
      if (!error.unauthorized) toast(error.message);
    }
  });
  $("enable-all").addEventListener("click", () => setAll(true));
  $("disable-all").addEventListener("click", () => setAll(false));
  document.querySelectorAll("[data-settings-nav]").forEach((button) => {
    button.addEventListener("click", () => setSettingsPane(button.dataset.settingsNav));
  });
  $("settings-form").addEventListener("input", () => {
    state.formDirty = true;
    syncGroups();
    renderEstimate();
  });
  $("settings-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const saved = await api("/api/settings", { method: "PUT", json: collectForm() });
      state.settings = saved;
      state.formDirty = false;
      fillForm(saved);
      state.remote.scheduler_enabled = saved.scheduler_enabled;
      state.remote.interval_minutes = saved.interval_minutes;
      renderStatus();
      toast("Настройки сохранены");
    } catch (error) {
      if (!error.unauthorized) toast(error.message);
    }
  });
  $("export-button").addEventListener("click", async () => {
    try {
      const response = await fetch("/api/export.csv", { headers: authHeaders() });
      if (!response.ok) throw new Error("не удалось скачать CSV");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "bababui.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(error.message);
    }
  });
  $("clear-button").addEventListener("click", async () => {
    if (!window.confirm("Удалить все результаты проверок?")) return;
    try {
      await api("/api/history", { method: "DELETE" });
      await reloadAll();
      toast("История очищена");
    } catch (error) {
      if (!error.unauthorized) toast(error.message);
    }
  });
  $("runs").addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-run]");
    if (!button) return;
    openRun(button.dataset.openRun, button.closest("article"));
  });
  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    sessionStorage.setItem("token", $("password").value);
    try {
      await api("/api/state");
      $("login-error").hidden = true;
      showApp();
      await reloadAll();
    } catch (error) {
      sessionStorage.removeItem("token");
      $("login-error").hidden = false;
      $("login-error").textContent = error.unauthorized ? "Неверный пароль" : error.message;
    }
  });
}

async function boot() {
  bind();
  setView((location.hash || "#overview").slice(1));
  try {
    const health = await fetch("/api/health").then((response) => response.json());
    if (health.auth && !sessionStorage.getItem("token")) {
      showLogin();
    } else {
      showApp();
      await reloadAll();
    }
  } catch (error) {
    if (!error.unauthorized) {
      toast(error.message || "Нет связи с сервисом");
      showApp();
    }
  }
  setInterval(tick, 1000);
}

boot();
