<script setup>
import StatusIcon from "./StatusIcon.vue";

defineProps({
  dot: { type: String, required: true },
  name: { type: String, required: true },
  sub: { type: String, default: "" },
  interactive: { type: Boolean, default: false },
});
defineEmits(["open"]);
</script>

<template>
  <div class="flex min-w-0 items-start gap-2">
    <StatusIcon :status="dot" class="mt-0.5" />
    <div class="min-w-0">
      <button
        v-if="interactive"
        type="button"
        class="block max-w-full truncate rounded-sm text-left font-medium hover:underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        @click="$emit('open')"
      >{{ name }}</button>
      <b v-else class="block truncate font-medium">{{ name }}</b>
      <span class="block min-h-4 truncate text-xs text-muted-foreground">{{ sub }}</span>
    </div>
  </div>
</template>
