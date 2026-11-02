<script setup>
import { removeToast, state } from "../store.js";

function ended(item) {
  if (item.leaving) removeToast(item.id);
}
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <div
      v-for="item in state.toasts"
      :key="item.id"
      class="toast"
      :class="{ 'is-out': item.leaving }"
      @animationend="ended(item)"
    >{{ item.message }}</div>
  </div>
</template>
