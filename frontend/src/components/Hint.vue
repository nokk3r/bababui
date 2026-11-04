<script setup>
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/* Подсказка в общем стиле приложения вместо системного title: обёртка над одним элементом.
   Ставится, только когда без неё непонятно: значок без подписи, обрезанный текст. Подсказка, которая
   повторяет видимую подпись или очевидный значок (корзина, крестик, ⋯), только мешает.
   Отключённая кнопка подсказку не показывает — браузер не шлёт ей события указателя. */
defineProps({
  text: { type: String, required: true },
  side: { type: String, default: "top" },
  disabled: { type: Boolean, default: false },
});
</script>

<template>
  <Tooltip :disabled="disabled">
    <TooltipTrigger as-child>
      <slot />
    </TooltipTrigger>
    <TooltipContent :side="side" class="max-w-64 text-sm">{{ text }}</TooltipContent>
  </Tooltip>
</template>
