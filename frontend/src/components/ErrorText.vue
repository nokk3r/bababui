<script setup>
import { computed, ref } from "vue";
import { cleanError } from "../lib/format.js";
import { t } from "../lib/i18n.js";

const LIMIT = 140;

const props = defineProps({ text: { type: String, required: true } });
const expanded = ref(false);
const clean = computed(() => cleanError(props.text));
const long = computed(() => clean.value.length > LIMIT);
const shown = computed(() => (long.value && !expanded.value ? `${clean.value.slice(0, LIMIT).trimEnd()}…` : clean.value));
</script>

<template>
  <span class="break-words">
    {{ shown }}
    <button
      v-if="long"
      type="button"
      class="ml-1 rounded-sm text-muted-foreground underline underline-offset-2 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      :aria-expanded="expanded"
      @click.stop="expanded = !expanded"
    >{{ t(expanded ? "error.showLess" : "error.showMore") }}</button>
  </span>
</template>
