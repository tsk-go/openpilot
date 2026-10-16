import { describe, expect, it } from "vitest";
import {
  analyzeBattery, batteryBlocksFromValues, BATTERY_LEVEL_LABEL, DANGER_DIFF_V, WARN_DIFF_V, type BatteryBlockReading,
} from "../src/lib/battery";
import type { ToyotaLiveValue } from "../src/lib/schema";

// Readings from a real Sienna in Ready (prototype data.js vReady / rReady), 12 blocks: 1, 2, 11, 12 are half blocks (2 modules)
const REAL: BatteryBlockReading[] = [
  { blockNumber: 1, modules: 2, voltage: 15.249, resistance: 23 },
  { blockNumber: 2, modules: 2, voltage: 15.199, resistance: 22 },
  { blockNumber: 3, modules: 4, voltage: 30.3394, resistance: 22 },
  { blockNumber: 4, modules: 4, voltage: 30.2698, resistance: 22 },
  { blockNumber: 5, modules: 4, voltage: 30.2588, resistance: 22 },
  { blockNumber: 6, modules: 4, voltage: 30.21, resistance: 22 },
  { blockNumber: 7, modules: 4, voltage: 30.2393, resistance: 22 },
  { blockNumber: 8, modules: 4, voltage: 30.2295, resistance: 22 },
  { blockNumber: 9, modules: 4, voltage: 30.2698, resistance: 22 },
  { blockNumber: 10, modules: 4, voltage: 30.3198, resistance: 22 },
  { blockNumber: 11, modules: 2, voltage: 15.199, resistance: 23 },
  { blockNumber: 12, modules: 2, voltage: 15.2197, resistance: 23 },
];

const edit = (blockNumber: number, over: Partial<BatteryBlockReading>) =>
  REAL.map((b) => (b.blockNumber === blockNumber ? { ...b, ...over } : b));

describe("analyzeBattery: real-car readings (numbers from prototype screenshot 12-battery)", () => {
  const a = analyzeBattery(REAL);

  it("total 303.0 V, max spread 0.14 V, rated healthy", () => {
    expect(a.total).toBeCloseTo(303.0, 1);
    expect(a.diff).toBeCloseTo(0.14, 2);
    expect(a.level).toBe("ok");
    expect(a.levelReason).toBe("All 12 blocks have consistent voltage (max spread 0.14 V) and even resistance. No issues in the resting readings.");
  });

  it("highest block #1 (15.25 V), lowest block #6 (15.11 V), full-block voltage normalized per 2 modules", () => {
    expect(a.max.blockNumber).toBe(1);
    expect(a.max.voltagePerTwoModules).toBeCloseTo(15.25, 2);
    expect(a.min.blockNumber).toBe(6);
    expect(a.min.voltagePerTwoModules).toBeCloseTo(15.11, 2);
  });

  it("resistance average 22.3, max 23 mΩ", () => {
    expect(a.resistanceAvg).toBeCloseTo(22.25, 2);
    expect(a.resistanceMaxBlock.resistance).toBe(23);
  });
});

