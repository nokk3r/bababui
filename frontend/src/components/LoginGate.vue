<script setup>
import { ref } from "vue";
import { api, loginOpen } from "../lib/api.js";
import { t } from "../lib/i18n.js";
import { reloadAll } from "../store.js";
import LangSelect from "./LangSelect.vue";

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
  <div class="gate">
    <form class="panel gate-card" @submit.prevent="submit">
      <p class="eyebrow">bababui</p>
      <h1>{{ t("login.title") }}</h1>
      <label for="password">{{ t("login.password") }}</label>
      <input id="password" v-model="password" type="password" autocomplete="current-password" required>
      <p v-if="error" class="form-error">{{ error }}</p>
      <button type="submit" class="primary">{{ t("login.submit") }}</button>
      <LangSelect :aria-label="t('settings.general.language')" />
    </form>
  </div>
</template>
