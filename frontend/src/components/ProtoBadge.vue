<script setup>
import { Badge } from "@/components/ui/badge";
import { protocolName } from "../lib/format.js";

const COLORS = {
  vless: "text-sky-700 dark:text-sky-300",
  vmess: "text-violet-700 dark:text-violet-300",
  trojan: "text-rose-700 dark:text-rose-300",
  shadowsocks: "text-neutral-600 dark:text-neutral-300",
  hysteria2: "text-emerald-700 dark:text-emerald-300",
  wireguard: "text-orange-700 dark:text-orange-300",
};

defineProps({ protocol: { type: String, required: true } });
</script>

<template>
  <Badge variant="outline" :class="COLORS[protocol]">{{ protocolName(protocol) }}</Badge>
</template>
