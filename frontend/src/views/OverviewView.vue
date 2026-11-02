<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import NodeName from "../components/NodeName.vue";
import ProtoBadge from "../components/ProtoBadge.vue";
import SparkLine from "../components/SparkLine.vue";
import SpeedValue from "../components/SpeedValue.vue";
import { formatMs, formatTime, mean, nodeDot, protocolName } from "../lib/format.js";
import { i18n, t } from "../lib/i18n.js";
import { COLUMN_KEYS, openNode, startRun, state } from "../store.js";

const COLUMN_LABELS = {
  protocol: "column.protocol",
  latency_ms: "column.latency",
  download_bps: "column.download",
  upload_bps: "column.upload",
  avg_latency_ms: "column.avgLatency",
  avg_download_bps: "column.avgDownload",
  avg_upload_bps: "column.avgUpload",
  spark: "column.spark",
  action: "column.action",
};

const SORTABLE = [
  ["name", "column.node"],
  ...COLUMN_KEYS.slice(0, 7).map((key) => [key, COLUMN_LABELS[key]]),
];

const menuOpen = ref(false);
const picker = ref(null);
const menu = ref(null);

const samples = computed(() => (
  state.nodes.filter((node) => node.active && node.supported && node.enabled && node.last_ok)
));
const activeCount = computed(() => state.nodes.filter((node) => node.active).length);
const avgLatency = computed(() => mean(samples.value.map((node) => node.latency_ms)));
const avgDownload = computed(() => mean(samples.value.map((node) => node.download_bps)));
const avgUpload = computed(() => mean(samples.value.map((node) => node.upload_bps)));

const protocols = computed(() => [...new Set(state.nodes.map((node) => node.protocol))].sort());

watch(protocols, (list) => {
  if (state.protocol !== "all" && !list.includes(state.protocol)) state.protocol = "all";
});

function sortNodes(nodes) {
  if (!state.sortKey || !state.sortDir) return nodes;
  const direction = state.sortDir === "asc" ? 1 : -1;
  const key = state.sortKey;
  return nodes.slice().sort((a, b) => {
    if (key === "name" || key === "protocol") {
      const left = key === "name" ? a.name : protocolName(a.protocol);
      const right = key === "name" ? b.name : protocolName(b.protocol);
      const compared = left.localeCompare(right, i18n.lang);
      return compared === 0 ? 0 : compared * direction;
    }
    const left = a[key];
    const right = b[key];
    const leftEmpty = left == null || left === "";
    const rightEmpty = right == null || right === "";
    if (leftEmpty && rightEmpty) return a.name.localeCompare(b.name, i18n.lang);
    if (leftEmpty) return 1;
    if (rightEmpty) return -1;
    const compared = Number(left) - Number(right);
    return compared === 0 ? a.name.localeCompare(b.name, i18n.lang) : compared * direction;
  });
}