describe("analyzeBattery: abnormal / caution", () => {
  it("block 4 low by 2.4 V (1.2 V normalized): abnormal, spread 1.31 V (screenshot 14-battery-danger)", () => {
    const a = analyzeBattery(edit(4, { voltage: 30.2698 - 2.4 }));
    expect(a.level).toBe("danger");
    expect(a.diff).toBeCloseTo(1.31, 2);
    expect(a.min.blockNumber).toBe(4);
    expect(a.min.voltagePerTwoModules).toBeCloseTo(13.93, 2);
    expect(a.total).toBeCloseTo(300.6, 1);
    expect(a.lowBlocks.map((b) => b.blockNumber)).toEqual([4]);
    expect(a.levelReason).toBe("Block 4 voltage is more than 1 V below the other blocks' average. Have it inspected by a dealer soon.");
  });

  it("spread 0.3-0.6 V: caution (block 7 low by 0.9 V → normalized 15.249 − 14.66965 = 0.58 V)", () => {
    const a = analyzeBattery(edit(7, { voltage: 30.2393 - 0.9 }));
    expect(a.level).toBe("warn");
    expect(a.levelReason).toBe("Block voltage spread is 0.58 V, slightly high. Keep an eye on it and recheck regularly.");
  });

  it("spread above 0.6 V but no block 1 V below average: abnormal, explained by spread", () => {
    // Half-block voltages: 11 blocks at 15.0 V, 1 at 15.75 V, spread 0.75 V; the highest block is above average, no "low" block
    const blocks = REAL.map((b) => ({ ...b, modules: 2, voltage: b.blockNumber === 1 ? 15.75 : 15.0 }));
    const a = analyzeBattery(blocks);
    expect(a.level).toBe("danger");
    expect(a.lowBlocks).toEqual([]);
    expect(a.levelReason).toBe("Block voltage spread is 0.75 V, above 0.6 V. Have it inspected by a dealer soon.");
  });

  it("spread 0.5 V: caution", () => {
    const blocks = REAL.map((b) => ({ ...b, modules: 2, voltage: b.blockNumber === 1 ? 15.5 : 15.0 }));
    expect(analyzeBattery(blocks).level).toBe("warn");
  });

  it("full / half block resistance compared separately: block 5 at 28 mΩ (class of 8 averages 22.75, ×1.2 = 27.3) → caution", () => {
    const a = analyzeBattery(edit(5, { resistance: 28 }));
    expect(a.level).toBe("warn");
    expect(a.highResistanceBlocks.map((b) => b.blockNumber)).toEqual([5]);
    expect(a.levelReason).toBe("Block 5 resistance is more than 20% above its class average. Keep an eye on it and recheck regularly.");
  });

  it("half-block resistance 23 is above full-block 22, but each is normal within its class: no false alarm", () => {
    expect(analyzeBattery(REAL).highResistanceBlocks).toEqual([]);
  });
});

describe("batteryBlocksFromValues", () => {
  const battery = {
    ecu: "7D2",
    blocks: [
      { voltageKey: "v1", resistanceKey: "r1", modules: 2 },
      { voltageKey: "v2", resistanceKey: "r2", modules: 4 },
    ],
  };
  const val = (key: string, value: number | null, error?: string): ToyotaLiveValue => ({ key, value, text: String(value), error });

  it("numbered in catalog order, voltage and resistance taken from the matching keys", () => {
    const values = [val("r2", 22), val("v2", 30.25), val("v1", 15.25), val("r1", 23)];
    expect(batteryBlocksFromValues(battery, values)).toEqual([
      { blockNumber: 1, modules: 2, voltage: 15.25, resistance: 23 },
      { blockNumber: 2, modules: 4, voltage: 30.25, resistance: 22 },
    ]);
  });

  it("any item missing or errored: whole set unusable (returns null)", () => {
    expect(batteryBlocksFromValues(battery, [val("v1", 15.25), val("r1", 23), val("v2", 30.25)])).toBeNull();
    expect(batteryBlocksFromValues(battery, [val("v1", 15.25), val("r1", 23), val("v2", null, "No response"), val("r2", 22)])).toBeNull();
  });
});

describe("level labels and threshold constants", () => {
  it("each of the three levels has a label and tone, shared by home and battery pages", () => {
    expect(BATTERY_LEVEL_LABEL).toEqual({
      ok: { text: "Healthy", tone: "accent" },
      warn: { text: "Caution", tone: "warn" },
      danger: { text: "Abnormal", tone: "danger" },
    });
  });

  it("spread thresholds 0.3 / 0.6 V are exported for the pages", () => {
    expect([WARN_DIFF_V, DANGER_DIFF_V]).toEqual([0.3, 0.6]);
  });
});
