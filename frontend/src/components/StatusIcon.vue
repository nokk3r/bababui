<script setup>
import { CircleCheckIcon, CircleDashedIcon, CircleXIcon, TriangleAlertIcon } from "@lucide/vue";
import { computed } from "vue";
import { t } from "../lib/i18n.js";

const STATUS = {
  ok: [CircleCheckIcon, "text-success"],
  warn: [TriangleAlertIcon, "text-warning"],
  bad: [CircleXIcon, "text-destructive"],
  idle: [CircleDashedIcon, "text-muted-foreground"],
};

const props = defineProps({ status: { type: String, required: true } });
const label = computed(() => t(`status.${props.status}`));
</script>

<template>
  <span role="img" class="inline-flex shrink-0" :class="STATUS[status][1]" :aria-label="label" :title="label">
    <component :is="STATUS[status][0]" class="size-4" aria-hidden="true" />
  </span>
</template>
