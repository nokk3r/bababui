<script setup>
import { computed, ref } from "vue";
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

async function toggle(event, node) {
  const { checked } = event.target;
  try {
    await api(`/api/nodes/${node.id}/enabled`, { method: "POST", json: { enabled: checked } });
    node.enabled = checked;
  } catch (error) {
    event.target.checked = !checked;
    reportError(error);
  }
}

function rowClick(event, node) {
  if (event.target.closest("input, label, button")) return;
  openNode(node.id);
}
</script>

<template>
  <section>
    <div class="section-head">
      <p class="muted">{{ t("subscription.lead") }}</p>
      <div class="top-actions">
        <button
          type="button"
          class="ghost"
          :disabled="refreshing || Boolean(state.remote.running)"
          @click="refresh"
        >{{ t("action.refreshSubscription") }}</button>
      </div>
    </div>
    <div class="toolbar">
      <input
        v-model="state.subQuery"
        type="search"
        :placeholder="t('search.placeholder')"
        :aria-label="t('search.subscription')"
      >
      <label class="check"><input v-model="state.showInactive" type="checkbox"> <span>{{ t("subscription.showInactive") }}</span></label>
      <div class="toolbar-end">
        <button type="button" class="ghost" @click="setAll(true)">{{ t("action.enableAll") }}</button>
        <button type="button" class="ghost" @click="setAll(false)">{{ t("action.disableAll") }}</button>
      </div>
    </div>
    <div class="table-wrap">
      <table id="subscription-nodes">
        <thead>
          <tr>
            <th>{{ t("column.node") }}</th>
            <th>{{ t("column.protocol") }}</th>
            <th>{{ t("column.inCheck") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="node in rows"
            :key="node.id"
            :class="{ 'is-off': !node.enabled, 'is-gone': !node.active }"
            @click="rowClick($event, node)"
          >
            <td>
              <NodeName
                :dot="nodeDot(node)"
                :name="node.name"
                :sub="node.active ? `${node.address}:${node.port}` : t('subscription.gone')"
              />
            </td>
            <td><ProtoBadge :protocol="node.protocol" /></td>
            <td>
              <label class="check">
                <input type="checkbox" :checked="node.enabled" :disabled="!node.supported" @change="toggle($event, node)">
              </label>
            </td>
          </tr>
          <tr v-if="!rows.length"><td colspan="3" class="empty">{{ t("common.noMatches") }}</td></tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
