<script setup>
import { ChevronRightIcon, EllipsisIcon, PencilIcon, PlayIcon, PlusIcon, RefreshCwIcon, SearchIcon, Trash2Icon } from "@lucide/vue";
import { computed, ref } from "vue";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import Hint from "../components/Hint.vue";
import NodeName from "../components/NodeName.vue";
import ProtoBadge from "../components/ProtoBadge.vue";
import { api } from "../lib/api.js";
import { formatBytes, formatTime, nodeDot, scheduleSummary, timeUntil } from "../lib/format.js";
import { i18n, t, tMsg } from "../lib/i18n.js";
import { suppressRepeatSelection } from "../lib/pointer.js";
import { openNode, openSourceDialog, refreshSources, reloadAll, reportError, setSourceOpen, startRun, state, toast } from "../store.js";

/* Двухуровневая таблица: источник (подписка или группа) и под ним его узлы. Узел из нескольких источников
   показан в каждом, но это один узел — с одной галочкой и одной историей. */

/* Подтверждение удаления: окно закрывается само по клику, поэтому сам источник держится отдельно от флага. */
const deleting = ref(null);
const confirmOpen = ref(false);

const query = computed(() => state.subQuery.trim().toLowerCase());
const busy = computed(() => state.refreshing !== null || Boolean(state.remote.running));

