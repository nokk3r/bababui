<script setup>
import { useResizeObserver } from "@vueuse/core";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { formatTime } from "../lib/format.js";
import { i18n, t } from "../lib/i18n.js";
import { theme } from "../lib/theme.js";

const HEIGHT = 240;
/* Точки между разрывами иначе не видны: у uPlot линия из одного замера пуста. */
const MAX_DOTTED_ROWS = 120;

const props = defineProps({ rows: { type: Array, required: true } });
const box = ref(null);
let plot = null;

const rows = computed(() => props.rows.filter((row) => !Number.isNaN(Date.parse(row.tested_at))));
const hasFailures = computed(() => rows.value.some((row) => !row.ok));

function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function toMbps(bytes) {
  return bytes == null ? null : (bytes * 8) / 1e6;
}

function epoch(row) {
  return Date.parse(row.tested_at) / 1000;
}

function axisTime(seconds, wide) {
  const options = wide ? { day: "2-digit", month: "2-digit" } : { hour: "2-digit", minute: "2-digit" };
  return new Intl.DateTimeFormat(i18n.lang, options).format(new Date(seconds * 1000));
}

/* На длинном отрезке несколько меток попадают на один день: дату пишем только у первой. */
function axisLabels(ticks, wide) {
  const labels = ticks.map((tick) => axisTime(tick, wide));
  return labels.map((label, index) => (label === labels[index - 1] ? "" : label));
}

function legendValue(unit) {
  return (self, value) => (value == null ? "—" : `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${t(unit)}`);
}

function zeroBased(self, min, max) {
  return [0, Math.max(1, (max || 0) * 1.1)];
}

function markFailures(self) {
  const { ctx, bbox } = self;
  ctx.save();
  ctx.fillStyle = cssColor("--destructive");
  ctx.globalAlpha = 0.28;
  rows.value.forEach((row, index) => {
    if (row.ok) return;
    const x = self.valToPos(self.data[0][index], "x", true);
    ctx.fillRect(Math.round(x - uPlot.pxRatio), bbox.top, 2 * uPlot.pxRatio, bbox.height);
  });
  ctx.restore();
}

function line(label, scale, color, unit) {
  return {
    label,
    scale,
    stroke: color,
    width: 2,
    value: legendValue(unit),
    points: { show: rows.value.length <= MAX_DOTTED_ROWS, size: 6, fill: color, stroke: color },
  };
}

function axis(color, gridColor, extra) {
  return {
    stroke: color,
    font: "11px 'Inter Variable', sans-serif",
    labelFont: "11px 'Inter Variable', sans-serif",
    grid: { stroke: gridColor, width: 1 },
    ticks: { show: false },
    ...extra,
  };
}

function draw() {
  plot?.destroy();
  plot = null;
  if (!box.value || !rows.value.length) return;
  const muted = cssColor("--muted-foreground");
  const grid = cssColor("--border");
  const times = rows.value.map(epoch);
  const span = times[times.length - 1] - times[0];
  plot = new uPlot({
    width: box.value.clientWidth,
    height: HEIGHT,
    cursor: { drag: { x: false, y: false } },
    scales: {
      x: { time: true },
      mbps: { range: zeroBased },
      ms: { range: zeroBased },
    },
    axes: [
      axis(muted, grid, { values: (self, ticks) => axisLabels(ticks, span > 2 * 86400) }),
      axis(muted, grid, { scale: "mbps", label: t("unit.mbps"), labelSize: 16, size: 44 }),
      axis(muted, grid, { scale: "ms", side: 1, label: t("unit.ms"), labelSize: 16, size: 44, grid: { show: false } }),
    ],
    series: [
      { label: t("column.time"), value: (self, value) => (value == null ? "—" : formatTime(new Date(value * 1000).toISOString())) },
      line(t("dialog.download"), "mbps", cssColor("--chart-download"), "unit.mbps"),
      line(t("dialog.upload"), "mbps", cssColor("--chart-upload"), "unit.mbps"),
      line(t("dialog.latency"), "ms", cssColor("--chart-latency"), "unit.ms"),
    ],
    hooks: { draw: [markFailures] },
  }, [
    times,
    rows.value.map((row) => toMbps(row.download_bps)),
    rows.value.map((row) => toMbps(row.upload_bps)),
    rows.value.map((row) => row.latency_ms ?? null),
  ], box.value);
}

useResizeObserver(box, ([entry]) => {
  if (plot && entry.contentRect.width) plot.setSize({ width: entry.contentRect.width, height: HEIGHT });
});

onMounted(draw);
watch(() => [rows.value, i18n.lang, theme.dark], draw, { flush: "post" });
onBeforeUnmount(() => plot?.destroy());
</script>

<template>
  <p v-if="!rows.length" class="py-8 text-center text-muted-foreground">{{ t("chart.noMeasurements") }}</p>
  <figure v-else class="m-0 min-w-0">
    <div ref="box" role="img" :aria-label="t('chart.label')"></div>
    <figcaption v-if="hasFailures" class="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
      <i class="h-3 w-0.5 bg-destructive" aria-hidden="true"></i>{{ t("chart.failed") }}
    </figcaption>
  </figure>
</template>
