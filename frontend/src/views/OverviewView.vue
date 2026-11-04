<script setup>
import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon, Columns3Icon, PlayIcon, SearchIcon } from "@lucide/vue";
import { useMediaQuery } from "@vueuse/core";
import { computed, watch } from "vue";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import NodeName from "../components/NodeName.vue";
import CheckBars from "../components/CheckBars.vue";
import Hint from "../components/Hint.vue";
import ProtoBadge from "../components/ProtoBadge.vue";
import SpeedValue from "../components/SpeedValue.vue";
import { formatMs, formatTime, mean, nodeDot, protocolName } from "../lib/format.js";
import { suppressRepeatSelection } from "../lib/pointer.js";
import { i18n, t } from "../lib/i18n.js";
import { checkingStage, COLUMN_KEYS, openNode, openSourceDialog, setColumn, setSort, SORT_KEYS, startRun, state } from "../store.js";

const COLUMN_LABELS = {
  protocol: "column.protocol",
  latency_ms: "column.latency",
  download_bps: "column.download",
  upload_bps: "column.upload",
  avg_latency_ms: "column.avgLatency",
  avg_download_bps: "column.avgDownload",
  avg_upload_bps: "column.avgUpload",
  spark: "column.spark",
  action: "column.action",
};

const SORTABLE = SORT_KEYS.map((key) => [key, key === "name" ? "column.node" : COLUMN_LABELS[key]]);

const NO_SORT = "none";

const tableLayout = useMediaQuery("(min-width: 768px)");

/* Отключённые узлы хранят старый результат, поэтому в здоровье подписки они не считаются. */
const checked = computed(() => (
  state.nodes.filter((node) => node.active && node.supported && node.enabled)
));
const health = computed(() => {
  const counts = { ok: 0, warn: 0, bad: 0, idle: 0, unsupported: 0 };
  for (const node of checked.value) counts[nodeDot(node)] += 1;
  return counts;
});

const STATUS_KEYS = ["ok", "warn", "bad", "idle"];
const STATUS_COLORS = { ok: "bg-success", warn: "bg-warning", bad: "bg-destructive", idle: "bg-muted-foreground" };

const segments = computed(() => STATUS_KEYS.filter((key) => health.value[key]).map((key) => ({
  key,
  color: STATUS_COLORS[key],
  count: health.value[key],
  title: `${t(`filter.${key}`)}: ${health.value[key]}`,
})));
/* Число стоит над своим сегментом: колонки общие, ширина по числу узлов, но не уже самого числа. */
const segmentColumns = computed(() => segments.value.map((segment) => `minmax(min-content, ${segment.count}fr)`).join(" "));

/* Повторное нажатие на тот же статус снимает фильтр. */
function toggleStatus(key) {
  state.status = state.status === key ? "all" : key;
}

const samples = computed(() => checked.value.filter((node) => node.last_ok));
const avgLatency = computed(() => mean(samples.value.map((node) => node.latency_ms)));
const avgDownload = computed(() => mean(samples.value.map((node) => node.download_bps)));
const avgUpload = computed(() => mean(samples.value.map((node) => node.upload_bps)));
const basedOn = computed(() => (samples.value.length ? t("stat.basedOn", { count: samples.value.length }) : ""));

const protocols = computed(() => [...new Set(state.nodes.map((node) => node.protocol))].sort());

watch(protocols, (list) => {
  if (state.protocol !== "all" && !list.includes(state.protocol)) state.protocol = "all";
});

function sortNodes(nodes) {
  if (!state.sortKey || !state.sortDir) return nodes;
  const direction = state.sortDir === "asc" ? 1 : -1;
  const key = state.sortKey;
  return nodes.slice().sort((a, b) => {
    if (key === "name" || key === "protocol") {
      const left = key === "name" ? a.name : protocolName(a.protocol);
      const right = key === "name" ? b.name : protocolName(b.protocol);
      const compared = left.localeCompare(right, i18n.lang);
      return compared === 0 ? 0 : compared * direction;
    }
    const left = a[key];
    const right = b[key];
    const leftEmpty = left == null || left === "";
    const rightEmpty = right == null || right === "";
    if (leftEmpty && rightEmpty) return a.name.localeCompare(b.name, i18n.lang);
    if (leftEmpty) return 1;
    if (rightEmpty) return -1;
    const compared = Number(left) - Number(right);
    return compared === 0 ? a.name.localeCompare(b.name, i18n.lang) : compared * direction;
  });
}

