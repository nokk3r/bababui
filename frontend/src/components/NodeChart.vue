<script setup>
import { useResizeObserver } from "@vueuse/core";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { cleanError, formatMs, formatSpeed, formatTime, speedUnit, toSpeed } from "../lib/format.js";
import { i18n, t, tMsg } from "../lib/i18n.js";
import { theme } from "../lib/theme.js";
import { units } from "../lib/units.js";

const HEIGHT = 240;
/* Точки между разрывами иначе не видны: у uPlot линия из одного замера пуста. */
const MAX_DOTTED_ROWS = 120;
const TIP_GAP = 12;

/* uPlot рисует только линии, а легенду и подсказку рисуем сами, в стиле остального интерфейса. */
const SERIES = [
  { key: "download_bps", label: "dialog.download", color: "--chart-download", scale: "speed" },
  { key: "upload_bps", label: "dialog.upload", color: "--chart-upload", scale: "speed" },
  { key: "latency_ms", label: "dialog.latency", color: "--chart-latency", scale: "ms" },
];

const props = defineProps({ rows: { type: Array, required: true } });
const box = ref(null);
const hover = ref(null);
let plot = null;
let snapped = null;

const rows = computed(() => props.rows.filter((row) => !Number.isNaN(Date.parse(row.tested_at))));
const hasFailures = computed(() => rows.value.some((row) => !row.ok));
/* Без наведения подписи показывают последний замер. */
const current = computed(() => rows.value[hover.value?.idx ?? rows.value.length - 1] || null);

