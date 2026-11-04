<script setup>
import { computed } from "vue";
import { resultDot } from "../lib/format.js";
import { RECENT_CHECKS } from "../store.js";

/* Полоска последних проверок: столбик — одна проверка, цвет — её итог, высота — загрузка относительно лучшего замера.
   Столбики идут в flex-wrap справа налево (новые справа), всё, что не влезло в первую строку, переносится вниз
   и срезается overflow. Поэтому min-content полоски — MIN_BARS столбиков, а max-content — все RECENT_CHECKS:
   в таблице с auto-раскладкой колонка сжимается до минимума, если места не хватает, и растёт до максимума,
   если хватает, а столбиков показывается ровно столько, сколько влезло целиком. */
const BAR = 6;
const GAP = 3;
const MIN_BARS = 6;
const MIN_WIDTH = MIN_BARS * (BAR + GAP) - GAP;
const COLORS = { ok: "bg-success", warn: "bg-warning", bad: "bg-destructive" };
/* Без замера загрузки высота говорит только об итоге: сбой ниже, чтобы полоска читалась и без цвета. */
const FALLBACK_HEIGHT = { ok: 1, warn: 0.5, bad: 0.25 };
const MIN_HEIGHT = 0.3;

const props = defineProps({ rows: { type: Array, required: true } });

/* Новые первыми: в flex-row-reverse первый элемент стоит справа и переносится вниз последним. */
const bars = computed(() => {
  const recent = props.rows.slice(-RECENT_CHECKS);
  const best = Math.max(0, ...recent.map((row) => row.download_bps ?? 0));
  const checks = recent.map((row) => {
    const status = resultDot(row.ok, row.alive);
    const height = best && row.download_bps != null
      ? Math.max(MIN_HEIGHT, row.download_bps / best)
      : FALLBACK_HEIGHT[status];
    return { key: row.tested_at, color: COLORS[status], height };
  });
  const empty = Array.from({ length: RECENT_CHECKS - checks.length }, (_, index) => ({ key: `empty-${index}`, color: "bg-muted", height: 1 }));
  return [...empty, ...checks].reverse();
});
</script>

<template>
  <div
    class="flex h-7 flex-row-reverse flex-wrap gap-x-[3px] overflow-hidden"
    :style="{ minWidth: `${MIN_WIDTH}px` }"
    aria-hidden="true"
  >
    <!-- Слот на всю высоту, чтобы каждая строка переноса была ровно h-7 и лишние строки целиком уходили под overflow. -->
    <span v-for="bar in bars" :key="bar.key" class="flex h-full w-1.5 shrink-0 items-end">
      <i class="w-full rounded-[2px]" :class="bar.color" :style="{ height: `${Math.round(bar.height * 100)}%` }"></i>
    </span>
  </div>
</template>
