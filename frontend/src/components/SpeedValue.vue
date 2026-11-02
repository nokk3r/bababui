<script setup>
import { computed } from "vue";
import { mbps } from "../lib/format.js";
import { t } from "../lib/i18n.js";

const props = defineProps({ bps: { type: Number, default: null } });
const value = computed(() => mbps(props.bps));
</script>

<template>
  {{ value }}<small v-if="value !== '—'" class="ml-1 text-[0.72em] font-normal text-muted-foreground">{{ t("unit.mbps") }}</small>
</template>
