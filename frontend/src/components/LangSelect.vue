<script setup>
import { i18n, LANGUAGES, setLang } from "../lib/i18n.js";

function change(event) {
  setLang(event.target.value).catch(() => {
    event.target.value = i18n.lang;
  });
}
</script>

<template>
  <select class="lang-select" data-lang-select :value="i18n.lang" @change="change">
    <option v-for="(name, code) in LANGUAGES" :key="code" :value="code">{{ name }}</option>
  </select>
</template>
