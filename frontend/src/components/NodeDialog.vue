<script setup>
import { computed, ref, watch } from "vue";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMs, formatTime, mbps } from "../lib/format.js";
import { t, tMsg } from "../lib/i18n.js";
import { state } from "../store.js";
import NodeChart from "./NodeChart.vue";
import ProtoBadge from "./ProtoBadge.vue";

/* Содержимое остаётся на время анимации закрытия, поэтому держим последний открытый узел. */
const shown = ref(null);
const recent = computed(() => (shown.value?.history || []).slice(-8).reverse());

watch(() => state.dialog, (value) => {
  if (value) shown.value = value;
});

function changed(open) {
  if (!open) state.dialog = null;
}
</script>

<template>
  <Dialog :open="Boolean(state.dialog)" @update:open="changed">
    <DialogContent class="max-h-[calc(100dvh-2rem)] gap-4 overflow-y-auto p-5 sm:max-w-3xl">
      <template v-if="shown">
        <DialogHeader class="min-w-0 pr-8">
          <ProtoBadge :protocol="shown.node.protocol" />
          <DialogTitle class="truncate text-xl font-semibold tracking-tight">{{ shown.node.name }}</DialogTitle>
          <DialogDescription class="font-mono text-xs">{{ shown.node.address }}:{{ shown.node.port }}</DialogDescription>
        </DialogHeader>
        <NodeChart :rows="shown.history" />
        <div class="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.time") }}</TableHead>
                <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.latency") }}</TableHead>
                <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.download") }}</TableHead>
                <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.upload") }}</TableHead>
                <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.result") }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-for="row in recent" :key="row.tested_at">
                <TableCell class="px-3">{{ formatTime(row.tested_at) }}</TableCell>
                <TableCell class="px-3 tabular">{{ formatMs(row.latency_ms) }}</TableCell>
                <TableCell class="px-3 tabular">{{ mbps(row.download_bps) }}</TableCell>
                <TableCell class="px-3 tabular">{{ mbps(row.upload_bps) }}</TableCell>
                <TableCell class="min-w-40 px-3 whitespace-normal" :class="row.ok ? 'text-success' : 'text-destructive'">
                  {{ row.ok ? t("dialog.ok") : tMsg(row.error) || t("dialog.error") }}
                </TableCell>
              </TableRow>
              <TableRow v-if="!recent.length">
                <TableCell colspan="5" class="px-3 py-6 text-muted-foreground">{{ t("dialog.noMeasurements") }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </template>
    </DialogContent>
  </Dialog>
</template>
