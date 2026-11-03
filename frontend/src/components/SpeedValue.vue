<script setup>
import { computed } from "vue";
import { formatSpeed, speedUnit } from "../lib/format.js";
import { t } from "../lib/i18n.js";

const UNIT_SIZE = {
  sm: "ml-1 text-[0.72em]",
  lg: "ml-1.5 text-sm tracking-normal",
};

const props = defineProps({
  bps: { type: Number, default: null },
  size: { type: String, default: "sm" },
  unit: { type: Boolean, default: true },
});
const value = computed(() => formatSpeed(props.bps));
</script>

<template>
  {{ value }}<small v-if="unit && value !== '—'" class="font-normal text-muted-foreground" :class="UNIT_SIZE[size]">{{ t(speedUnit()) }}</small>
</template>
