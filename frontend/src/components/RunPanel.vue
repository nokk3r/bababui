<script setup>
import { ChevronDownIcon, Loader2Icon, SquareIcon, XIcon } from "@lucide/vue";
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { nodeDot } from "../lib/format.js";
import { t } from "../lib/i18n.js";
import { state, stopRun } from "../store.js";
import SpeedValue from "./SpeedValue.vue";
import StatusIcon from "./StatusIcon.vue";

/* Ход проверки в плавающей панели: страница не блокируется и не прыгает, панель видна в любом разделе.
   Ширину полосы считает App.vue, здесь только показ. */
const SUMMARY_MS = 6000;
const SUMMARY_TITLES = { done: "runPanel.finished", cancelled: "runPanel.stopped", failed: "runPanel.failed" };

const props = defineProps({ progress: { type: Object, default: null } });
const collapsed = ref(false);
const summary = ref(null);
let summaryTimer = null;

const run = computed(() => state.remote.running);
const stopping = computed(() => run.value?.phase === "stopping");
const title = computed(() => {
  const phase = run.value?.phase || "checking";
  return phase === "checking" ? t("runPanel.title") : t(`phase.${phase}`);
});

const checking = computed(() => {
  const current = run.value?.current || [];
  return current.map((name, index) => ({
    id: run.value.current_ids?.[index] ?? name,
    name,
    stage: run.value.current_stages?.[index] || "",
  }));
});

/* Готовые узлы этого прогона: проверены после его начала и уже не в работе. Свежие сверху. */
const finished = computed(() => {
  const started = Date.parse(run.value?.started_at || "");
  if (Number.isNaN(started)) return [];
  const busy = new Set(run.value.current_ids || []);
  return state.nodes
    .filter((node) => !busy.has(node.id) && Date.parse(node.last_tested_at || "") >= started)
    .sort((a, b) => Date.parse(b.last_tested_at) - Date.parse(a.last_tested_at));
});

const waiting = computed(() => {
  if (!run.value?.total) return 0;
  return Math.max(0, run.value.total - (run.value.done || 0) - checking.value.length);
});

/* Когда прогон закончился, несколько секунд показываем итог, потом панель уходит.
   Следим за самим прогоном, а не за флагом «идёт»: короткая проверка может начаться и закончиться между опросами. */
const lastRunKey = computed(() => {
  const last = state.remote.last_run;
  return last ? `${last.id}:${last.status}` : "";
});

watch(lastRunKey, (key, previous) => {
  const last = state.remote.last_run;
  /* Первое значение — это прогон, который был до открытия страницы: его итог не показываем. */
  if (!previous || !last || last.status === "running") return;
  clearTimeout(summaryTimer);
  summary.value = last;
  summaryTimer = setTimeout(() => { summary.value = null; }, SUMMARY_MS);
});

watch(() => Boolean(run.value), (active) => {
  if (active) summary.value = null;
});

onBeforeUnmount(() => clearTimeout(summaryTimer));
</script>

<template>
  <div
    v-if="run || summary"
    class="fixed inset-x-4 bottom-20 z-40 flex justify-end lg:inset-x-auto lg:right-6 lg:bottom-6"
    role="status"
    aria-live="polite"
  >
    <button
      v-if="run && collapsed"
      type="button"
      class="flex items-center gap-2 rounded-full border bg-popover px-3.5 py-2 text-sm text-popover-foreground shadow-lg hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      :aria-label="t('runPanel.expand')"
      @click="collapsed = false"
    >
      <Loader2Icon class="size-4 animate-spin text-muted-foreground" aria-hidden="true" />
      <span class="tabular">{{ props.progress?.count || title }}</span>
    </button>

    <div v-else class="w-full rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg lg:w-80">
      <template v-if="run">
        <div class="flex items-center justify-between gap-2">
          <p class="flex min-w-0 items-center gap-2 text-sm font-medium">
            <Loader2Icon class="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
            <span class="truncate">{{ title }}</span>
          </p>
          <span class="flex shrink-0 items-center gap-1">
            <span class="text-sm tabular text-muted-foreground">{{ props.progress?.count }}</span>
            <Button variant="ghost" size="icon-sm" :aria-label="t('runPanel.collapse')" @click="collapsed = true">
              <ChevronDownIcon aria-hidden="true" />
            </Button>
          </span>
        </div>
        <Progress v-if="props.progress?.width != null" :model-value="props.progress.width" class="mt-2 h-1.5" />
        <div v-else class="relative mt-2 h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" :aria-label="t('progress.label')">
          <div class="progress-indeterminate absolute inset-y-0 w-1/3 rounded-full bg-primary"></div>
        </div>
        <ul v-if="checking.length || finished.length" class="mt-3 flex max-h-52 flex-col gap-1.5 overflow-y-auto text-sm">
          <li v-for="node in checking" :key="node.id" class="flex items-center justify-between gap-3">
            <span class="flex min-w-0 items-center gap-2">
              <Loader2Icon class="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
              <span class="truncate">{{ node.name }}</span>
            </span>
            <span class="shrink-0 text-xs text-muted-foreground">{{ node.stage ? t(`stage.${node.stage}`) : "" }}</span>
          </li>
          <li v-for="node in finished" :key="node.id" class="flex items-center justify-between gap-3">
            <span class="flex min-w-0 items-center gap-2">
              <StatusIcon :status="nodeDot(node)" />
              <span class="truncate">{{ node.name }}</span>
            </span>
            <span class="shrink-0 text-xs tabular"><SpeedValue :bps="node.download_bps" /></span>
          </li>
        </ul>
        <p v-if="waiting" class="mt-2 text-xs text-muted-foreground">{{ t("runPanel.waiting", { count: waiting }) }}</p>
        <!-- Кнопка остановки живёт здесь: панель видна на любом экране, пока идёт проверка. -->
        <Button variant="outline" size="sm" class="mt-3 w-full" :disabled="stopping" @click="stopRun">
          <SquareIcon aria-hidden="true" />{{ t("action.stop") }}
        </Button>
      </template>

      <div v-else-if="summary" class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-sm font-medium">{{ t(SUMMARY_TITLES[summary.status] || "runPanel.finished") }}</p>
          <p class="text-xs text-muted-foreground">{{ t("history.summary", { ok: summary.ok_count, fail: summary.fail_count }) }}</p>
        </div>
        <Button variant="ghost" size="icon-sm" :aria-label="t('action.close')" @click="summary = null">
          <XIcon aria-hidden="true" />
        </Button>
      </div>
    </div>
  </div>
</template>
