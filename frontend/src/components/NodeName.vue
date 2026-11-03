<script setup>
import { Loader2Icon } from "@lucide/vue";
import StatusIcon from "./StatusIcon.vue";

defineProps({
  dot: { type: String, required: true },
  name: { type: String, required: true },
  sub: { type: String, default: "" },
  interactive: { type: Boolean, default: false },
  activity: { type: String, default: "" },
});
defineEmits(["open"]);
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <StatusIcon :status="dot" />
    <div class="min-w-0">
      <button
        v-if="interactive"
        type="button"
        class="block max-w-full truncate rounded-sm text-left font-medium hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        @click.stop="$emit('open')"
      >{{ name }}</button>
      <b v-else class="block truncate font-medium">{{ name }}</b>
      <span v-if="activity" class="flex min-h-4 items-center gap-1 truncate text-xs text-foreground">
        <Loader2Icon class="size-3 shrink-0 animate-spin" aria-hidden="true" />{{ activity }}
      </span>
      <span v-else class="block min-h-4 truncate text-xs text-muted-foreground">{{ sub }}</span>
    </div>
  </div>
</template>
