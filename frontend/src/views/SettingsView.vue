<script setup>
import { computed, reactive, ref, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import LangSelect from "../components/LangSelect.vue";
import SwitchField from "../components/SwitchField.vue";
import ThemeSelect from "../components/ThemeSelect.vue";
import { api } from "../lib/api.js";
import { t } from "../lib/i18n.js";
import { pollSoon, reportError, state, toast } from "../store.js";

const PANES = [
  ["general", "settings.general.title"],
  ["subscription", "settings.subscription.title"],
  ["schedule", "settings.schedule.title"],
  ["check", "settings.check.title"],
];

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
          <div class="grid gap-4 sm:grid-cols-2">
            <div class="flex flex-col gap-2">
              <Label for="language">{{ t("settings.general.language") }}</Label>
              <LangSelect id="language" />
            </div>
            <div class="flex flex-col gap-2">
              <Label for="theme">{{ t("settings.general.theme") }}</Label>
              <ThemeSelect id="theme" />
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
            <Label for="interval_minutes">{{ t("settings.schedule.interval") }}</Label>
            <Input id="interval_minutes" v-model="form.interval_minutes" type="number" min="1" max="1440" step="1" class="h-9" :disabled="!form.scheduler_enabled" />
          </div>
          <div class="flex flex-col gap-2">
            <Label for="concurrency">{{ t("settings.schedule.concurrency") }}</Label>
            <Input id="concurrency" v-model="form.concurrency" type="number" min="1" max="4" step="1" class="h-9" aria-describedby="concurrency-hint" />
            <p id="concurrency-hint" class="text-sm text-muted-foreground">{{ t("settings.schedule.concurrencyHint") }}</p>
          </div>
          <div class="flex flex-col gap-2">
            <Label for="retention_days">{{ t("settings.schedule.retention") }}</Label>
            <Input id="retention_days" v-model="form.retention_days" type="number" min="1" max="3650" step="1" class="h-9" />
          </div>
          <p class="rounded-lg border bg-muted px-3 py-2 text-sm text-muted-foreground">{{ estimate }}</p>
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
