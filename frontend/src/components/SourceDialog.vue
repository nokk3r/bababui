<script setup>
import { computed, reactive, ref, useId, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import OptionSelect from "./OptionSelect.vue";
import SwitchField from "./SwitchField.vue";
import { api } from "../lib/api.js";
import { i18n, t } from "../lib/i18n.js";
import { reloadAll, reportError, state, toast } from "../store.js";

/* Создание и правка источника. Подписка — один адрес, который скачивается; группа — свои узлы ссылками.
   После сохранения источник сразу обновляется, чтобы результат был виден в таблице. */
const form = reactive({
  name: "",
  url: "",
  links: "",
  insecure: true,
  schedule_enabled: true,
  schedule_mode: "interval",
  interval: "2",
  unit: "hours",
  cron_expression: "0 */2 * * *",
  refresh_before_run: true,
});
const saving = ref(false);
const ids = { name: useId(), url: useId(), links: useId(), hint: useId(), mode: useId(), interval: useId(), unit: useId(), cron: useId(), cronHint: useId() };
/* Cron считается в поясе браузера: «в 9:30» для человека значит его 9:30, а не UTC контейнера. */
const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

const modeOptions = computed(() => [
  ["interval", t("settings.schedule.modeInterval")],
  ["cron", t("settings.schedule.modeCron")],
]);
const unitOptions = computed(() => [
  ["minutes", t("source.unitMinutes")],
  ["hours", t("source.unitHours")],
]);
const intervalMinutes = computed(() => Math.round(Number(form.interval) * (form.unit === "hours" ? 60 : 1)));

/* Сколько раз в сутки источник будет проверяться: замер скорости через каждый узел расходует трафик. */
const perDay = computed(() => {
  if (!form.schedule_enabled || form.schedule_mode !== "interval" || !(intervalMinutes.value > 0)) return "";
  const runs = new Intl.NumberFormat(i18n.lang, { maximumFractionDigits: 1 }).format(1440 / intervalMinutes.value);
  const source = editing.value;
  if (!source) return t("source.perDay", { runs });
  const nodes = state.nodes.filter((node) => node.sources.includes(source.id) && node.supported && node.enabled).length;
  return t("source.perDayNodes", { runs, nodes });
});

const dialog = computed(() => state.sourceDialog);
const kind = computed(() => dialog.value?.kind || "subscription");
const editing = computed(() => (dialog.value?.id == null ? null : state.sources.find((source) => source.id === dialog.value.id)));
const isGroup = computed(() => kind.value === "group");

const title = computed(() => {
  if (editing.value) return t(isGroup.value ? "source.editGroup" : "source.editSubscription");
  return t(isGroup.value ? "source.newGroup" : "source.newSubscription");
});

/* Форма заполняется только при открытии: после неудачной загрузки диалог переключается на правку
   уже созданного источника, и введённое не должно стираться. */
watch(dialog, (value, previous) => {
  if (!value || previous) return;
  const source = editing.value;
  form.name = source?.name || "";
  form.url = source?.url || "";
  form.links = source?.links || "";
  form.insecure = source ? source.insecure : true;
  form.schedule_enabled = source ? source.schedule_enabled : true;
  form.schedule_mode = source?.schedule_mode || "interval";
  const minutes = source?.interval_minutes || 120;
  form.unit = minutes % 60 === 0 ? "hours" : "minutes";
  form.interval = String(form.unit === "hours" ? minutes / 60 : minutes);
  form.cron_expression = source?.cron_expression || "0 */2 * * *";
  form.refresh_before_run = source ? source.refresh_before_run : true;
});

function close() {
  state.sourceDialog = null;
}

async function save() {
  saving.value = true;
  try {
    const body = {
      kind: kind.value,
      name: form.name,
      url: form.url,
      links: form.links,
      insecure: form.insecure,
      schedule_enabled: form.schedule_enabled,
      schedule_mode: form.schedule_mode,
      interval_minutes: intervalMinutes.value,
      cron_expression: form.cron_expression,
      schedule_timezone: browserZone,
      refresh_before_run: form.refresh_before_run,
    };
    const source = editing.value
      ? await api(`/api/sources/${editing.value.id}`, { method: "PUT", json: body })
      : await api("/api/sources", { method: "POST", json: body });
    /* Новый источник сразу раскрыт: его узлы видны без лишнего клика. */
    if (!editing.value) state.openSources = new Set([...(state.openSources || []), String(source.id)]);
    try {
      const result = await api(`/api/sources/${source.id}/refresh`, { method: "POST" });
      toast(t("toast.sourceSaved", { count: result.count }));
      close();
    } catch (error) {
      /* Источник сохранён, но не загрузился: диалог остаётся открытым, чтобы адрес можно было поправить.
         Повторное сохранение пойдёт правкой уже созданного источника. */
      state.sourceDialog = { kind: kind.value, id: source.id };
      reportError(error);
    }
  } catch (error) {
    reportError(error);
  } finally {
    saving.value = false;
    await reloadAll().catch(() => {});
  }
}
</script>

<template>
  <Dialog :open="Boolean(dialog)" @update:open="(open) => !open && close()">
    <!-- Описания нет: заголовок и подписи полей говорят всё сами. aria-describedby снимает предупреждение Reka. -->
    <DialogContent class="max-h-[calc(100dvh-2rem)] gap-4 overflow-y-auto sm:max-w-xl" :aria-describedby="undefined">
      <DialogHeader>
        <DialogTitle>{{ title }}</DialogTitle>
      </DialogHeader>
      <!-- min-w-0: окно диалога — сетка, и длинная ссылка без переноса иначе раздвинет его по ширине. -->
      <form class="flex min-w-0 flex-col gap-4" @submit.prevent="save">
        <div class="flex flex-col gap-2">
          <Label :for="ids.name">{{ t("source.name") }}</Label>
          <Input
            :id="ids.name"
            v-model="form.name"
            maxlength="80"
            autocomplete="off"
            :placeholder="t(isGroup ? 'source.namePlaceholderGroup' : 'source.namePlaceholderSubscription')"
          />
        </div>
        <template v-if="isGroup">
          <div class="flex flex-col gap-2">
            <Label :for="ids.links">{{ t("source.links") }}</Label>
            <Textarea
              :id="ids.links"
              v-model="form.links"
              rows="6"
              wrap="off"
              spellcheck="false"
              autocomplete="off"
              placeholder="vless://…"
              :aria-describedby="ids.hint"
              class="font-mono text-xs"
            />
            <p :id="ids.hint" class="text-sm text-muted-foreground">{{ t("source.linksHint") }}</p>
          </div>
        </template>
        <template v-else>
          <div class="flex flex-col gap-2">
            <Label :for="ids.url">{{ t("source.url") }}</Label>
            <Input
              :id="ids.url"
              v-model="form.url"
              type="url"
              spellcheck="false"
              autocomplete="off"
              placeholder="https://…"
              class="font-mono text-xs"
            />
          </div>
          <SwitchField v-model="form.insecure" :label="t('subscription.insecure')" />
        </template>

        <fieldset class="flex min-w-0 flex-col gap-4 border-t pt-4">
          <legend class="sr-only">{{ t("source.schedule") }}</legend>
          <h3 class="text-sm font-semibold" aria-hidden="true">{{ t("source.schedule") }}</h3>
          <div class="-my-3 divide-y">
            <SwitchField v-model="form.schedule_enabled" :label="t('source.scheduleEnabled')" />
            <SwitchField v-if="!isGroup" v-model="form.refresh_before_run" :label="t('source.refreshBeforeRun')" />
          </div>
          <template v-if="form.schedule_enabled">
            <div class="flex flex-col gap-2">
              <Label :for="ids.mode">{{ t("settings.schedule.mode") }}</Label>
              <OptionSelect :id="ids.mode" v-model="form.schedule_mode" :options="modeOptions" />
            </div>
            <div v-if="form.schedule_mode === 'cron'" class="flex flex-col gap-2">
              <Label :for="ids.cron">{{ t("settings.schedule.cron") }}</Label>
              <Input
                :id="ids.cron"
                v-model="form.cron_expression"
                class="font-mono"
                spellcheck="false"
                autocomplete="off"
                placeholder="0 */2 * * *"
                :aria-describedby="ids.cronHint"
              />
              <p :id="ids.cronHint" class="text-sm text-muted-foreground">{{ t("settings.schedule.cronHint", { zone: browserZone }) }}</p>
            </div>
            <div v-else class="flex flex-col gap-2">
              <Label :for="ids.interval">{{ t("source.every") }}</Label>
              <div class="flex gap-2">
                <Input :id="ids.interval" v-model="form.interval" type="number" min="1" step="1" class="w-28" />
                <div class="w-40"><OptionSelect v-model="form.unit" :options="unitOptions" :aria-label="t('source.unit')" /></div>
              </div>
              <p v-if="perDay" class="text-sm text-muted-foreground">{{ perDay }}</p>
            </div>
          </template>
        </fieldset>
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="ghost" size="lg" @click="close">{{ t("action.cancel") }}</Button>
          <Button type="submit" size="lg" :disabled="saving">{{ t(isGroup ? "action.save" : "action.saveAndRefresh") }}</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
</template>