const rows = computed(() => {
  const query = state.query.trim().toLowerCase();
  const visible = state.nodes.filter((node) => {
    if (!node.active) return false;
    if (state.protocol !== "all" && node.protocol !== state.protocol) return false;
    /* Как в карточке «Работают»: отключённые узлы в статусах не считаются. */
    if (state.status !== "all" && !(node.enabled && node.supported && nodeDot(node) === state.status)) return false;
    if (!query) return true;
    return `${node.name} ${node.address} ${node.protocol}`.toLowerCase().includes(query);
  }).map((node) => {
    const history = state.series.get(node.id) || [];
    return {
      ...node,
      avg_latency_ms: mean(history.map((row) => (row.ok ? row.latency_ms : null))),
      avg_download_bps: mean(history.map((row) => (row.ok ? row.download_bps : null))),
      avg_upload_bps: mean(history.map((row) => (row.ok ? row.upload_bps : null))),
      spark: state.recent.get(node.id) || [],
    };
  });
  return sortNodes(visible);
});

/* Источники приходят вместе с настройками: до загрузки пустой экран не должен звать добавлять подписку. */
const noSubscription = computed(() => Boolean(state.settings) && !state.sources.length);

const emptyText = computed(() => {
  if (noSubscription.value) return t("empty.noSubscription");
  const waiting = !state.sources.some((source) => source.refreshed_at || source.error);
  return waiting ? t("common.loadingSubscription") : t("common.noMatches");
});

const sortColumns = computed(() => SORTABLE.filter(([key]) => key === "name" || state.columns[key]));
const running = computed(() => state.remote.running);

/* Проверка одного узла, как на экране подписок: и выключенного тоже, раз его просят явно. */
function checkNode(node) {
  startRun({ node_ids: [node.id], include_disabled: true });
}

/* Нажатия по заголовку: по возрастанию, по убыванию, без сортировки. */
function sortBy(key) {
  if (state.sortKey !== key || !state.sortDir) setSort(key, "asc");
  else if (state.sortDir === "asc") setSort(key, "desc");
  else setSort(null, null);
}

/* На телефоне заголовков нет, поэтому «без сортировки» — отдельный пункт списка, а не третье нажатие. */
function setSortKey(key) {
  if (key === NO_SORT) setSort(null, null);
  else setSort(key, state.sortDir || "asc");
}

function flipSort() {
  setSort(state.sortKey, state.sortDir === "asc" ? "desc" : "asc");
}

function isSorted(key) {
  return key === state.sortKey && Boolean(state.sortDir);
}

function ariaSort(key) {
  if (!isSorted(key)) return "none";
  return state.sortDir === "asc" ? "ascending" : "descending";
}

/* Пока узел проверяется, вместо времени последней проверки показываем этап. */
function activity(node) {
  const stage = checkingStage(node.id);
  if (stage === null) return "";
  return stage ? `${t(`stage.${stage}`)}…` : `${t("phase.checking")}…`;
}
</script>

