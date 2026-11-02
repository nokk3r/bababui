<script setup>
import { ClockIcon, HistoryIcon, LayoutDashboardIcon, ListChecksIcon, PlayIcon, SettingsIcon, SquareIcon, TriangleAlertIcon } from "@lucide/vue";
import { computed } from "vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Toaster } from "@/components/ui/sonner";
import LoginGate from "./components/LoginGate.vue";
import NodeDialog from "./components/NodeDialog.vue";
import { loginOpen } from "./lib/api.js";
import { formatBytes, formatTime, nextLabel } from "./lib/format.js";
import { t, tMsg } from "./lib/i18n.js";
import { theme } from "./lib/theme.js";
import { setView, startRun, state, stopRun } from "./store.js";
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

const PROJECT_LINKS = {
  app: "https://github.com/nokk3r/bababui",
  xray: "https://github.com/XTLS/Xray-core",
  hysteria: "https://github.com/apernet/hysteria",
  speedtest: "https://github.com/showwin/speedtest-go",
};

const running = computed(() => state.remote.running);

const nextText = computed(() => {
  /* Обратный отсчёт зависит от часов, поэтому пересчитываем его на каждый такт. */
  void state.tick;
  return nextLabel(state.remote);
});

const progress = computed(() => {
  const run = running.value;
  if (!run) return null;
  const total = run.total || 0;
  const done = run.done || 0;
  const width = total ? Math.min(100, Math.round((done / total) * 100)) : (run.phase === "checking" ? 8 : 15);
  const current = (run.current || []).join(", ");
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
  return messages.join(" ");
});

const versionLinks = computed(() => {
  const versions = state.remote.versions || {};
  return [
    [versions.app && `bababui ${versions.app}`, PROJECT_LINKS.app],
    [versions.xray?.text, PROJECT_LINKS.xray],
    [versions.hysteria?.text, PROJECT_LINKS.hysteria],
    [versions.speedtest?.text, PROJECT_LINKS.speedtest],
  ].filter(([text]) => text).map(([text, url]) => ({ text: tMsg(text), url }));
});

const quota = computed(() => {
  const info = state.remote.userinfo;
  if (info && info.total > 0) {
    const used = (info.upload || 0) + (info.download || 0);
    return t("subscription.traffic", { used: formatBytes(used), total: formatBytes(info.total) });
  }
  if (info && info.expire > 0) {
    return t("subscription.until", { date: formatTime(new Date(info.expire * 1000).toISOString()) });
  }
  return "";
});

const refreshed = computed(() => (
  state.remote.last_refresh_at ? t("subscription.lastRefresh", { time: formatTime(state.remote.last_refresh_at) }) : ""
));
</script>

<template>
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
        <p class="mt-3 hidden text-xs/relaxed text-muted-foreground lg:block">
          <a
            v-for="link in versionLinks"
            :key="link.url"
            class="block rounded-sm hover:text-foreground hover:underline"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
          >{{ link.text }}</a>
        </p>
      </div>
    </aside>

    <div class="flex min-w-0 flex-col gap-4 p-4 pb-24 lg:min-h-dvh lg:p-7">
      <header class="flex items-center justify-between gap-3">
        <h1 class="min-w-0 text-2xl font-semibold tracking-tight lg:text-3xl">{{ t(PAGE_TITLES[state.view]) }}</h1>
        <Button v-if="!running" size="lg" @click="startRun({})">
          <PlayIcon aria-hidden="true" />{{ t("action.checkNow") }}
        </Button>
        <Button v-else size="lg" variant="destructive" @click="stopRun">
          <SquareIcon aria-hidden="true" />{{ t("action.stop") }}
        </Button>
      </header>

      <Alert v-if="banner" class="border-warning/40 bg-warning/10 text-warning">
        <TriangleAlertIcon aria-hidden="true" />
        <AlertDescription class="text-foreground">{{ banner }}</AlertDescription>
      </Alert>

      <div v-if="progress" class="flex flex-col gap-1.5" aria-live="polite">
        <div class="flex justify-between gap-3 text-sm">
          <span class="min-w-0 truncate">{{ progress.label }}</span>
          <span class="shrink-0 tabular text-muted-foreground">{{ progress.count }}</span>
        </div>
        <Progress :model-value="progress.width" class="h-1.5" />
      </div>

      <OverviewView :hidden="state.view !== 'overview'" />
      <SubscriptionView :hidden="state.view !== 'subscription'" />
      <HistoryView :hidden="state.view !== 'history'" />
      <SettingsView :hidden="state.view !== 'settings'" />

      <footer class="mt-auto flex flex-wrap gap-x-4 gap-y-1 pt-2 text-sm text-muted-foreground" :hidden="state.view !== 'subscription'">
        <span>{{ refreshed }}</span>
        <span>{{ quota }}</span>
      </footer>
    </div>
  </div>

  <NodeDialog />
  <Toaster position="top-center" :theme="theme.dark ? 'dark' : 'light'" />
</template>
