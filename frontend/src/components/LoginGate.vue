<script setup>
import { ref } from "vue";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, loginOpen } from "../lib/api.js";
import { changeLang, i18n, LANGUAGES, t } from "../lib/i18n.js";
import { reloadAll } from "../store.js";
import OptionSelect from "./OptionSelect.vue";

const password = ref("");
const error = ref("");

async function submit() {
  sessionStorage.setItem("token", password.value);
  try {
    await api("/api/state");
    error.value = "";
    loginOpen.value = false;
    await reloadAll();
  } catch (failure) {
    sessionStorage.removeItem("token");
    error.value = failure.unauthorized ? t("login.wrongPassword") : failure.message;
  }
}
</script>

<template>
  <div class="grid min-h-dvh place-items-center bg-sidebar p-6">
    <Card class="w-full max-w-sm px-6 py-6">
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div class="flex items-center gap-3">
          <span class="brand-mark size-9 rounded-lg" aria-hidden="true"></span>
          <div>
            <p class="text-xs text-muted-foreground">bababui</p>
            <h1 class="text-xl font-semibold tracking-tight">{{ t("login.title") }}</h1>
          </div>
        </div>
        <div class="flex flex-col gap-2">
          <Label for="password">{{ t("login.password") }}</Label>
          <Input id="password" v-model="password" type="password" autocomplete="current-password" required />
        </div>
        <p v-if="error" class="text-sm text-destructive" role="alert">{{ error }}</p>
        <Button type="submit" size="lg">{{ t("login.submit") }}</Button>
        <OptionSelect
          :options="Object.entries(LANGUAGES)"
          :model-value="i18n.lang"
          :aria-label="t('settings.general.language')"
          @update:model-value="changeLang"
        />
      </form>
    </Card>
  </div>
</template>
