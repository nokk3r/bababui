<script setup>
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { i18n, LANGUAGES, setLang } from "../lib/i18n.js";

defineOptions({ inheritAttrs: false });

function change(lang) {
  setLang(lang).catch(() => {
    /* остаётся прежний язык */
  });
}
</script>

<template>
  <Select :model-value="i18n.lang" @update:model-value="change">
    <SelectTrigger v-bind="$attrs" class="w-full">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="(name, code) in LANGUAGES" :key="code" :value="code">{{ name }}</SelectItem>
    </SelectContent>
  </Select>
</template>