function cssColor(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function epoch(row) {
  return Date.parse(row.tested_at) / 1000;
}

function seriesValue(row, series) {
  if (!row) return "—";
  if (series.scale === "ms") return formatMs(row[series.key]);
  const value = formatSpeed(row[series.key]);
  return value === "—" ? value : `${value} ${t(speedUnit())}`;
}

function failureText(row) {
  const text = cleanError(tMsg(row.error) || t("dialog.error"));
  return text.length > 90 ? `${text.slice(0, 90).trimEnd()}…` : text;
}

function axisTime(seconds, wide) {
  const options = wide ? { day: "2-digit", month: "2-digit" } : { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
  return new Intl.DateTimeFormat(i18n.lang, options).format(new Date(seconds * 1000));
}

/* На длинном отрезке несколько меток попадают на один день: дату пишем только у первой. */
function axisLabels(ticks, wide) {
  const labels = ticks.map((tick) => axisTime(tick, wide));
  return labels.map((label, index) => (label === labels[index - 1] ? "" : label));
}

function zeroBased(self, min, max) {
  return [0, Math.max(1, (max || 0) * 1.1)];
}

/* Сбой — бледная полоса и точка у нижней оси: яркая полоса во всю высоту на краю графика выглядела как его рамка. */
function markFailures(self) {
  const { ctx, bbox } = self;
  const radius = 3.5 * uPlot.pxRatio;
  ctx.save();
  ctx.fillStyle = cssColor("--destructive");
  rows.value.forEach((row, index) => {
    if (row.ok) return;
    const x = self.valToPos(self.data[0][index], "x", true);
    ctx.globalAlpha = 0.1;
    ctx.fillRect(Math.round(x - uPlot.pxRatio), bbox.top, 2 * uPlot.pxRatio, bbox.height);
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(x, bbox.top + bbox.height - radius, radius, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();
}

/* Ближайший замер по времени. Свой поиск, потому что uPlot пропускает замеры без значений, а это как раз сбои. */
function nearestRow(self, left) {
  const value = self.posToVal(left, "x");
  const times = self.data[0];
  let best = 0;
  for (let index = 1; index < times.length; index += 1) {
    if (Math.abs(times[index] - value) < Math.abs(times[best] - value)) best = index;
  }
  return best;
}

/* Линия курсора встаёт на ближайший замер, иначе она висит между точками, а подсказка показывает другой момент. */
function snapToRow(self, left, top) {
  if (left < 0) {
    snapped = null;
    return [left, top];
  }
  snapped = nearestRow(self, left);
  return [self.valToPos(self.data[0][snapped], "x"), top];
}

/* Подсказка стоит справа от курсора, а во второй половине графика уходит влево, чтобы не вылезать за край. */
function trackCursor(self) {
  const { left } = self.cursor;
  if (snapped == null || left == null || left < 0) {
    hover.value = null;
    return;
  }
  hover.value = { idx: snapped, x: self.over.offsetLeft + left, flip: left > self.over.clientWidth / 2 };
}

function line(series, color) {
  return {
    scale: series.scale,
    stroke: color,
    width: 2,
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
  snapped = null;
  hover.value = null;
  if (!box.value || !rows.value.length) return;
  const muted = cssColor("--muted-foreground");
  const grid = cssColor("--border");
  const times = rows.value.map(epoch);
  const span = times[times.length - 1] - times[0];
  plot = new uPlot({
    width: box.value.clientWidth,
    height: HEIGHT,
    legend: { show: false },
    cursor: { y: false, move: snapToRow, drag: { x: false, y: false } },
    scales: {
      x: { time: true },
      speed: { range: zeroBased },
      ms: { range: zeroBased },
    },
    axes: [
      axis(muted, grid, { space: 60, values: (self, ticks) => axisLabels(ticks, span > 2 * 86400) }),
      axis(muted, grid, { scale: "speed", label: t(speedUnit()), labelSize: 16, size: 44 }),
      axis(muted, grid, { scale: "ms", side: 1, label: t("unit.ms"), labelSize: 16, size: 44, grid: { show: false } }),
    ],
    series: [{}, ...SERIES.map((series) => line(series, cssColor(series.color)))],
    hooks: { draw: [markFailures], setCursor: [trackCursor] },
  }, [
    times,
    rows.value.map((row) => toSpeed(row.download_bps)),
    rows.value.map((row) => toSpeed(row.upload_bps)),
    rows.value.map((row) => row.latency_ms ?? null),
  ], box.value);
}

useResizeObserver(box, ([entry]) => {
  if (plot && entry.contentRect.width) plot.setSize({ width: entry.contentRect.width, height: HEIGHT });
});

onMounted(draw);
watch(() => [rows.value, i18n.lang, theme.dark, units.speed], draw, { flush: "post" });
onBeforeUnmount(() => plot?.destroy());
</script>

<template>
  <p v-if="!rows.length" class="py-8 text-center text-muted-foreground">{{ t("chart.noMeasurements") }}</p>
  <figure v-else class="m-0 min-w-0" :aria-label="t('chart.label')">
    <div class="relative">
      <div ref="box"></div>
      <div
        v-if="hover && current"
        class="pointer-events-none absolute top-2 z-10 w-max max-w-64 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md"
        :style="{ left: `${hover.x}px`, transform: hover.flip ? `translateX(calc(-100% - ${TIP_GAP}px))` : `translateX(${TIP_GAP}px)` }"
        aria-hidden="true"
      >
        <p class="mb-1.5 font-medium">{{ formatTime(current.tested_at) }}</p>
        <p v-for="series in SERIES" :key="series.key" class="flex items-center justify-between gap-4 leading-5">
          <span class="flex items-center gap-1.5 text-muted-foreground">
            <i class="h-0.5 w-3 rounded-full" :style="{ background: `var(${series.color})` }"></i>{{ t(series.label) }}
          </span>
          <span class="font-medium tabular">{{ seriesValue(current, series) }}</span>
        </p>
        <p v-if="!current.ok" class="mt-1.5 border-t pt-1.5 break-words text-destructive">{{ failureText(current) }}</p>
      </div>
    </div>
    <figcaption class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      <span class="tabular">{{ current ? formatTime(current.tested_at) : "" }}</span>
      <span v-for="series in SERIES" :key="series.key" class="flex items-center gap-1.5">
        <i class="h-0.5 w-3 rounded-full" :style="{ background: `var(${series.color})` }" aria-hidden="true"></i>
        {{ t(series.label) }}
        <b class="font-medium text-foreground tabular">{{ seriesValue(current, series) }}</b>
      </span>
      <span v-if="hasFailures" class="flex items-center gap-1.5">
        <i class="size-2 rounded-full bg-destructive" aria-hidden="true"></i>{{ t("chart.failed") }}
      </span>
    </figcaption>
  </figure>
</template>
