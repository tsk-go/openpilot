import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn-vue style class merge helper */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** A few units in the schema are English words rather than symbols ("second", "meters"),
 *  which look awkward right after a number ("0second"). Only the display changes, not the schema. */
const UNIT_LABELS: Record<string, string> = {
  second: "s",
  seconds: "s",
  meters: "m",
  meter: "m",
};

/** Unit resolution: a string or {metric, imperial}; the latter follows IsMetric.
 *
 * Both forms appear in the real schema (CameraOffset uses "meters",
 * BlinkerMinLateralControlSpeed uses {metric:"km/h", imperial:"mph"}).
 */
export function resolveUnit(
  unit: string | { metric: string; imperial: string } | undefined,
  metric: boolean,
): string {
  if (!unit) return "";
  const raw = typeof unit === "string" ? unit : metric ? unit.metric : unit.imperial;
  return UNIT_LABELS[raw] ?? raw;
}

/** Slider value display: decimals inferred from step, avoiding 0.30000000000000004 */
export function formatSliderValue(value: number, step: number | undefined): string {
  const s = step ?? 1;
  if (Number.isInteger(s) && Number.isInteger(value)) return String(value);
  const decimals = (String(s).split(".")[1] ?? "").length;
  return value.toFixed(decimals);
}

/** Whether an option value equals the raw string stored on the device. Numeric options compare as numbers: 1.0 in the schema
 *  becomes "1" in JS while the device stores "1.0", so a string compare never matches (selection not highlighted). */
export function optionMatches(optValue: number | string, raw: string): boolean {
  if (String(optValue) === raw) return true;
  if (raw === "" || optValue === "") return false;
  return Number(optValue) === Number(raw);
}
