<script setup>
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { t } from "../lib/i18n.js";
import { setTheme, theme, THEMES } from "../lib/theme.js";

defineOptions({ inheritAttrs: false });
</script>

<template>
  <Select :model-value="theme.mode" @update:model-value="setTheme">
    <SelectTrigger v-bind="$attrs" class="w-full">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="mode in THEMES" :key="mode" :value="mode">{{ t(`theme.${mode}`) }}</SelectItem>
    </SelectContent>
  </Select>
</template>
