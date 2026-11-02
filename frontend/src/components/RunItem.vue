<script setup>
import { ref } from "vue";
import { api } from "../lib/api.js";
import { formatMs, formatTime, resultDot, statusLabel } from "../lib/format.js";
import { t, tMsg } from "../lib/i18n.js";
import { reportError } from "../store.js";
import NodeName from "./NodeName.vue";
import ProtoBadge from "./ProtoBadge.vue";
import SpeedValue from "./SpeedValue.vue";

const props = defineProps({ run: { type: Object, required: true } });
const open = ref(false);
const rows = ref([]);

async function toggle() {
  if (open.value) {
    open.value = false;
    return;
  }
  try {
    const payload = await api(`/api/runs/${props.run.id}`);
    rows.value = payload.results || [];
    open.value = true;
  } catch (error) {
    reportError(error);
  }
}
</script>

<template>
  <article class="run">
    <button type="button" @click="toggle">
      <strong>{{ formatTime(run.started_at) }}</strong>
      <span>{{ t(run.trigger === "schedule" ? "history.scheduled" : "history.manual") }}</span>
      <span :class="`status-${run.status}`">{{ statusLabel(run.status) }}</span>
      <span>{{ t("history.summary", { ok: run.ok_count, fail: run.fail_count }) }}{{ run.error ? ` · ${tMsg(run.error)}` : "" }}</span>
    </button>
    <div class="run-detail" :hidden="!open">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t("column.node") }}</th>
              <th>{{ t("column.protocol") }}</th>
              <th>{{ t("column.latency") }}</th>
              <th>{{ t("column.download") }}</th>
              <th>{{ t("column.upload") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in rows" :key="index">
              <td>
                <NodeName
                  :dot="resultDot(row.ok, row.alive)"
                  :name="row.name"
                  :sub="row.tested_at ? formatTime(row.tested_at) : ''"
                />
              </td>
              <td><ProtoBadge :protocol="row.protocol" /></td>
              <td class="metric">{{ formatMs(row.latency_ms) }}</td>
              <td class="metric"><SpeedValue :bps="row.download_bps" /></td>
              <td class="metric"><SpeedValue :bps="row.upload_bps" /></td>
            </tr>
            <tr v-if="!rows.length"><td colspan="5" class="empty">{{ t("history.noResults") }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </article>
</template>
