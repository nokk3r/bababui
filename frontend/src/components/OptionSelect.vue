<script setup>
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { i18n } from "../lib/i18n.js";

defineOptions({ inheritAttrs: false });
/* Варианты приходят парами [значение, подпись], атрибуты вроде id и aria-label уходят на кнопку списка. */
defineProps({ options: { type: Array, required: true } });
const model = defineModel({ type: String });
</script>

<template>
  <!-- Подпись выбранного пункта запоминается при монтировании, поэтому смена языка собирает список заново. -->
  <Select :key="i18n.lang" v-model="model">
    <SelectTrigger v-bind="$attrs" class="w-full">
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      <SelectItem v-for="[value, label] in options" :key="value" :value="value">{{ label }}</SelectItem>
    </SelectContent>
  </Select>
</template>
