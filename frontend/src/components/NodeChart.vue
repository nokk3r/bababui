<script setup>
import { onMounted, ref, watch } from "vue";
import { formatTime } from "../lib/format.js";
import { i18n, t } from "../lib/i18n.js";

const props = defineProps({ rows: { type: Array, required: true } });
const canvas = ref(null);

function cssColor(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function strokeSeries(ctx, points, key, color, pad, plotW, plotH, max) {
  const coords = [];
  points.forEach((row, index) => {
    if (row[key] == null) return;
    const x = pad.left + (points.length === 1 ? plotW / 2 : (plotW * index) / (points.length - 1));
    const y = pad.top + plotH - ((row[key] * 8) / 1e6 / max) * plotH;
    coords.push([x, y, index]);
  });
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  coords.forEach(([x, y, index], position) => {
    const previous = coords[position - 1];
    if (!previous || index !== previous[2] + 1) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillStyle = color;
  for (const [x, y] of coords) {
    ctx.beginPath();
    ctx.arc(x, y, 3.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function draw() {
  const el = canvas.value;
  if (!el) return;
  const width = el.clientWidth || 640;
  const height = 220;
  const dpr = window.devicePixelRatio || 1;
  el.width = Math.round(width * dpr);
  el.height = Math.round(height * dpr);
  const ctx = el.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  const points = props.rows.filter((row) => row.download_bps != null || row.upload_bps != null);
  if (!points.length) {
    ctx.fillStyle = cssColor("--muted", "#6e6e6e");
    ctx.font = "14px sans-serif";
    ctx.fillText(t("chart.noMeasurements"), 12, 28);
    return;
  }
  const pad = { left: 52, right: 12, top: 16, bottom: 28 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = Math.max(
    1,
    ...points.flatMap((row) => [row.download_bps, row.upload_bps].filter((value) => value != null).map((value) => (value * 8) / 1e6)),
  );
  ctx.strokeStyle = cssColor("--line", "#e3e3e3");
  ctx.fillStyle = cssColor("--muted", "#6e6e6e");
  ctx.font = "11px ui-monospace, monospace";
  ctx.lineWidth = 1;
  for (let step = 0; step <= 4; step += 1) {
    const y = pad.top + (plotH * step) / 4;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(width - pad.right, y);
    ctx.stroke();
    ctx.fillText((max * (1 - step / 4)).toFixed(max >= 10 ? 0 : 1), 6, y + 4);
  }
  strokeSeries(ctx, points, "download_bps", cssColor("--ok", "#2f9e62"), pad, plotW, plotH, max);
  strokeSeries(ctx, points, "upload_bps", cssColor("--red", "#d14332"), pad, plotW, plotH, max);
  ctx.fillStyle = cssColor("--muted", "#6e6e6e");
  ctx.fillText(formatTime(points[0].tested_at), pad.left, height - 8);
  const lastLabel = formatTime(points[points.length - 1].tested_at);
  ctx.fillText(lastLabel, width - pad.right - ctx.measureText(lastLabel).width, height - 8);
}

onMounted(() => requestAnimationFrame(draw));
watch(() => [props.rows, i18n.lang], draw);
</script>

<template>
  <canvas ref="canvas"></canvas>
</template>
