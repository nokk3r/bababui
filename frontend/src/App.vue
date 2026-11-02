<script setup>
import { computed } from "vue";
import LoginGate from "./components/LoginGate.vue";
import NodeDialog from "./components/NodeDialog.vue";
import ToastStack from "./components/ToastStack.vue";
import { loginOpen } from "./lib/api.js";
import { formatBytes, formatTime, nextLabel } from "./lib/format.js";
import { t, tMsg } from "./lib/i18n.js";
import { setView, startRun, state, stopRun } from "./store.js";
import HistoryView from "./views/HistoryView.vue";
import OverviewView from "./views/OverviewView.vue";
import SettingsView from "./views/SettingsView.vue";
import SubscriptionView from "./views/SubscriptionView.vue";

const NAV = [
  ["overview", "nav.overview"],
  ["subscription", "nav.subscription"],
  ["history", "nav.history"],
  ["settings", "nav.settings"],
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
    [`bababui ${versions.app || "0.2.0"}`, PROJECT_LINKS.app],
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

  <div class="shell" :hidden="loginOpen">
    <aside class="nav">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <div>
          <strong>bababui</strong>
          <p>{{ t("app.tagline") }}</p>
        </div>
      </div>
      <nav>
        <button
          v-for="[view, label] in NAV"
          :key="view"
          type="button"
          :class="{ active: state.view === view }"
          @click="setView(view)"
        >{{ t(label) }}</button>
      </nav>
      <div class="nav-foot">
        <p class="next-label">{{ t("nav.nextCheck") }}</p>
        <p class="next-run">{{ nextText }}</p>
        <p class="versions">
          <a
            v-for="link in versionLinks"
            :key="link.url"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
          >{{ link.text }}</a>
        </p>
      </div>
    </aside>

    <div class="workspace">
      <header class="top">
        <div>
          <h1>{{ t(PAGE_TITLES[state.view]) }}</h1>
        </div>
        <div class="top-actions">
          <button v-if="!running" type="button" class="primary" @click="startRun({})">{{ t("action.checkNow") }}</button>
          <button v-else type="button" class="danger" @click="stopRun">{{ t("action.stop") }}</button>
        </div>
      </header>

      <div class="banner" :hidden="!banner">{{ banner }}</div>
      <div v-if="progress" class="progress">
        <div class="progress-meta">
          <span>{{ progress.label }}</span>
          <span>{{ progress.count }}</span>
        </div>
        <div class="progress-track"><div id="progress-bar" :style="{ width: `${progress.width}%` }"></div></div>
      </div>

      <OverviewView :hidden="state.view !== 'overview'" />
      <SubscriptionView :hidden="state.view !== 'subscription'" />
      <HistoryView :hidden="state.view !== 'history'" />
      <SettingsView :hidden="state.view !== 'settings'" />

      <footer class="footnote" :hidden="state.view !== 'subscription'">
        <span>{{ refreshed }}</span>
        <span>{{ quota }}</span>
      </footer>
    </div>
  </div>

  <NodeDialog />
  <ToastStack />
</template>
