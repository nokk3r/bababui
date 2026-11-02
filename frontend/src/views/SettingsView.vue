<script setup>
import { computed, reactive, ref, watch } from "vue";
import LangSelect from "../components/LangSelect.vue";
import { api } from "../lib/api.js";
import { t } from "../lib/i18n.js";
import { pollSoon, reportError, state, toast } from "../store.js";

const PANES = [
  ["general", "settings.general.title"],
  ["subscription", "settings.subscription.title"],
  ["schedule", "settings.schedule.title"],
  ["check", "settings.check.title"],
];

const pane = ref("general");
const dirty = ref(false);
const form = reactive({
  subscription_url: "",
  subscription_insecure: false,
  refresh_before_run: false,
  tls_insecure_if_no_sni: false,
  interval_minutes: "",
  concurrency: "",
  retention_days: "",
  scheduler_enabled: false,
  measure_download: false,
  measure_upload: false,
});

watch(() => state.settings, (settings) => {
  if (!settings || dirty.value) return;
  for (const key of Object.keys(form)) {
    form[key] = typeof form[key] === "boolean" ? Boolean(settings[key]) : settings[key] ?? "";
  }
});

const estimate = computed(() => {
  const enabled = state.nodes.filter((node) => node.active && node.supported && node.enabled).length;
  if (!enabled) return t("estimate.noNodes");
  const parts = [t("estimate.latency")];
  if (form.measure_download) parts.push(t("estimate.download"));
  if (form.measure_upload) parts.push(t("estimate.upload"));
  return t("estimate.measuring", { parts: parts.join(", ") });
});

function touched(event) {
  if (event.target.matches("[data-lang-select]")) return;
  dirty.value = true;
}

async function save() {
  try {
    const saved = await api("/api/settings", {
      method: "PUT",
      json: {
        ...form,
        subscription_url: String(form.subscription_url).trim(),
        interval_minutes: Number(form.interval_minutes),
        concurrency: Number(form.concurrency),
        retention_days: Number(form.retention_days),
      },
    });
    dirty.value = false;
    state.settings = saved;
    state.remote.scheduler_enabled = saved.scheduler_enabled;
    state.remote.interval_minutes = saved.interval_minutes;
    pollSoon();
    toast(t("toast.settingsSaved"));
  } catch (error) {
    reportError(error);
  }
}
</script>

<template>
  <section>
    <form class="settings" @input="touched" @submit.prevent="save">
      <nav class="settings-nav" :aria-label="t('settings.sections')">
        <button
          v-for="[name, label] in PANES"
          :key="name"
          type="button"
          :class="{ active: pane === name }"
          @click="pane = name"
        >{{ t(label) }}</button>
      </nav>

      <div class="settings-main">
        <section class="settings-pane" :hidden="pane !== 'general'">
          <h2>{{ t("settings.general.title") }}</h2>
          <p class="settings-lead">{{ t("settings.general.lead") }}</p>
          <label for="language">{{ t("settings.general.language") }}</label>
          <LangSelect id="language" />
        </section>

        <section class="settings-pane" :hidden="pane !== 'subscription'">
          <h2>{{ t("settings.subscription.title") }}</h2>
          <p class="settings-lead">{{ t("settings.subscription.lead") }}</p>
          <label for="subscription_url">{{ t("settings.subscription.links") }}</label>
          <textarea id="subscription_url" v-model="form.subscription_url" rows="5" spellcheck="false"></textarea>
          <label class="check"><input v-model="form.subscription_insecure" type="checkbox"> <span>{{ t("settings.subscription.insecure") }}</span></label>
          <label class="check"><input v-model="form.refresh_before_run" type="checkbox"> <span>{{ t("settings.subscription.refreshBeforeRun") }}</span></label>
          <label class="check"><input v-model="form.tls_insecure_if_no_sni" type="checkbox"> <span>{{ t("settings.subscription.insecureNoSni") }}</span></label>
          <button type="submit" class="primary">{{ t("action.save") }}</button>
        </section>

        <section
          class="settings-pane group"
          :class="{ 'is-off': !form.scheduler_enabled }"
          :hidden="pane !== 'schedule'"
        >
          <h2>{{ t("settings.schedule.title") }}</h2>
          <p class="settings-lead">{{ t("settings.schedule.lead") }}</p>
          <label>
            <span>{{ t("settings.schedule.interval") }}</span>
            <input v-model="form.interval_minutes" type="number" min="1" max="1440" step="1" :disabled="!form.scheduler_enabled">
          </label>
          <div class="field">
            <span class="label-row">
              <label for="concurrency">{{ t("settings.schedule.concurrency") }}</label>
              <span class="hint" tabindex="0">
                <span class="hint-mark" aria-hidden="true">?</span>
                <span class="hint-bubble" role="tooltip">{{ t("settings.schedule.concurrencyHint") }}</span>
              </span>
            </span>
            <input id="concurrency" v-model="form.concurrency" type="number" min="1" max="4" step="1" :disabled="!form.scheduler_enabled">
          </div>
          <label>
            <span>{{ t("settings.schedule.retention") }}</span>
            <input v-model="form.retention_days" type="number" min="1" max="3650" step="1" :disabled="!form.scheduler_enabled">
          </label>
          <label class="check"><input v-model="form.scheduler_enabled" type="checkbox"> <span>{{ t("settings.schedule.enabled") }}</span></label>
          <p class="estimate">{{ estimate }}</p>
          <button type="submit" class="primary">{{ t("action.save") }}</button>
        </section>

        <section class="settings-pane" :hidden="pane !== 'check'">
          <h2>{{ t("settings.check.title") }}</h2>
          <p class="settings-lead">{{ t("settings.check.lead") }}</p>
          <div class="group">
            <h3>{{ t("settings.check.whatToMeasure") }}</h3>
            <p class="card-note">{{ t("settings.check.note") }}</p>
            <label class="check"><input v-model="form.measure_download" type="checkbox"> <span>{{ t("settings.check.measureDownload") }}</span></label>
            <label class="check"><input v-model="form.measure_upload" type="checkbox"> <span>{{ t("settings.check.measureUpload") }}</span></label>
          </div>
          <p class="estimate">{{ estimate }}</p>
          <button type="submit" class="primary">{{ t("action.save") }}</button>
        </section>
      </div>
    </form>
  </section>
</template>
