/*
 * Оценка хода проверки узла по времени. speedtest-go не сообщает прогресс посреди замера,
 * поэтому доля этапа считается от его типичной длительности, а не от переданных байтов.
 */

/* Типичная длительность этапов, с. Направление speedtest-go — 10–15 с плюс список серверов и пинг. */
const STAGE_SECONDS = { connecting: 3, traffic: 1.5, download: 15, upload: 17 };

export function nodePlan(settings) {
  const plan = ["connecting", "traffic"];
  if (settings?.measure_download !== false) plan.push("download");
  if (settings?.measure_upload !== false) plan.push("upload");
  return plan;
}

/* За типичное время этап доходит до 90%, дальше медленно ползёт к 98%: полоса не упирается в стену и не врёт о конце. */
function stageShare(elapsed, expected) {
  const ratio = Math.max(0, elapsed) / expected;
  return ratio <= 1 ? 0.9 * ratio : 0.9 + 0.08 * (1 - Math.exp(1 - ratio));
}

export function nodeFraction(stage, elapsed, plan) {
  const index = Math.max(0, plan.indexOf(stage || "connecting"));
  const total = plan.reduce((sum, name) => sum + STAGE_SECONDS[name], 0);
  const before = plan.slice(0, index).reduce((sum, name) => sum + STAGE_SECONDS[name], 0);
  const current = STAGE_SECONDS[plan[index]];
  return (before + current * stageShare(elapsed, current)) / total;
}
