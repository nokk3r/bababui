<script setup>
import { DownloadIcon, Trash2Icon } from "@lucide/vue";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
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
  <section class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex flex-wrap gap-2">
        <Button variant="outline" size="lg" @click="exportCsv">
          <DownloadIcon aria-hidden="true" />{{ t("action.downloadCsv") }}
        </Button>
        <AlertDialog>
          <AlertDialogTrigger as-child>
            <Button variant="destructive" size="lg" :disabled="Boolean(state.remote.running)">
              <Trash2Icon aria-hidden="true" />{{ t("action.clearHistory") }}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{{ t("history.confirmClear") }}</AlertDialogTitle>
              <AlertDialogDescription>{{ t("history.confirmClearNote") }}</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{{ t("action.cancel") }}</AlertDialogCancel>
              <AlertDialogAction variant="destructive" @click="clearHistory">{{ t("action.clearHistory") }}</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
    <div class="flex flex-col gap-2">
      <RunItem v-for="run in state.runs" :key="run.id" :run="run" />
      <p v-if="!state.runs.length" class="rounded-xl border px-4 py-7 text-muted-foreground">{{ t("history.empty") }}</p>
    </div>
  </section>
</template>
