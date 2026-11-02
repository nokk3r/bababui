<script setup>
import { useId } from "vue";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

defineProps({
  label: { type: String, required: true },
  hint: { type: String, default: "" },
});
const model = defineModel({ type: Boolean });
const id = useId();
</script>

<template>
  <div class="flex items-start justify-between gap-4 py-3">
    <div class="min-w-0">
      <Label :for="id" class="leading-snug">{{ label }}</Label>
      <p v-if="hint" class="mt-1 text-sm text-muted-foreground">{{ hint }}</p>
    </div>
    <Switch :id="id" v-model="model" />
  </div>
</template>
