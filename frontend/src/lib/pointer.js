/* Второй и следующие клики не должны выделять текст: сортировка и строки остаются нажатиями. */
export function suppressRepeatSelection(event) {
  if (event.detail <= 1) return;
  event.preventDefault();
}
