<script setup>
import RunItem from "../components/RunItem.vue";
import { api, authHeaders } from "../lib/api.js";
import { t } from "../lib/i18n.js";
import { reloadAll, reportError, state, toast } from "../store.js";

async function exportCsv() {
  try {
    const response = await fetch("/api/export.csv", { headers: authHeaders() });
    if (!response.ok) throw new Error(t("error.csvFailed"));
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
}

async function clearHistory() {
  if (!window.confirm(t("history.confirmClear"))) return;
  try {
    await api("/api/history", { method: "DELETE" });
    await reloadAll();
    toast(t("toast.historyCleared"));
  } catch (error) {
    reportError(error);
  }
}
</script>

<template>
  <section>
    <div class="section-head">
      <div>
        <p class="muted">{{ t("history.lead") }}</p>
      </div>
      <div class="top-actions">
        <button type="button" class="ghost" @click="exportCsv">{{ t("action.downloadCsv") }}</button>
        <button type="button" class="danger" @click="clearHistory">{{ t("action.clearHistory") }}</button>
      </div>
    </div>
    <div class="runs">
      <RunItem v-for="run in state.runs" :key="run.id" :run="run" />
      <p v-if="!state.runs.length" class="empty">{{ t("history.empty") }}</p>
    </div>
  </section>
</template>