function matches(node) {
  return !query.value || `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query.value);
}

function byName(a, b) {
  return a.name.localeCompare(b.name, i18n.lang);
}

/* В строке только хост: в пути адреса подписки обычно лежит токен, а этот экран открывают каждый день. */
function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

function sourceName(source) {
  return source.name || source.title || (source.kind === "subscription" ? hostOf(source.url) : t("source.untitled"));
}

function sourceMeta(source, members) {
  const parts = [t(source.kind === "group" ? "source.kindGroup" : "source.kindSubscription")];
  if (source.kind === "subscription" && (source.name || source.title)) parts.push(hostOf(source.url));
  parts.push(t("source.nodes", { count: members.length }));
  parts.push(scheduleSummary(source));
  if (source.refreshed_at) parts.push(t("source.refreshed", { time: formatTime(source.refreshed_at) }));
  const info = source.userinfo;
  if (info && info.total > 0) {
    const used = (info.upload || 0) + (info.download || 0);
    parts.push(t("subscription.traffic", { used: formatBytes(used), total: formatBytes(info.total) }));
  } else if (info && info.expire > 0) {
    parts.push(t("subscription.until", { date: formatTime(new Date(info.expire * 1000).toISOString()) }));
  }
  return parts;
}

/* Срок следующей проверки источника. Обратный отсчёт пересчитывается на каждый такт, поэтому отдельно от groups. */
function sourceNext(source) {
  void state.tick;
  if (!source.schedule_enabled) return "";
  if (source.idle) return t("source.nothingToCheck");
  if (state.remote.running || !source.next_run_at) return "";
  const left = timeUntil(source.next_run_at);
  return left ? t("source.nextIn", { time: left }) : t("source.nextNow");
}

const groups = computed(() => {
  const list = state.sources.map((source) => {
    const members = state.nodes.filter((node) => node.sources.includes(source.id)).sort(byName);
    return {
      key: String(source.id),
      source,
      name: sourceName(source),
      meta: sourceMeta(source, members),
      members,
      visible: members.filter(matches),
      enabled: members.filter((node) => node.supported && node.enabled).length,
      checkable: members.filter((node) => node.supported).length,
    };
  });
  /* Узлы, которых больше не присылает ни один источник: история у них осталась, а проверять их нечем. */
  if (state.showInactive) {
    const gone = state.nodes.filter((node) => !node.sources.length).sort(byName);
    if (gone.length) list.push({ key: "gone", source: null, name: t("source.gone"), meta: [], members: gone, visible: gone.filter(matches) });
  }
  return query.value ? list.filter((group) => group.visible.length) : list;
});

/* Пока человек ничего не сворачивал, единственный источник раскрыт, а несколько — свёрнуты.
   При поиске раскрыто всё, где нашлось совпадение. */
function isOpen(group) {
  if (query.value) return true;
  if (state.openSources === null) return state.sources.length === 1;
  return state.openSources.has(group.key);
}

function toggle(group) {
  if (query.value) return;
  const open = isOpen(group);
  if (state.openSources === null) {
    state.openSources = new Set(groups.value.filter((item) => isOpen(item)).map((item) => item.key));
  }
  setSourceOpen(group.key, !open);
}

async function setNode(node, enabled) {
  try {
    await api(`/api/nodes/${node.id}/enabled`, { method: "POST", json: { enabled } });
    node.enabled = enabled;
  } catch (error) {
    reportError(error);
  }
}

async function setSource(source, enabled) {
  try {
    await api(`/api/sources/${source.id}/enabled`, { method: "POST", json: { enabled } });
    await reloadAll();
  } catch (error) {
    reportError(error);
  }
}

function askDelete(source) {
  deleting.value = source;
  confirmOpen.value = true;
}

async function remove() {
  const source = deleting.value;
  confirmOpen.value = false;
  if (!source) return;
  try {
    await api(`/api/sources/${source.id}`, { method: "DELETE" });
    await reloadAll();
    toast(t("toast.sourceDeleted"));
  } catch (error) {
    reportError(error);
  }
}
</script>

<template>
  <section class="flex flex-col gap-4">

    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div v-if="state.sources.length || state.nodes.length" class="relative min-w-52 flex-1 sm:max-w-sm">
        <SearchIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          v-model="state.subQuery"
          type="search"
          class="pl-8"
          :placeholder="t('search.placeholder')"
          :aria-label="t('search.subscription')"
        />
      </div>
      <div v-if="state.nodes.length" class="flex items-center gap-2">
        <Checkbox id="show-inactive" v-model="state.showInactive" />
        <Label for="show-inactive" class="font-normal">{{ t("subscription.showInactive") }}</Label>
      </div>
      <div class="flex gap-2 sm:ml-auto">
        <Button v-if="state.sources.length" variant="outline" size="lg" :disabled="busy" @click="refreshSources()">
          <RefreshCwIcon :class="{ 'animate-spin': state.refreshing === 'all' }" aria-hidden="true" />{{ t("action.refreshAll") }}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="lg"><PlusIcon aria-hidden="true" />{{ t("action.add") }}</Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-auto min-w-44">
            <DropdownMenuItem @select="openSourceDialog('subscription')">{{ t("source.kindSubscription") }}</DropdownMenuItem>
            <DropdownMenuItem @select="openSourceDialog('group')">{{ t("source.kindGroup") }}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <!-- Ручная проверка всех включённых узлов. Остановить её можно в панели прогресса. -->
        <Button v-if="state.sources.length" size="lg" :disabled="busy" @click="startRun({})">
          <PlayIcon aria-hidden="true" />{{ t("action.checkAll") }}
        </Button>
      </div>
    </div>

    <div v-if="state.settings && !groups.length && !query" class="flex flex-col items-start gap-3 rounded-xl border px-4 py-7">
      <p class="text-muted-foreground">{{ t("source.empty") }}</p>
      <div class="flex flex-wrap gap-2">
        <Button size="lg" @click="openSourceDialog('subscription')">{{ t("action.addSubscription") }}</Button>
        <Button variant="outline" size="lg" @click="openSourceDialog('group')">{{ t("action.addGroup") }}</Button>
      </div>
    </div>

    <div v-else-if="groups.length || query" class="overflow-hidden rounded-xl border select-none" @mousedown="suppressRepeatSelection">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent">
            <TableHead class="px-3 text-xs text-muted-foreground">{{ t("column.node") }}</TableHead>
            <TableHead class="hidden px-3 text-xs text-muted-foreground sm:table-cell">{{ t("column.protocol") }}</TableHead>
            <TableHead class="px-3 text-right text-xs text-muted-foreground">{{ t("column.inCheck") }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody v-for="group in groups" :key="group.key" class="border-b last:border-b-0 [&_tr:last-child]:border-b-0">
          <TableRow class="cursor-pointer bg-muted/40 select-none hover:bg-muted" @click="toggle(group)">
            <TableCell colspan="3" class="px-3 py-2.5 whitespace-normal">
              <div class="flex items-center gap-2">
                <button
                  type="button"
                  class="flex min-w-0 flex-1 items-start gap-2 rounded-sm text-left focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                  :aria-expanded="isOpen(group)"
                  @click.stop="toggle(group)"
                >
                  <ChevronRightIcon
                    class="mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform"
                    :class="{ 'rotate-90': isOpen(group) }"
                    aria-hidden="true"
                  />
                  <span class="min-w-0">
                    <span class="block truncate font-medium">{{ group.name }}</span>
                    <span v-if="group.meta.length" class="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                      <span v-for="part in group.meta" :key="part">{{ part }}</span>
                      <span v-if="group.source && sourceNext(group.source)" class="tabular">{{ sourceNext(group.source) }}</span>
                    </span>
                    <span v-if="group.source?.error" class="block text-xs text-destructive">{{ tMsg(group.source.error) }}</span>
                  </span>
                </button>
                <template v-if="group.source">
                  <span v-if="group.checkable" class="hidden shrink-0 text-xs text-muted-foreground tabular sm:inline">
                    {{ t("source.inCheck", { on: group.enabled, total: group.checkable }) }}
                  </span>
                  <Hint :text="t('source.check', { name: group.name })">
                    <Button
                      variant="ghost"
                      size="icon"
                      :disabled="busy || !group.enabled"
                      :aria-label="t('source.check', { name: group.name })"
                      @click.stop="startRun({ source_ids: [group.source.id] })"
                    >
                      <PlayIcon aria-hidden="true" />
                    </Button>
                  </Hint>
                  <Hint v-if="group.source.kind === 'subscription'" :text="t('action.refreshSubscription')">
                    <Button
                      variant="ghost"
                      size="icon"
                      :disabled="busy"
                      :aria-label="t('action.refreshSubscription')"
                      @click.stop="refreshSources(group.source.id)"
                    >
                      <RefreshCwIcon :class="{ 'animate-spin': state.refreshing === group.source.id }" aria-hidden="true" />
                    </Button>
                  </Hint>
                  <DropdownMenu>
                    <DropdownMenuTrigger as-child>
                      <Button variant="ghost" size="icon" :aria-label="t('source.menu', { name: group.name })" @click.stop>
                        <EllipsisIcon aria-hidden="true" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" class="w-auto min-w-44" @click.stop>
                      <DropdownMenuItem @select="openSourceDialog(group.source.kind, group.source.id)">
                        <PencilIcon aria-hidden="true" />{{ t("action.edit") }}
                      </DropdownMenuItem>
                      <DropdownMenuItem :disabled="!group.checkable" @select="setSource(group.source, true)">{{ t("action.enableAll") }}</DropdownMenuItem>
                      <DropdownMenuItem :disabled="!group.checkable" @select="setSource(group.source, false)">{{ t("action.disableAll") }}</DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem variant="destructive" @select="askDelete(group.source)">
                        <Trash2Icon aria-hidden="true" />{{ t("action.delete") }}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </template>
              </div>
            </TableCell>
          </TableRow>
          <template v-if="isOpen(group)">
            <TableRow
              v-for="node in group.visible"
              :key="node.id"
              class="cursor-pointer select-none"
              :class="{ 'opacity-60': !node.enabled }"
              @click="openNode(node.id)"
            >
              <TableCell class="max-w-56 py-2 pr-3 pl-9 sm:max-w-96">
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
                <!-- Проверка одного узла, как в его карточке: и выключенного тоже, раз его просят явно. -->
                <span class="inline-flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    :disabled="busy || !node.supported"
                    :aria-label="t('source.check', { name: node.name })"
                    @click.stop="startRun({ node_ids: [node.id], include_disabled: true })"
                  >
                    <PlayIcon aria-hidden="true" />
                  </Button>
                  <Switch
                    :model-value="node.enabled"
                    :disabled="!node.supported"
                    :aria-label="node.name"
                    @update:model-value="setNode(node, $event)"
                    @click.stop
                  />
                </span>
              </TableCell>
            </TableRow>
            <TableRow v-if="!group.visible.length" class="hover:bg-transparent">
              <TableCell colspan="3" class="py-3 pr-3 pl-9 text-sm text-muted-foreground">{{ t("source.noNodes") }}</TableCell>
            </TableRow>
          </template>
        </TableBody>
        <TableBody v-if="!groups.length">
          <TableRow>
            <TableCell colspan="3" class="px-3 py-6 text-muted-foreground">{{ t("common.noMatches") }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <AlertDialog v-model:open="confirmOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t("source.confirmDelete", { name: deleting ? sourceName(deleting) : "" }) }}</AlertDialogTitle>
          <AlertDialogDescription>{{ t("source.confirmDeleteNote") }}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("action.cancel") }}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" @click="remove">{{ t("action.delete") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </section>
</template>
