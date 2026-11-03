<script setup>
import { InfoIcon } from "@lucide/vue";
import { computed, reactive, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import OptionSelect from "../components/OptionSelect.vue";
import SwitchField from "../components/SwitchField.vue";
import { api } from "../lib/api.js";
import { changeLang, i18n, LANGUAGES, t } from "../lib/i18n.js";
import { setTheme, theme, THEMES } from "../lib/theme.js";
import { setSpeedUnit, SPEED_UNITS, units } from "../lib/units.js";
import { pollSoon, reportError, state, toast } from "../store.js";

const PANES = [
  ["general", "settings.general.title"],
  ["subscription", "settings.subscription.title"],
  ["schedule", "settings.schedule.title"],
  ["check", "settings.check.title"],
];

const languageOptions = Object.entries(LANGUAGES);
const themeOptions = computed(() => THEMES.map((mode) => [mode, t(`theme.${mode}`)]));
const unitOptions = computed(() => Object.keys(SPEED_UNITS).map((unit) => [unit, t(`speedUnit.${unit}`)]));
const modeOptions = computed(() => [
  ["interval", t("settings.schedule.modeInterval")],
  ["cron", t("settings.schedule.modeCron")],
]);
/* Cron считается в поясе браузера: «в 9:30» для человека значит его 9:30, а не UTC контейнера. */
const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

const form = reactive({
  subscription_url: "",
  subscription_insecure: false,
  refresh_before_run: false,
  tls_insecure_if_no_sni: false,
  schedule_mode: "interval",
  interval_minutes: "",
  cron_expression: "",
  concurrency: "",
  retention_days: "",
  scheduler_enabled: false,
  measure_download: false,
  measure_upload: false,
});

function fingerprint(values) {
  return JSON.stringify(Object.keys(form).map((key) => String(values[key] ?? "")));
}

const baseline = ref(fingerprint(form));
const dirty = computed(() => fingerprint(form) !== baseline.value);

function fill(settings) {
  for (const key of Object.keys(form)) {
    form[key] = typeof form[key] === "boolean" ? Boolean(settings[key]) : settings[key] ?? "";
  }
  baseline.value = fingerprint(form);
}

watch(() => state.settings, (settings) => {
  if (settings && !dirty.value) fill(settings);
});

const estimate = computed(() => {
  const enabled = state.nodes.filter((node) => node.active && node.supported && node.enabled).length;
  if (!enabled) return t("estimate.noNodes");
  const parts = [t("estimate.latency")];
  if (form.measure_download) parts.push(t("estimate.download"));
  if (form.measure_upload) parts.push(t("estimate.upload"));
  return t("estimate.measuring", { parts: parts.join(", ") });
});

async function save() {
  try {
    const saved = await api("/api/settings", {
      method: "PUT",
      json: {
        ...form,
        subscription_url: String(form.subscription_url).trim(),
        interval_minutes: Number(form.interval_minutes),
        cron_expression: String(form.cron_expression).trim(),
        schedule_timezone: browserZone,
        concurrency: Number(form.concurrency),
        retention_days: Number(form.retention_days),
      },
    });
    fill(saved);
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
    <form class="flex max-w-2xl flex-col gap-4" @submit.prevent="save">
      <Tabs v-model="state.settingsPane">
        <TabsList class="w-full sm:w-fit" :aria-label="t('settings.sections')">
          <TabsTrigger v-for="[name, label] in PANES" :key="name" :value="name">{{ t(label) }}</TabsTrigger>
        </TabsList>

        <TabsContent value="general" class="mt-4 flex flex-col gap-4">
          <p class="text-sm text-muted-foreground">{{ t("settings.general.lead") }}</p>
          <div class="flex flex-col gap-4">
            <div class="flex flex-col gap-2">
              <Label for="language">{{ t("settings.general.language") }}</Label>
              <OptionSelect id="language" :options="languageOptions" :model-value="i18n.lang" @update:model-value="changeLang" />
            </div>
            <div class="flex flex-col gap-2">
              <Label for="theme">{{ t("settings.general.theme") }}</Label>
              <OptionSelect id="theme" :options="themeOptions" :model-value="theme.mode" @update:model-value="setTheme" />
            </div>
            <div class="flex flex-col gap-2">
              <Label for="speed-unit">{{ t("settings.general.speedUnit") }}</Label>
              <OptionSelect id="speed-unit" :options="unitOptions" :model-value="units.speed" @update:model-value="setSpeedUnit" />
            </div>
            <div class="flex flex-col gap-2">
              <Label for="retention_days">{{ t("settings.general.retention") }}</Label>
              <Input id="retention_days" v-model="form.retention_days" type="number" min="1" max="3650" step="1" />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="subscription" class="mt-4 flex flex-col gap-4">
          <p class="text-sm text-muted-foreground">{{ t("settings.subscription.lead") }}</p>
          <div class="flex flex-col gap-2">
            <Label for="subscription_url">{{ t("settings.subscription.links") }}</Label>
            <Textarea id="subscription_url" v-model="form.subscription_url" rows="5" spellcheck="false" class="font-mono text-xs" />
          </div>
          <div class="divide-y">
            <SwitchField v-model="form.subscription_insecure" :label="t('settings.subscription.insecure')" />
            <SwitchField v-model="form.refresh_before_run" :label="t('settings.subscription.refreshBeforeRun')" />
            <SwitchField v-model="form.tls_insecure_if_no_sni" :label="t('settings.subscription.insecureNoSni')" />
          </div>
        </TabsContent>

        <TabsContent value="schedule" class="mt-4 flex flex-col gap-4">
          <p class="text-sm text-muted-foreground">{{ t("settings.schedule.lead") }}</p>
          <SwitchField v-model="form.scheduler_enabled" :label="t('settings.schedule.enabled')" />
          <div class="flex flex-col gap-2">
            <Label for="schedule_mode">{{ t("settings.schedule.mode") }}</Label>
            <OptionSelect id="schedule_mode" v-model="form.schedule_mode" :options="modeOptions" :disabled="!form.scheduler_enabled" />
          </div>
          <div v-if="form.schedule_mode === 'cron'" class="flex flex-col gap-2">
            <Label for="cron_expression">{{ t("settings.schedule.cron") }}</Label>
            <Input
              id="cron_expression"
              v-model="form.cron_expression"
              class="font-mono"
              spellcheck="false"
              autocomplete="off"
              placeholder="0 */2 * * *"
              aria-describedby="cron-hint"
              :disabled="!form.scheduler_enabled"
            />
            <p id="cron-hint" class="text-sm text-muted-foreground">{{ t("settings.schedule.cronHint", { zone: browserZone }) }}</p>
          </div>
          <div v-else class="flex flex-col gap-2">
            <Label for="interval_minutes">{{ t("settings.schedule.interval") }}</Label>
            <Input id="interval_minutes" v-model="form.interval_minutes" type="number" min="1" max="1440" step="1" :disabled="!form.scheduler_enabled" />
          </div>
        </TabsContent>

        <TabsContent value="check" class="mt-4 flex flex-col gap-4">
          <p class="text-sm text-muted-foreground">{{ t("settings.check.lead") }}</p>
          <div>
            <h2 class="text-base font-semibold">{{ t("settings.check.whatToMeasure") }}</h2>
            <p class="mt-1 text-sm text-muted-foreground">{{ t("settings.check.note") }}</p>
          </div>
          <div class="divide-y">
            <SwitchField v-model="form.measure_download" :label="t('settings.check.measureDownload')" />
            <SwitchField v-model="form.measure_upload" :label="t('settings.check.measureUpload')" />
          </div>
          <div class="flex flex-col gap-2">
            <div class="flex items-center gap-1.5">
              <Label for="concurrency">{{ t("settings.check.concurrency") }}</Label>
              <Tooltip>
                <TooltipTrigger as-child>
                  <button
                    type="button"
                    class="rounded-sm text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                    :aria-label="t('settings.check.concurrencyHint')"
                  >
                    <InfoIcon class="size-4" aria-hidden="true" />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" class="max-w-64 text-sm">{{ t("settings.check.concurrencyHint") }}</TooltipContent>
              </Tooltip>
            </div>
            <Input id="concurrency" v-model="form.concurrency" type="number" min="1" max="4" step="1" />
          </div>
          <p class="rounded-lg border bg-muted px-3 py-2 text-sm text-muted-foreground">{{ estimate }}</p>
        </TabsContent>
      </Tabs>

      <div
        v-if="dirty"
        class="sticky bottom-20 z-30 flex items-center justify-between gap-3 rounded-xl border bg-popover p-3 shadow-md lg:bottom-4"
      >
        <span class="min-w-0 text-sm">{{ t("settings.unsaved") }}</span>
        <span class="flex shrink-0 gap-2">
          <Button type="button" variant="ghost" size="lg" @click="fill(state.settings)">{{ t("action.reset") }}</Button>
          <Button type="submit" size="lg">{{ t("action.save") }}</Button>
        </span>
      </div>
    </form>
  </section>
</template>
