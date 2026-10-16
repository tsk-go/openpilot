/** Hybrid battery assessment: voltage and internal resistance of the 12 blocks -> Healthy / Caution / Abnormal.
 *  Thresholds ported from the user-approved prototype (there are no official Toyota thresholds; judged by block-to-block spread). */
import type { ToyotaBatteryBlock, ToyotaLiveValue } from "./schema";
import { formatNumber } from "./toyota";

export type BatteryLevel = "ok" | "warn" | "danger";

/** Level -> verdict text and tone (shared by the home page badge and the battery page verdict card) */
export const BATTERY_LEVEL_LABEL: Record<BatteryLevel, { text: string; tone: "accent" | "warn" | "danger" }> = {
  ok: { text: "Healthy", tone: "accent" },
  warn: { text: "Caution", tone: "warn" },
  danger: { text: "Abnormal", tone: "danger" },
};

export interface BatteryBlockReading {
  /** Block number, starting at 1 */
  blockNumber: number;
  /** Module count: 2 for a half block, 4 for a full block */
  modules: number;
  voltage: number;
  /** mΩ */
  resistance: number;
}

export interface BatteryBlock extends BatteryBlockReading {
  /** Voltage normalized per 2 modules: unchanged for half blocks, ÷2 for full blocks */
  voltagePerTwoModules: number;
}

export interface BatteryAnalysis {
  blocks: BatteryBlock[];
  total: number;
  max: BatteryBlock;
  min: BatteryBlock;
  /** Max − min of the per-2-module voltage */
  diff: number;
  resistanceAvg: number;
  resistanceMaxBlock: BatteryBlock;
  level: BatteryLevel;
  levelReason: string;
  /** Blocks whose resistance is more than 20% above the average of their class (full / half blocks compared separately) */
  highResistanceBlocks: BatteryBlock[];
  /** Blocks whose voltage is more than 1 V below the average of the other blocks */
  lowBlocks: BatteryBlock[];
}

export const WARN_DIFF_V = 0.3;
export const DANGER_DIFF_V = 0.6;
const DANGER_LOW_V = 1;
const HIGH_RESISTANCE_RATIO = 1.2;

export function analyzeBattery(readings: BatteryBlockReading[]): BatteryAnalysis {
  const blocks = readings.map((b) => ({ ...b, voltagePerTwoModules: b.voltage / (b.modules / 2) }));
  const total = blocks.reduce((s, b) => s + b.voltage, 0);
  const voltagePerTwoModulesSum = blocks.reduce((s, b) => s + b.voltagePerTwoModules, 0);
  const max = blocks.reduce((a, b) => (b.voltagePerTwoModules > a.voltagePerTwoModules ? b : a));
  const min = blocks.reduce((a, b) => (b.voltagePerTwoModules < a.voltagePerTwoModules ? b : a));
  const diff = max.voltagePerTwoModules - min.voltagePerTwoModules;
  const lowBlocks = blocks.filter(
    (b) => (voltagePerTwoModulesSum - b.voltagePerTwoModules) / (blocks.length - 1) - b.voltagePerTwoModules >= DANGER_LOW_V,
  );
  const classAvg = (modules: number) => {
    const group = blocks.filter((b) => b.modules === modules);
    return group.reduce((s, b) => s + b.resistance, 0) / group.length;
  };
  const highResistanceBlocks = blocks.filter((b) => b.resistance > classAvg(b.modules) * HIGH_RESISTANCE_RATIO);
  const resistanceAvg = blocks.reduce((s, b) => s + b.resistance, 0) / blocks.length;
  const resistanceMaxBlock = blocks.reduce((a, b) => (b.resistance > a.resistance ? b : a));
  const diffText = formatNumber(diff, 2);

  let level: BatteryLevel = "ok";
  let levelReason = `All 12 blocks have consistent voltage (max spread ${diffText} V) and even resistance. No issues in the resting readings.`;
  if (diff > DANGER_DIFF_V || lowBlocks.length) {
    level = "danger";
    levelReason = lowBlocks.length
      ? `Block ${lowBlocks.map((b) => b.blockNumber).join(", ")} voltage is more than 1 V below the other blocks' average. Have it inspected by a dealer soon.`
      : `Block voltage spread is ${diffText} V, above 0.6 V. Have it inspected by a dealer soon.`;
  } else if (diff > WARN_DIFF_V || highResistanceBlocks.length) {
    level = "warn";
    levelReason = diff > WARN_DIFF_V
      ? `Block voltage spread is ${diffText} V, slightly high. Keep an eye on it and recheck regularly.`
      : `Block ${highResistanceBlocks.map((b) => b.blockNumber).join(", ")} resistance is more than 20% above its class average. Keep an eye on it and recheck regularly.`;
  }
  return { blocks, total, max, min, diff, resistanceAvg, resistanceMaxBlock, level, levelReason, highResistanceBlocks, lowBlocks };
}

/** Catalog block definitions + live data readings -> assessment input. Returns null if any item is missing or errored (the whole set is unusable). */
export function batteryBlocksFromValues(
  battery: { blocks: ToyotaBatteryBlock[] },
  values: ToyotaLiveValue[],
): BatteryBlockReading[] | null {
  const byKey = new Map(values.map((v) => [v.key, v]));
  const readings: BatteryBlockReading[] = [];
  for (const [i, b] of battery.blocks.entries()) {
    const voltage = byKey.get(b.voltageKey);
    const resistance = byKey.get(b.resistanceKey);
    if (voltage?.value == null || voltage.error || resistance?.value == null || resistance.error) return null;
    readings.push({ blockNumber: i + 1, modules: b.modules, voltage: voltage.value, resistance: resistance.value });
  }
  return readings;
}
