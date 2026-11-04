<script setup>
import { ClockIcon, HistoryIcon, LayoutDashboardIcon, ListChecksIcon, SettingsIcon, TriangleAlertIcon } from "@lucide/vue";
import { useIntervalFn } from "@vueuse/core";
import { ConfigProvider } from "reka-ui";
import { computed, ref, watch } from "vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import Hint from "./components/Hint.vue";
import LoginGate from "./components/LoginGate.vue";
import NodeDialog from "./components/NodeDialog.vue";
import SourceDialog from "./components/SourceDialog.vue";
import RunPanel from "./components/RunPanel.vue";
import { loginOpen } from "./lib/api.js";
import { cleanError, nextLabel } from "./lib/format.js";
import { t, tMsg } from "./lib/i18n.js";
import { nodeFraction, nodePlan } from "./lib/progress.js";
import { theme } from "./lib/theme.js";
import { setView, state } from "./store.js";
import HistoryView from "./views/HistoryView.vue";
import OverviewView from "./views/OverviewView.vue";
import SettingsView from "./views/SettingsView.vue";
import SubscriptionView from "./views/SubscriptionView.vue";

const NAV = [
  ["overview", "nav.overview", LayoutDashboardIcon],
  ["subscription", "nav.subscription", ListChecksIcon],
  ["history", "nav.history", HistoryIcon],
  ["settings", "nav.settings", SettingsIcon],
];

const PAGE_TITLES = {
  overview: "page.overview",
  subscription: "nav.subscription",
  history: "nav.history",
  settings: "nav.settings",
};

const PROJECT_URL = "https://github.com/nokk3r/bababui";

const running = computed(() => state.remote.running);

const nextSources = computed(() => {
  const remote = state.remote;
  if (remote.running || !remote.next_run_at) return "";
  return (remote.next_sources || []).map(tMsg).join(", ");
});

const nextClipped = ref(false);

function checkClipped(event) {
  const el = event.currentTarget;
  nextClipped.value = el.scrollWidth > el.clientWidth;
}

const nextText = computed(() => {
  /* Обратный отсчёт зависит от часов, поэтому пересчитываем его на каждый такт. */
  void state.tick;
  return nextLabel(state.remote);
});

/* Между опросами полоса досчитывается по часам браузера, чтобы двигаться плавно. */
const now = ref(Date.now());
let receivedAt = Date.now();
const clock = useIntervalFn(() => { now.value = Date.now(); }, 250, { immediate: false });
watch(() => state.remote, () => { receivedAt = Date.now(); });
watch(() => Boolean(running.value), (active) => (active ? clock.resume() : clock.pause()), { immediate: true });

/* Оценка по времени может перескочить вперёд, но назад полоса не идёт: сброс только на новом прогоне. */
let shown = { runId: null, width: 0 };

function estimateWidth(run, total, done) {
  const stages = run.current_stages || [];
  const started = run.current_stage_started || [];
  const plan = nodePlan(state.settings);
  const sinceReply = Math.max(0, now.value - receivedAt) / 1000;
  let partial = 0;
  stages.forEach((stage, index) => {
    if (started[index] == null || state.remote.server_time == null) return;
    partial += nodeFraction(stage, state.remote.server_time - started[index] + sinceReply, plan);
  });
  const width = Math.min(100, ((done + partial) / total) * 100);
  if (shown.runId !== run.run_id) shown = { runId: run.run_id, width: 0 };
  shown.width = Math.max(shown.width, width);
  return Math.round(shown.width * 10) / 10;
}

const progress = computed(() => {
  const run = running.value;
  if (!run) return null;
  const total = run.total || 0;
  const done = run.done || 0;
  /* Пока бэкенд не знает число узлов, процента нет: полоса бежит без него. */
  const width = total ? estimateWidth(run, total, done) : null;
  const stages = run.current_stages || [];
  const current = (run.current || [])
    .map((name, index) => (stages[index] ? `${name} — ${t(`stage.${stages[index]}`)}` : name))
    .join(", ");
  const phase = t(`phase.${run.phase || "checking"}`);
  return {
    width,
    label: current ? `${phase}: ${current}` : phase,
    count: total ? `${done} / ${total}` : "",
  };
});

const banner = computed(() => {
  const remote = state.remote;
  const versions = remote.versions || {};
  const messages = [];
  if (remote.last_refresh_error) messages.push(tMsg(remote.last_refresh_error));
  if (versions.xray && versions.xray.ok === false) messages.push(`Xray: ${tMsg(versions.xray.text)}`);
  if (versions.hysteria && versions.hysteria.ok === false) messages.push(`Hysteria2: ${tMsg(versions.hysteria.text)}`);
  if (versions.speedtest && versions.speedtest.ok === false) messages.push(`speedtest: ${tMsg(versions.speedtest.text)}`);
  return messages.map(cleanError);
});

