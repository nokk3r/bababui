<script setup>
import { ChevronDownIcon, Trash2Icon } from "@lucide/vue";
import { computed, ref } from "vue";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "../lib/api.js";
import { formatMs, formatTime, resultDot, statusLabel } from "../lib/format.js";
import { t, tMsg } from "../lib/i18n.js";
import { reloadAll, reportError, toast } from "../store.js";
import NodeName from "./NodeName.vue";
import ProtoBadge from "./ProtoBadge.vue";
import SpeedValue from "./SpeedValue.vue";

const STATUS_COLORS = {
  done: "text-success",
  running: "text-warning",
  cancelled: "text-muted-foreground",
  failed: "text-destructive",
};

const props = defineProps({ run: { type: Object, required: true } });
const open = ref(false);
const rows = ref([]);
const runSources = computed(() => (props.run.sources || []).map(tMsg).join(", "));

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

async function remove() {
  try {
    await api(`/api/runs/${props.run.id}`, { method: "DELETE" });
    await reloadAll();
    toast(t("toast.runDeleted"));
  } catch (error) {
    reportError(error);
  }
}
</script>

<template>
  <article class="overflow-hidden rounded-xl border">
    <div class="flex items-center hover:bg-muted">
      <button
        type="button"
        class="grid min-w-0 flex-1 grid-cols-[1fr_1fr_auto] items-center gap-x-3 gap-y-1 px-4 py-3 text-left text-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset md:grid-cols-[150px_110px_100px_1fr_auto]"
        :aria-expanded="open"
        @click="toggle"
      >
        <strong class="font-medium tabular">{{ formatTime(run.started_at) }}</strong>
        <span class="text-muted-foreground">{{ t(run.trigger === "schedule" ? "history.scheduled" : "history.manual") }}</span>
        <ChevronDownIcon class="col-start-3 row-start-1 size-4 text-muted-foreground transition-transform md:col-start-5" :class="{ 'rotate-180': open }" aria-hidden="true" />
        <span :class="STATUS_COLORS[run.status]">{{ statusLabel(run.status) }}</span>
        <!-- У проверки по расписанию видно, чьё это было расписание: у каждого источника оно своё. -->
        <span class="min-w-0 break-words"><span v-if="runSources" class="font-medium">{{ runSources }} · </span>{{ t("history.summary", { ok: run.ok_count, fail: run.fail_count }) }}{{ run.error ? ` · ${tMsg(run.error)}` : "" }}</span>
      </button>
      <!-- Отдельно от кнопки раскрытия: кнопка внутри кнопки недопустима. -->
      <AlertDialog>
        <AlertDialogTrigger as-child>
          <Button
            variant="ghost"
            size="icon"
            class="mr-2 shrink-0 text-muted-foreground hover:text-destructive"
            :aria-label="t('history.deleteRun', { time: formatTime(run.started_at) })"
            :disabled="run.status === 'running'"
          >
            <Trash2Icon aria-hidden="true" />
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{{ t("history.confirmDelete", { time: formatTime(run.started_at) }) }}</AlertDialogTitle>
            <AlertDialogDescription>{{ t("history.confirmDeleteNote") }}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{{ t("action.cancel") }}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" @click="remove">{{ t("action.delete") }}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    <div v-if="open" class="border-t">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent">
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.node") }}</TableHead>
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.protocol") }}</TableHead>
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.latency") }}</TableHead>
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.download") }}</TableHead>
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.upload") }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-for="(row, index) in rows" :key="index">
            <TableCell class="max-w-64 px-3">
              <NodeName
                :dot="resultDot(row.ok, row.alive)"
                :name="row.name"
                :sub="row.tested_at ? formatTime(row.tested_at) : ''"
              />
            </TableCell>
            <TableCell class="px-3"><ProtoBadge :protocol="row.protocol" /></TableCell>
            <TableCell class="px-3 tabular">{{ formatMs(row.latency_ms) }}</TableCell>
            <TableCell class="px-3 tabular"><SpeedValue :bps="row.download_bps" /></TableCell>
            <TableCell class="px-3 tabular"><SpeedValue :bps="row.upload_bps" /></TableCell>
          </TableRow>
          <TableRow v-if="!rows.length">
            <TableCell colspan="5" class="px-3 py-6 text-muted-foreground">{{ t("history.noResults") }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </article>
</template>
