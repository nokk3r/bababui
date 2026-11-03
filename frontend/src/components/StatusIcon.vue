<script setup>
import { BanIcon, CircleCheckIcon, CircleDashedIcon, CircleXIcon, TriangleAlertIcon } from "@lucide/vue";
import { computed } from "vue";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { t } from "../lib/i18n.js";

const STATUS = {
  ok: [CircleCheckIcon, "text-success"],
  warn: [TriangleAlertIcon, "text-warning"],
  bad: [CircleXIcon, "text-destructive"],
  idle: [CircleDashedIcon, "text-muted-foreground"],
  unsupported: [BanIcon, "text-muted-foreground"],
};

const props = defineProps({ status: { type: String, required: true } });
const label = computed(() => t(`status.${props.status}`));
</script>

<template>
  <Tooltip>
    <TooltipTrigger as-child>
      <span role="img" class="inline-flex shrink-0" :class="STATUS[status][1]" :aria-label="label">
        <component :is="STATUS[status][0]" class="size-4" aria-hidden="true" />
      </span>
    </TooltipTrigger>
    <TooltipContent side="top" class="text-sm">{{ label }}</TooltipContent>
  </Tooltip>
</template>