/* Версии Xray, Hysteria и speedtest здесь не нужны: если чего-то не хватает, об этом говорит баннер. */
const appVersion = computed(() => state.remote.versions?.app || "");
</script>

<template>
  <!-- Место под полосу прокрутки держит scrollbar-gutter, поэтому Reka не должна добавлять свой отступ. -->
  <ConfigProvider :scroll-body="false">
    <TooltipProvider :delay-duration="200">
      <LoginGate v-if="loginOpen" />

      <div class="min-h-dvh lg:grid lg:grid-cols-[232px_minmax(0,1fr)]" :hidden="loginOpen">
        <aside class="flex items-center justify-between gap-3 border-b bg-sidebar px-4 py-3 lg:sticky lg:top-0 lg:h-dvh lg:flex-col lg:items-stretch lg:justify-start lg:gap-6 lg:border-r lg:border-b-0 lg:py-5">
          <div class="flex min-w-0 items-center gap-3">
            <span class="brand-mark size-9 rounded-lg" aria-hidden="true"></span>
            <div class="min-w-0">
              <strong class="block font-semibold">bababui</strong>
              <p class="truncate text-xs text-muted-foreground">{{ t("app.tagline") }}</p>
            </div>
          </div>

          <nav class="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t bg-sidebar pb-[env(safe-area-inset-bottom)] lg:static lg:flex lg:flex-col lg:gap-1 lg:border-0 lg:bg-transparent lg:pb-0">
            <button
              v-for="[view, label, icon] in NAV"
              :key="view"
              type="button"
              class="flex min-w-0 flex-col items-center gap-1 px-1 py-2 text-xs transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none lg:flex-row lg:gap-2.5 lg:rounded-lg lg:px-3 lg:py-2 lg:text-sm"
              :class="state.view === view ? 'font-medium text-foreground lg:bg-sidebar-accent' : 'text-muted-foreground hover:text-foreground lg:hover:bg-sidebar-accent'"
              :aria-current="state.view === view ? 'page' : undefined"
              @click="setView(view)"
            >
              <component :is="icon" class="size-5 shrink-0 lg:size-4" aria-hidden="true" />
              <span class="max-w-full truncate">{{ t(label) }}</span>
            </button>
          </nav>

          <div class="shrink-0 text-right lg:mt-auto lg:text-center">
            <p class="flex items-center justify-end gap-1 text-xs text-muted-foreground lg:justify-center">
              <ClockIcon class="size-3" aria-hidden="true" />{{ t("nav.nextCheck") }}
            </p>
            <p class="mt-0.5 text-sm font-semibold tabular">{{ nextText }}</p>
            <!-- Чьё расписание наступит первым: у каждого источника оно своё. -->
            <!-- Подсказка нужна, только если названия не влезли и обрезаны многоточием. -->
            <Hint v-if="nextSources" :text="nextSources" :disabled="!nextClipped">
              <p class="max-w-40 truncate text-xs text-muted-foreground lg:mx-auto" @mouseenter="checkClipped">{{ nextSources }}</p>
            </Hint>
            <a
              class="mt-3 hidden items-center justify-center gap-1.5 rounded-sm text-xs text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none lg:flex"
              :href="PROJECT_URL"
              target="_blank"
              rel="noopener noreferrer"
              :aria-label="t('app.github')"
            >
              <!-- Знак GitHub: в наборе Lucide брендовых иконок нет. -->
              <svg viewBox="0 0 16 16" class="size-3.5 shrink-0" fill="currentColor" aria-hidden="true">
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
              </svg>
              <span>bababui {{ appVersion }}</span>
            </a>
          </div>
        </aside>

        <div class="flex min-w-0 flex-col gap-4 p-4 pb-24 lg:min-h-dvh lg:p-7">
          <header class="flex items-center justify-between gap-3">
            <h1 class="min-w-0 text-2xl font-semibold tracking-tight lg:text-3xl">{{ t(PAGE_TITLES[state.view]) }}</h1>
          </header>

          <Alert v-if="banner.length" class="border-warning/40 bg-warning/10 text-warning">
            <TriangleAlertIcon aria-hidden="true" />
            <AlertDescription class="text-foreground">
              <p v-for="message in banner" :key="message">{{ message }}</p>
            </AlertDescription>
          </Alert>

          <OverviewView :hidden="state.view !== 'overview'" />
          <SubscriptionView :hidden="state.view !== 'subscription'" />
          <HistoryView :hidden="state.view !== 'history'" />
          <SettingsView :hidden="state.view !== 'settings'" />
        </div>
      </div>

      <NodeDialog />
      <SourceDialog />
      <RunPanel :progress="progress" />
      <Toaster position="top-center" :theme="theme.dark ? 'dark' : 'light'" />
    </TooltipProvider>
  </ConfigProvider>
</template>
