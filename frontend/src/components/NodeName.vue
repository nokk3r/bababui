<script setup>
defineProps({
  dot: { type: String, required: true },
  name: { type: String, required: true },
  sub: { type: String, default: "" },
});
</script>

<template>
  <div class="name">
    <b><i class="dot" :class="dot"></i>{{ name }}</b>
    <span class="sub">{{ sub }}</span>
  </div>
</template>
