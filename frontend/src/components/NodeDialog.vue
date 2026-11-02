<script setup>
import { computed, ref, watch } from "vue";
import { formatMs, formatTime, mbps, protocolName } from "../lib/format.js";
import { t, tMsg } from "../lib/i18n.js";
import { state } from "../store.js";
import NodeChart from "./NodeChart.vue";

const dialog = ref(null);
const recent = computed(() => (state.dialog?.history || []).slice(-8).reverse());

function stopBackgroundScroll(event) {
  const el = dialog.value;
  if (!el?.open || event.deltaY === 0) return;
  const box = el.getBoundingClientRect();
  const overDialog = event.clientX >= box.left && event.clientX <= box.right
    && event.clientY >= box.top && event.clientY <= box.bottom;
  const canScroll = el.scrollHeight > el.clientHeight + 1;
  const atTop = el.scrollTop <= 0;
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
  const dialogTakesIt = overDialog && canScroll && !((event.deltaY < 0 && atTop) || (event.deltaY > 0 && atBottom));
  if (!dialogTakesIt) event.preventDefault();
}

watch(() => state.dialog, (value) => {
  if (!value || dialog.value.open) return;
  dialog.value.showModal();
  document.addEventListener("wheel", stopBackgroundScroll, { passive: false });
}, { flush: "post" });

function closed() {
  document.removeEventListener("wheel", stopBackgroundScroll);
  state.dialog = null;
}
</script>

<template>
  <dialog ref="dialog" @close="closed">
    <template v-if="state.dialog">
      <div class="dialog-head">
        <div>
          <p class="eyebrow">{{ protocolName(state.dialog.node.protocol) }}</p>
          <h2>{{ state.dialog.node.name }}</h2>
          <p class="muted">{{ state.dialog.node.address }}:{{ state.dialog.node.port }}</p>
        </div>
        <button type="button" class="ghost" @click="dialog.close()">{{ t("action.close") }}</button>
      </div>
      <p class="legend">
        <span><i class="down"></i>{{ t("dialog.download") }}</span>
        <span><i class="up"></i>{{ t("dialog.upload") }}</span>
      </p>
      <NodeChart :rows="state.dialog.history" />
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t("column.time") }}</th>
              <th>{{ t("column.latency") }}</th>
              <th>{{ t("column.download") }}</th>
              <th>{{ t("column.upload") }}</th>
              <th>{{ t("column.result") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in recent" :key="row.tested_at">
              <td>{{ formatTime(row.tested_at) }}</td>
              <td class="metric">{{ formatMs(row.latency_ms) }}</td>
              <td class="metric">{{ mbps(row.download_bps) }}</td>
              <td class="metric">{{ mbps(row.upload_bps) }}</td>
              <td>{{ row.ok ? t("dialog.ok") : tMsg(row.error) || t("dialog.error") }}</td>
            </tr>
            <tr v-if="!recent.length"><td colspan="5" class="empty">{{ t("dialog.noMeasurements") }}</td></tr>
          </tbody>
        </table>
      </div>
    </template>
  </dialog>
</template>
