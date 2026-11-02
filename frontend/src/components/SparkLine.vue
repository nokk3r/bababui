<script setup>
import { computed } from "vue";

const WIDTH = 92;
const HEIGHT = 28;

const props = defineProps({ values: { type: Array, required: true } });

const path = computed(() => {
  const { values } = props;
  const nums = values.filter((value) => value != null);
  if (!nums.length) return "";
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const step = values.length > 1 ? (WIDTH - 4) / (values.length - 1) : 0;
  let result = "";
  values.forEach((value, index) => {
    if (value == null) return;
    const x = 2 + index * step;
    const y = HEIGHT - 3 - ((value - min) / span) * (HEIGHT - 6);
    const command = result && values[index - 1] != null ? "L" : "M";
    result += `${command}${x.toFixed(1)} ${y.toFixed(1)} `;
  });
  return result;
});
</script>

<template>
  <svg
    v-if="path"
    class="spark"
    :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
    :width="WIDTH"
    :height="HEIGHT"
    aria-hidden="true"
  ><path :d="path" /></svg>
  <span v-else class="muted">—</span>
</template>