const rows = computed(() => {
  const query = state.query.trim().toLowerCase();
  const visible = state.nodes.filter((node) => {
    if (!node.active) return false;
    if (state.protocol !== "all" && node.protocol !== state.protocol) return false;
    if (!query) return true;
    return `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query);
  }).map((node) => {
    const history = state.series.get(node.id) || [];
    return {
      ...node,
      avg_latency_ms: mean(history.map((row) => (row.ok ? row.latency_ms : null))),
      avg_download_bps: mean(history.map((row) => (row.ok ? row.download_bps : null))),
      avg_upload_bps: mean(history.map((row) => (row.ok ? row.upload_bps : null))),
      spark: history.slice(-24).map((row) => row.download_bps),
    };
  });
  return sortNodes(visible);
});

const emptyText = computed(() => {
  const waiting = !state.remote.last_refresh_at && !state.remote.last_refresh_error;
  return waiting ? t("common.loadingSubscription") : t("common.noMatches");
});

const hiddenColumns = computed(() => (
  COLUMN_KEYS.filter((key) => !state.columns[key]).map((key) => `hide-${key}`)
));

function sortBy(key) {
  if (state.sortKey !== key || !state.sortDir) {
    state.sortKey = key;
    state.sortDir = "asc";
  } else if (state.sortDir === "asc") {
    state.sortDir = "desc";
  } else {
    state.sortKey = null;
    state.sortDir = null;
  }
}

function isSorted(key) {
  return key === state.sortKey && Boolean(state.sortDir);
}

function ariaSort(key) {
  if (!isSorted(key)) return "none";
  return state.sortDir === "asc" ? "ascending" : "descending";
}

function saveColumns() {
  localStorage.setItem("bababui-columns", JSON.stringify(state.columns));
}

function closeMenu(event) {
  if (picker.value?.contains(event.target) || menu.value?.contains(event.target)) return;
  menuOpen.value = false;
}

function rowClick(event, node) {
  if (event.target.closest("input, label, button")) return;
  openNode(node.id);
}

onMounted(() => document.addEventListener("click", closeMenu));
onBeforeUnmount(() => document.removeEventListener("click", closeMenu));
</script>

<template>
  <section>
    <div class="cards">
      <article class="card">
        <p>{{ t("stat.inSubscription") }}</p>
        <strong>{{ activeCount }}</strong>
      </article>
      <article class="card">
        <p>{{ t("stat.avgLatency") }}</p>
        <strong>
          <template v-if="avgLatency == null">—</template>
          <template v-else>{{ Math.round(avgLatency) }}<small>{{ t("unit.ms") }}</small></template>
        </strong>
      </article>
      <article class="card">
        <p>{{ t("stat.avgDownload") }}</p>
        <strong><SpeedValue :bps="avgDownload" /></strong>
      </article>
      <article class="card">
        <p>{{ t("stat.avgUpload") }}</p>
        <strong><SpeedValue :bps="avgUpload" /></strong>
      </article>
    </div>

    <div class="toolbar">
      <input
        id="search"
        v-model="state.query"
        type="search"
        :placeholder="t('search.placeholder')"
        :aria-label="t('search.node')"
      >
      <select v-model="state.protocol" :aria-label="t('filter.protocol')">
        <option value="all">{{ t("filter.allProtocols") }}</option>
        <option v-for="protocol in protocols" :key="protocol" :value="protocol">{{ protocolName(protocol) }}</option>
      </select>
    </div>

    <div class="table-frame">
      <button
        ref="picker"
        type="button"
        class="column-picker"
        :aria-label="t('columns.label')"
        :aria-expanded="menuOpen"
        aria-controls="column-menu"
        @click="menuOpen = !menuOpen"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path fill="currentColor" d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.2 7.2 0 0 0-1.63-.94l-.36-2.54a.5.5 0 0 0-.5-.42h-3.84a.5.5 0 0 0-.5.42l-.36 2.54c-.58.22-1.13.54-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.71 8.48a.5.5 0 0 0 .12.64l2.03 1.58c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32c.13.22.4.31.6.22l2.39-.96c.5.4 1.05.72 1.63.94l.36 2.54c.05.24.26.42.5.42h3.84c.24 0 .45-.18.5-.42l.36-2.54c.58-.22 1.13-.54 1.63-.94l2.39.96c.22.09.47 0 .6-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7z" />
        </svg>
      </button>
      <div id="column-menu" ref="menu" class="column-menu" :hidden="!menuOpen">
        <label v-for="key in COLUMN_KEYS" :key="key">
          <input v-model="state.columns[key]" type="checkbox" @change="saveColumns">
          <span>{{ t(COLUMN_LABELS[key]) }}</span>
        </label>
      </div>
      <div class="table-wrap">
        <table id="nodes" :class="hiddenColumns">
          <thead>
            <tr>
              <th
                v-for="[key, label] in SORTABLE"
                :key="key"
                :data-sort="key"
                :data-col="key"
                :class="{ sorted: isSorted(key) }"
                :data-dir="isSorted(key) ? state.sortDir : null"
                :aria-sort="ariaSort(key)"
                @click="sortBy(key)"
              >{{ t(label) }}</th>
              <th data-col="spark">{{ t("column.spark") }}</th>
              <th data-col="action"></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="node in rows"
              :key="node.id"
              :class="{ 'is-off': !node.enabled, 'is-gone': !node.active }"
              @click="rowClick($event, node)"
            >
              <td data-col="name">
                <NodeName
                  :dot="nodeDot(node)"
                  :name="node.name"
                  :sub="node.last_tested_at ? formatTime(node.last_tested_at) : ''"
                />
              </td>
              <td data-col="protocol"><ProtoBadge :protocol="node.protocol" /></td>
              <td data-col="latency_ms" class="metric">{{ formatMs(node.latency_ms) }}</td>
              <td data-col="download_bps" class="metric"><SpeedValue :bps="node.download_bps" /></td>
              <td data-col="upload_bps" class="metric"><SpeedValue :bps="node.upload_bps" /></td>
              <td data-col="avg_latency_ms" class="metric">{{ formatMs(node.avg_latency_ms) }}</td>
              <td data-col="avg_download_bps" class="metric"><SpeedValue :bps="node.avg_download_bps" /></td>
              <td data-col="avg_upload_bps" class="metric"><SpeedValue :bps="node.avg_upload_bps" /></td>
              <td data-col="spark"><SparkLine :values="node.spark" /></td>
              <td data-col="action">
                <button
                  type="button"
                  class="ghost row-button"
                  :disabled="!node.supported"
                  @click="startRun({ node_ids: [node.id], include_disabled: true })"
                >{{ t("action.check") }}</button>
              </td>
            </tr>
            <tr v-if="!rows.length"><td colspan="10" class="empty">{{ emptyText }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
