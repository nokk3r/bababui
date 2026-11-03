<script setup>
import { RefreshCwIcon, SearchIcon } from "@lucide/vue";
import { computed, ref } from "vue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import NodeName from "../components/NodeName.vue";
import ProtoBadge from "../components/ProtoBadge.vue";
import { api } from "../lib/api.js";
import { nodeDot } from "../lib/format.js";
import { i18n, t } from "../lib/i18n.js";
import { openNode, reloadAll, reportError, state, toast } from "../store.js";

const refreshing = ref(false);

const rows = computed(() => {
  const query = state.subQuery.trim().toLowerCase();
  return state.nodes.filter((node) => {
    if (!state.showInactive && !node.active) return false;
    if (!query) return true;
    return `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query);
  }).sort((a, b) => a.name.localeCompare(b.name, i18n.lang));
});

async function refresh() {
  refreshing.value = true;
  try {
    const result = await api("/api/subscription/refresh", { method: "POST" });
    await reloadAll();
    toast(t("toast.subscriptionUpdated", { count: result.count }));
  } catch (error) {
    reportError(error);
  } finally {
    refreshing.value = false;
  }
}

async function setAll(enabled) {
  try {
    await api("/api/nodes/enabled", { method: "POST", json: { enabled } });
    await reloadAll();
  } catch (error) {
    reportError(error);
  }
}

async function toggle(node, enabled) {
  try {
    await api(`/api/nodes/${node.id}/enabled`, { method: "POST", json: { enabled } });
    node.enabled = enabled;
  } catch (error) {
    reportError(error);
  }
}

</script>

<template>
  <section class="flex flex-col gap-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="text-sm text-muted-foreground">{{ t("subscription.lead") }}</p>
      <Button variant="outline" size="lg" :disabled="refreshing || Boolean(state.remote.running)" @click="refresh">
        <RefreshCwIcon :class="{ 'animate-spin': refreshing }" aria-hidden="true" />{{ t("action.refreshSubscription") }}
      </Button>
    </div>
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div class="relative min-w-52 flex-1 sm:max-w-sm">
        <SearchIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          v-model="state.subQuery"
          type="search"
          class="pl-8"
          :placeholder="t('search.placeholder')"
          :aria-label="t('search.subscription')"
        />
      </div>
      <div class="flex items-center gap-2">
        <Checkbox id="show-inactive" v-model="state.showInactive" />
        <Label for="show-inactive" class="font-normal">{{ t("subscription.showInactive") }}</Label>
      </div>
      <div class="flex gap-2 sm:ml-auto">
        <Button variant="outline" size="lg" @click="setAll(true)">{{ t("action.enableAll") }}</Button>
        <Button variant="outline" size="lg" @click="setAll(false)">{{ t("action.disableAll") }}</Button>
      </div>
    </div>
    <div class="overflow-hidden rounded-xl border">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent">
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.node") }}</TableHead>
            <TableHead class="hidden px-3 text-xs text-muted-foreground sm:table-cell">{{ t("column.protocol") }}</TableHead>
            <TableHead class="px-3 text-right text-xs text-muted-foreground">{{ t("column.inCheck") }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="node in rows"
            :key="node.id"
            class="cursor-pointer"
            :class="{ 'opacity-60': !node.enabled }"
            @click="openNode(node.id)"
          >
            <TableCell class="max-w-56 px-3 sm:max-w-96">
              <NodeName
                :dot="nodeDot(node)"
                :name="node.name"
                :sub="node.active ? `${node.address}:${node.port}` : t('subscription.gone')"
                interactive
                @open="openNode(node.id)"
              />
            </TableCell>
            <TableCell class="hidden px-3 sm:table-cell"><ProtoBadge :protocol="node.protocol" /></TableCell>
            <TableCell class="px-3 text-right">
              <Switch
                :model-value="node.enabled"
                :disabled="!node.supported"
                :aria-label="node.name"
                @update:model-value="toggle(node, $event)"
                @click.stop
              />
            </TableCell>
          </TableRow>
          <TableRow v-if="!rows.length">
            <TableCell colspan="3" class="px-3 py-6 text-muted-foreground">{{ t("common.noMatches") }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </section>
</template>
