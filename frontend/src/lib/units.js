import { reactive } from "vue";
import { readStored, writeStored } from "./storage.js";

/* API отдаёт скорость в байтах в секунду, множитель переводит её в выбранную единицу. */
export const SPEED_UNITS = {
  mbps: { label: "unit.mbps", perByte: 8 / 1e6 },
  mbytes: { label: "unit.mbytes", perByte: 1 / 1e6 },
};
const STORAGE_KEY = "bababui-speed-unit";

const saved = readStored(STORAGE_KEY);
export const units = reactive({ speed: saved in SPEED_UNITS ? saved : "mbps" });

export function setSpeedUnit(unit) {
  units.speed = unit;
  writeStored(STORAGE_KEY, unit);
}
