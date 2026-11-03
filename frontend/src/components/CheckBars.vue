<script setup>
import { useElementSize } from "@vueuse/core";
import { computed, ref } from "vue";
import { resultDot } from "../lib/format.js";
import { RECENT_CHECKS } from "../store.js";

/* Полоска последних проверок: столбик — одна проверка, цвет — её итог, высота — загрузка относительно лучшего замера.
   Столбиков столько, сколько помещается по ширине, но не больше RECENT_CHECKS, новые справа. */
const BAR = 6;
const GAP = 3;
const MIN_BARS = 6;
const COLORS = { ok: "bg-success", warn: "bg-warning", bad: "bg-destructive" };
/* Без замера загрузки высота говорит только об итоге: сбой ниже, чтобы полоска читалась и без цвета. */
const FALLBACK_HEIGHT = { ok: 1, warn: 0.5, bad: 0.25 };
const MIN_HEIGHT = 0.3;

const props = defineProps({ rows: { type: Array, required: true } });
const strip = ref(null);
const { width } = useElementSize(strip);

const slots = computed(() => Math.min(RECENT_CHECKS, Math.max(MIN_BARS, Math.floor((width.value + GAP) / (BAR + GAP)))));

const bars = computed(() => {
  const recent = props.rows.slice(-slots.value);
  const best = Math.max(0, ...recent.map((row) => row.download_bps ?? 0));
  const checks = recent.map((row) => {
    const status = resultDot(row.ok, row.alive);
    const height = best && row.download_bps != null
      ? Math.max(MIN_HEIGHT, row.download_bps / best)
      : FALLBACK_HEIGHT[status];
    return { key: row.tested_at, color: COLORS[status], height };
  });
  const empty = Array.from({ length: slots.value - checks.length }, (_, index) => ({ key: `empty-${index}`, color: "bg-muted", height: 1 }));
  return [...empty, ...checks];
});
</script>

<template>
  <div ref="strip" class="flex h-7 items-end justify-end gap-[3px] overflow-hidden" aria-hidden="true">
    <i
      v-for="bar in bars"
      :key="bar.key"
      class="w-1.5 shrink-0 rounded-[2px]"
      :class="bar.color"
      :style="{ height: `${Math.round(bar.height * 100)}%` }"
    ></i>
  </div>
</template>
