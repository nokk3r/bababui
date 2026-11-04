<script setup>
import { InfoIcon } from "@lucide/vue";
import { computed, reactive, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import OptionSelect from "../components/OptionSelect.vue";
import SwitchField from "../components/SwitchField.vue";
import { api } from "../lib/api.js";
import { formatBytes } from "../lib/format.js";
import { changeLang, i18n, LANGUAGES, t } from "../lib/i18n.js";
import { setTheme, theme, THEMES } from "../lib/theme.js";
import { setSpeedUnit, SPEED_UNITS, units } from "../lib/units.js";
import { pollSoon, reportError, state, toast } from "../store.js";

const PANES = [
  ["general", "settings.general.title"],
  ["check", "settings.check.title"],
];

const languageOptions = Object.entries(LANGUAGES);
const themeOptions = computed(() => THEMES.map((mode) => [mode, t(`theme.${mode}`)]));
const unitOptions = computed(() => Object.keys(SPEED_UNITS).map((unit) => [unit, t(`speedUnit.${unit}`)]));

/* Сколько сейчас хранится истории: перечитывается при каждом открытии настроек,
   потому что история растёт с каждой проверкой и чистится сроком хранения. */
const stats = ref(null);

async function loadStats() {
  try {
    stats.value = await api("/api/history/stats");
  } catch {
    /* без цифры поле срока хранения всё равно работает */
  }
}

watch(() => state.view, (view) => {
  if (view === "settings") loadStats();
}, { immediate: true });

/* Важно одно — сколько места занято: подпись короткая, число выделено. */
const historySize = computed(() => {
  const value = stats.value;
  if (!value) return null;
  if (!value.results) return { label: t("settings.general.historyEmpty"), size: "" };
  return {
    label: t(value.whole_database ? "settings.general.databaseTakes" : "settings.general.historyTakes"),
    size: formatBytes(value.bytes),
  };
});

const form = reactive({
  tls_insecure_if_no_sni: false,
  concurrency: "",
  retention_days: "",
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

async function save() {
  try {
    const saved = await api("/api/settings", {
      method: "PUT",
      json: {
        ...form,
        concurrency: Number(form.concurrency),
        retention_days: Number(form.retention_days),
      },
    });
    fill(saved);
    state.settings = saved;
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
              <Input id="retention_days" v-model="form.retention_days" type="number" min="1" max="3650" step="1" aria-describedby="history-size" />
              <p v-if="historySize" id="history-size" class="text-sm text-muted-foreground">
                {{ historySize.label }}<strong v-if="historySize.size" class="ml-1 font-medium text-foreground tabular">{{ historySize.size }}</strong>
              </p>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="check" class="mt-4 flex flex-col gap-4">
          <h2 class="text-base font-semibold">{{ t("settings.check.whatToMeasure") }}</h2>
          <div class="divide-y">
            <SwitchField v-model="form.measure_download" :label="t('settings.check.measureDownload')" />
            <SwitchField v-model="form.measure_upload" :label="t('settings.check.measureUpload')" />
            <SwitchField
              v-model="form.tls_insecure_if_no_sni"
              :label="t('settings.check.insecureNoSni')"
              :hint="t('settings.check.insecureNoSniHint')"
            />
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