<template>
  <section class="flex flex-col gap-4">
    <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
      <Card class="col-span-2 gap-1 px-4 py-3.5 sm:col-span-3 xl:col-span-1">
        <p class="text-muted-foreground">{{ t("stat.working") }}</p>
        <strong class="text-3xl font-semibold tracking-tight tabular">
          {{ health.ok }}<small class="ml-1.5 text-sm font-normal tracking-normal text-muted-foreground">{{ t("stat.outOf", { total: checked.length }) }}</small>
        </strong>
        <!-- Сегмент с числом над ним — одна кнопка: нажатие оставляет в таблице узлы этого статуса. -->
        <div v-if="checked.length" class="mt-1 grid gap-x-0.5" :style="{ gridTemplateColumns: segmentColumns }">
          <Hint v-for="(segment, index) in segments" :key="segment.key" :text="segment.title">
            <button
              type="button"
              class="group flex min-w-0 cursor-pointer flex-col items-start gap-1 rounded-sm select-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              :class="state.status !== 'all' && state.status !== segment.key ? 'opacity-30' : ''"
              :aria-label="segment.title"
              :aria-pressed="state.status === segment.key"
              @mousedown="suppressRepeatSelection"
              @click="toggleStatus(segment.key)"
            >
              <span
                class="px-0.5 text-xs leading-none tabular group-hover:text-foreground"
                :class="state.status === segment.key ? 'font-medium text-foreground' : 'text-muted-foreground'"
              >{{ segment.count }}</span>
              <span
                class="h-1.5 w-full transition-opacity"
                :class="[segment.color, index === 0 ? 'rounded-l-full' : '', index === segments.length - 1 ? 'rounded-r-full' : '']"
              ></span>
            </button>
          </Hint>
        </div>
      </Card>
      <Card class="gap-1 px-4 py-3.5">
        <p class="text-muted-foreground">{{ t("stat.avgLatency") }}</p>
        <strong class="text-3xl font-semibold tracking-tight tabular">
          <template v-if="avgLatency == null">—</template>
          <template v-else>{{ Math.round(avgLatency) }}<small class="ml-1.5 text-sm font-normal tracking-normal text-muted-foreground">{{ t("unit.ms") }}</small></template>
        </strong>
        <p class="min-h-4 text-xs text-muted-foreground">{{ basedOn }}</p>
      </Card>
      <Card class="gap-1 px-4 py-3.5">
        <p class="text-muted-foreground">{{ t("stat.avgDownload") }}</p>
        <strong class="text-3xl font-semibold tracking-tight tabular"><SpeedValue :bps="avgDownload" size="lg" /></strong>
        <p class="min-h-4 text-xs text-muted-foreground">{{ basedOn }}</p>
      </Card>
      <Card class="col-span-2 gap-1 px-4 py-3.5 sm:col-span-1">
        <p class="text-muted-foreground">{{ t("stat.avgUpload") }}</p>
        <strong class="text-3xl font-semibold tracking-tight tabular"><SpeedValue :bps="avgUpload" size="lg" /></strong>
        <p class="min-h-4 text-xs text-muted-foreground">{{ basedOn }}</p>
      </Card>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="relative min-w-52 flex-1 sm:max-w-sm">
        <SearchIcon class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          v-model="state.query"
          type="search"
          class="pl-8"
          :placeholder="t('search.placeholder')"
          :aria-label="t('search.node')"
        />
      </div>
      <Select :key="`protocol-${i18n.lang}`" v-model="state.protocol">
        <SelectTrigger :aria-label="t('filter.protocol')">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{{ t("filter.allProtocols") }}</SelectItem>
          <SelectItem v-for="protocol in protocols" :key="protocol" :value="protocol">{{ protocolName(protocol) }}</SelectItem>
        </SelectContent>
      </Select>
      <Select :key="`status-${i18n.lang}`" v-model="state.status">
        <SelectTrigger :aria-label="t('filter.status')">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{{ t("filter.allStatuses") }}</SelectItem>
          <SelectItem v-for="key in STATUS_KEYS" :key="key" :value="key">{{ t(`filter.${key}`) }}</SelectItem>
        </SelectContent>
      </Select>

      <template v-if="tableLayout">
        <!-- Подсказка снаружи меню и на обёртке: у подсказки и меню по своему якорю. Вложенные внутрь меню,
             они делят один, и меню рисуется за краем экрана. -->
        <Hint :text="t('columns.label')">
          <span class="ml-auto inline-flex">
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="outline" size="icon-lg" :aria-label="t('columns.label')">
                  <Columns3Icon aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" class="w-auto min-w-44">
                <DropdownMenuCheckboxItem
                  v-for="key in COLUMN_KEYS"
                  :key="key"
                  :model-value="state.columns[key]"
                  @update:model-value="setColumn(key, $event)"
                  class="whitespace-nowrap"
                  @select.prevent
                >{{ t(COLUMN_LABELS[key]) }}</DropdownMenuCheckboxItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </span>
        </Hint>
      </template>
      <template v-else>
        <Select :key="`sort-${i18n.lang}`" :model-value="state.sortKey || NO_SORT" @update:model-value="setSortKey">
          <SelectTrigger :aria-label="t('sort.label')">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem :value="NO_SORT">{{ t("sort.none") }}</SelectItem>
            <SelectItem v-for="[key, label] in SORTABLE" :key="key" :value="key">{{ t(label) }}</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="icon-lg" :aria-label="t('sort.toggle')" :disabled="!state.sortKey" @click="flipSort">
          <ArrowUpIcon v-if="state.sortDir === 'asc'" aria-hidden="true" />
          <ArrowDownIcon v-else aria-hidden="true" />
        </Button>
      </template>
    </div>

    <div v-if="!rows.length" class="flex flex-col items-start gap-3 rounded-xl border px-4 py-7">
      <p class="text-muted-foreground">{{ emptyText }}</p>
      <Button v-if="noSubscription" size="lg" @click="openSourceDialog('subscription')">{{ t("action.addSubscription") }}</Button>
    </div>

    <div v-else-if="tableLayout" class="overflow-hidden rounded-xl border select-none" @mousedown="suppressRepeatSelection">
      <Table>
        <TableHeader>
          <TableRow class="hover:bg-transparent">
            <TableHead
              v-for="[key, label] in sortColumns"
              :key="key"
              class="px-3 text-xs font-medium text-muted-foreground"
              :class="key === 'name' ? 'sticky left-0 z-10 bg-background' : ''"
              :aria-sort="ariaSort(key)"
            >
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-sm select-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                :class="isSorted(key) ? 'text-foreground' : ''"
                @click="sortBy(key)"
              >
                {{ t(label) }}
                <ArrowUpIcon v-if="isSorted(key) && state.sortDir === 'asc'" class="size-3.5" aria-hidden="true" />
                <ArrowDownIcon v-else-if="isSorted(key)" class="size-3.5" aria-hidden="true" />
                <ArrowUpDownIcon v-else class="size-3.5 opacity-40" aria-hidden="true" />
              </button>
            </TableHead>
            <TableHead v-if="state.columns.spark" class="px-3 text-xs font-medium text-muted-foreground">{{ t("column.spark") }}</TableHead>
            <TableHead v-if="state.columns.action" class="w-0 px-3"><span class="sr-only">{{ t("column.action") }}</span></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="node in rows"
            :key="node.id"
            class="group cursor-pointer select-none hover:bg-muted"
            :class="{ 'opacity-60': !node.enabled }"
            @click="openNode(node.id)"
          >
            <TableCell class="sticky left-0 z-10 max-w-64 bg-background px-3 transition-colors group-hover:bg-muted">
              <NodeName
                :dot="nodeDot(node)"
                :name="node.name"
                :sub="node.last_tested_at ? formatTime(node.last_tested_at) : ''"
                :activity="activity(node)"
                interactive
                @open="openNode(node.id)"
              />
            </TableCell>
            <TableCell v-if="state.columns.protocol" class="px-3"><ProtoBadge :protocol="node.protocol" /></TableCell>
            <TableCell v-if="state.columns.latency_ms" class="px-3 tabular">{{ formatMs(node.latency_ms) }}</TableCell>
            <TableCell v-if="state.columns.download_bps" class="px-3 tabular"><SpeedValue :bps="node.download_bps" /></TableCell>
            <TableCell v-if="state.columns.upload_bps" class="px-3 tabular"><SpeedValue :bps="node.upload_bps" /></TableCell>
            <TableCell v-if="state.columns.avg_latency_ms" class="px-3 tabular">{{ formatMs(node.avg_latency_ms) }}</TableCell>
            <TableCell v-if="state.columns.avg_download_bps" class="px-3 tabular"><SpeedValue :bps="node.avg_download_bps" /></TableCell>
            <TableCell v-if="state.columns.avg_upload_bps" class="px-3 tabular"><SpeedValue :bps="node.avg_upload_bps" /></TableCell>
            <!-- Ширина колонки плавает между min- и max-content полоски (6…24 столбика); 213 px — ровно RECENT_CHECKS
                 столбиков по 6 px с зазорами по 3 px, чтобы на широком экране полоска не растягивалась вслед за ячейкой. -->
            <TableCell v-if="state.columns.spark" class="px-3"><CheckBars :rows="node.spark" class="max-w-[213px]" /></TableCell>
            <TableCell v-if="state.columns.action" class="px-3 text-right">
              <Button
                variant="ghost"
                size="icon"
                :disabled="!node.supported || Boolean(running)"
                :aria-label="t('source.check', { name: node.name })"
                @click.stop="checkNode(node)"
              >
                <PlayIcon aria-hidden="true" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <ul v-else class="flex flex-col gap-2">
      <li
        v-for="node in rows"
        :key="node.id"
        class="flex flex-col gap-3 rounded-xl border p-3"
        :class="{ 'opacity-60': !node.enabled }"
      >
        <div class="flex items-start justify-between gap-2">
          <NodeName
            :dot="nodeDot(node)"
            :name="node.name"
            :sub="node.last_tested_at ? formatTime(node.last_tested_at) : ''"
            :activity="activity(node)"
            interactive
            @open="openNode(node.id)"
          />
          <ProtoBadge :protocol="node.protocol" />
        </div>
        <dl class="grid grid-cols-3 gap-2 text-sm tabular">
          <div>
            <dt class="text-xs text-muted-foreground">{{ t("column.latency") }}</dt>
            <dd>{{ formatMs(node.latency_ms) }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">{{ t("column.download") }}</dt>
            <dd><SpeedValue :bps="node.download_bps" /></dd>
          </div>
          <div>
            <dt class="text-xs text-muted-foreground">{{ t("column.upload") }}</dt>
            <dd><SpeedValue :bps="node.upload_bps" /></dd>
          </div>
        </dl>
        <div class="flex items-center gap-3">
          <CheckBars :rows="node.spark" class="flex-1" />
          <Button
            variant="ghost"
            size="icon"
            :disabled="!node.supported || Boolean(running)"
            :aria-label="t('source.check', { name: node.name })"
            @click="checkNode(node)"
          >
            <PlayIcon aria-hidden="true" />
          </Button>
        </div>
      </li>
    </ul>
  </section>
</template>
