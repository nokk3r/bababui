<script setup>
import { protocolName } from "../lib/format.js";

defineProps({ protocol: { type: String, required: true } });
</script>

<template>
  <span class="proto" :class="`proto-${protocol}`">{{ protocolName(protocol) }}</span>
</template>
