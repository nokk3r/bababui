<script setup>
import { computed, ref, watch } from "vue";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatMs, formatTime, resultDot, speedUnit } from "../lib/format.js";
import { t, tMsg } from "../lib/i18n.js";
import { state } from "../store.js";
import ErrorText from "./ErrorText.vue";
import NodeChart from "./NodeChart.vue";
import ProtoBadge from "./ProtoBadge.vue";
import SpeedValue from "./SpeedValue.vue";
import StatusIcon from "./StatusIcon.vue";

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
    <DialogContent class="max-h-[calc(100dvh-2rem)] gap-4 overflow-y-auto p-3 sm:max-w-3xl sm:p-5">
      <template v-if="shown">
        <DialogHeader class="min-w-0 pr-8">
          <ProtoBadge :protocol="shown.node.protocol" />
          <DialogTitle class="truncate text-xl font-semibold tracking-tight">{{ shown.node.name }}</DialogTitle>
          <DialogDescription class="font-mono text-xs">{{ shown.node.address }}:{{ shown.node.port }}</DialogDescription>
        </DialogHeader>
        <NodeChart :rows="shown.history" />
        <!-- Единицы стоят в заголовке, а причина сбоя идёт отдельной строкой: так таблица помещается в телефон. -->
        <div class="overflow-hidden rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead class="px-2 text-xs text-muted-foreground sm:px-3">{{ t("column.time") }}</TableHead>
                <TableHead class="px-2 text-xs text-muted-foreground sm:px-3">{{ t("column.latency") }}</TableHead>
                <TableHead class="px-2 text-xs text-muted-foreground sm:px-3">{{ t("column.download") }}<span class="block font-normal">{{ t(speedUnit()) }}</span></TableHead>
                <TableHead class="px-2 text-xs text-muted-foreground sm:px-3">{{ t("column.upload") }}<span class="block font-normal">{{ t(speedUnit()) }}</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <template v-for="row in recent" :key="row.tested_at">
                <TableRow class="hover:bg-transparent" :class="{ 'border-b-0': !row.ok }">
                  <TableCell class="px-2 sm:px-3">
                    <span class="flex items-center gap-1.5">
                      <StatusIcon :status="resultDot(row.ok, row.alive)" />{{ formatTime(row.tested_at) }}
                    </span>
                  </TableCell>
                  <TableCell class="px-2 tabular sm:px-3">{{ formatMs(row.latency_ms) }}</TableCell>
                  <TableCell class="px-2 tabular sm:px-3"><SpeedValue :bps="row.download_bps" :unit="false" /></TableCell>
                  <TableCell class="px-2 tabular sm:px-3"><SpeedValue :bps="row.upload_bps" :unit="false" /></TableCell>
                </TableRow>
                <TableRow v-if="!row.ok" class="hover:bg-transparent">
                  <TableCell colspan="4" class="px-2 pt-0 pb-2.5 text-xs whitespace-normal text-destructive sm:px-3 sm:pl-[1.85rem]">
                    <ErrorText :text="tMsg(row.error) || t('dialog.error')" />
                  </TableCell>
                </TableRow>
              </template>
              <TableRow v-if="!recent.length">
                <TableCell colspan="4" class="px-3 py-6 text-muted-foreground">{{ t("dialog.noMeasurements") }}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </template>
    </DialogContent>
  </Dialog>
</template>
