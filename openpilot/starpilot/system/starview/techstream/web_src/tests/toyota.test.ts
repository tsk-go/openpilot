import { describe, expect, it } from "vitest";
import {
  countdownText, ecusWithSettings, errorText, formatNumber, hexDiff, idleRemainingS, liveValueText, mileageText,
  dtcDescription, liveCards, dtcScanState, dtcStatusTags, dtcSummary, dtcSummaryText, ecuProtocolText, groupDtcs, onlineEcuText, previewRaw,
  restoreToast, scanTally, settingValueFromRaw, settingValuesAfterRawChange, sortEcusByDtcCount, sessionView, settingValueLabel,
} from "../src/lib/toyota";
import type { ToyotaLiveItem, ToyotaDtc, ToyotaDtcScan, ToyotaEcu, ToyotaLiveValue, ToyotaSession, ToyotaSetting } from "../src/lib/schema";
import { ApiError } from "../src/lib/api";

function session(over: Partial<ToyotaSession> = {}): ToyotaSession {
  return { state: "idle", idleTimeoutS: 900, ...over };
}

describe("hexDiff", () => {
  it("identical data has no differences", () => {
    const d = hexDiff("00 11", "0011");
    expect(d.before.map((b) => b.changed)).toEqual([false, false]);
    expect(d.after.map((b) => b.changed)).toEqual([false, false]);
  });

  it("marks differing bytes and normalizes to two uppercase digits", () => {
    const d = hexDiff("00ff10", "00fe10");
    expect(d.before.map((b) => b.byte)).toEqual(["00", "FF", "10"]);
    expect(d.after.map((b) => b.byte)).toEqual(["00", "FE", "10"]);
    expect(d.after.map((b) => b.changed)).toEqual([false, true, false]);
    expect(d.before.map((b) => b.changed)).toEqual([false, true, false]);
  });

  it("different lengths: extra bytes count as changed", () => {
    const d = hexDiff("0001", "000102");
    expect(d.before).toHaveLength(2);
    expect(d.after.map((b) => b.changed)).toEqual([false, false, true]);
  });

  it("empty strings give empty arrays", () => {
    expect(hexDiff("", "")).toEqual({ before: [], after: [] });
  });
});

describe("sessionView", () => {
  it("idle: can only enter, tabs disabled", () => {
    const v = sessionView(session());
    expect(v).toMatchObject({ label: "Not active", canEnter: true, canExit: false, canUseDiagnostics: false });
  });

  it("entering: nothing clickable", () => {
    expect(sessionView(session({ state: "entering" }))).toMatchObject({
      label: "Entering", canEnter: false, canExit: false, canUseDiagnostics: false,
    });
  });

  it("active: can exit, tabs enabled", () => {
    expect(sessionView(session({ state: "active" }))).toMatchObject({
      label: "Diagnostic mode", canEnter: false, canExit: true, canUseDiagnostics: true,
    });
  });

  it("idle with error: shows last failure reason, allows retrying entry and exit cleanup", () => {
    const v = sessionView(session({ state: "idle", error: "pandad not stopped" }));
    expect(v).toMatchObject({ label: "Not active", tone: "danger", canEnter: true, canExit: true, canUseDiagnostics: false, detail: "pandad not stopped" });
  });

  it("active does not show error", () => {
    expect(sessionView(session({ state: "active", error: "old error" })).detail).toBe("");
  });

  it("no session data: treated as not active but nothing is actionable", () => {
    expect(sessionView(null)).toMatchObject({ canEnter: false, canExit: false, canUseDiagnostics: false });
  });
});

describe("idleRemainingS / countdownText", () => {
  it("remaining = device idleRemainingS minus locally elapsed seconds, never below 0", () => {
    const s = session({ state: "active", idleRemainingS: 800 });
    expect(idleRemainingS(s, 0)).toBe(800);
    expect(idleRemainingS(s, 100)).toBe(700);
    expect(idleRemainingS(s, 5000)).toBe(0);
  });

  it("returns null when not active or idleRemainingS is missing", () => {
    expect(idleRemainingS(session({ state: "idle", idleRemainingS: 5 }), 1)).toBeNull();
    expect(idleRemainingS(session({ state: "active" }), 1)).toBeNull();
    expect(idleRemainingS(null, 1)).toBeNull();
  });

  it("formats as mm:ss", () => {
    expect(countdownText(0)).toBe("00:00");
    expect(countdownText(65)).toBe("01:05");
    expect(countdownText(899.4)).toBe("14:59");
  });
});

describe("errorText", () => {
  it("ApiError uses the server's error text", () => {
    expect(errorText(new ApiError("Enter diagnostic mode first", 409))).toBe("Enter diagnostic mode first");
  });
  it("plain Error uses message, anything else is stringified", () => {
    expect(errorText(new Error("boom"))).toBe("boom");
    expect(errorText("x")).toBe("x");
  });
});

describe("formatNumber", () => {
  it("rounds to the given decimals and pads with zeros", () => {
    expect(formatNumber(14.248, 2)).toBe("14.25");
    expect(formatNumber(14.2, 2)).toBe("14.20");
    expect(formatNumber(0, 1)).toBe("0.0");
  });

  it("integer part has thousands separators", () => {
    expect(formatNumber(13875, 0)).toBe("13,875");
  });
});

describe("liveValueText", () => {
  it("uses the backend text plus unit", () => {
    expect(liveValueText({ key: "k", value: 14.248, text: "14.25" }, "V")).toBe("14.25 V");
    expect(liveValueText({ key: "k", value: 0, text: "0" })).toBe("0");
  });

  it("shows — when not read or the item errored", () => {
    expect(liveValueText(undefined, "V")).toBe("—");
    expect(liveValueText({ key: "k", value: null, text: "", error: "No response" }, "V")).toBe("—");
  });
});

describe("mileageText", () => {
  const mileage: ToyotaLiveValue = { key: "m", value: 13875, text: "13875" };

  it("odometer with thousands separators + unit item text", () => {
    expect(mileageText(mileage, { key: "u", value: 2, text: "mi" })).toBe("13,875 mi");
  });

  it("defaults to km when the unit item was not read", () => {
    expect(mileageText(mileage, undefined)).toBe("13,875 km");
  });

  it("shows — when the odometer was not read", () => {
    expect(mileageText(undefined, { key: "u", value: 1, text: "km" })).toBe("—");
    expect(mileageText({ key: "m", value: null, text: "", error: "x" }, undefined)).toBe("—");
  });
});

function setting(over: Partial<ToyotaSetting>): ToyotaSetting {
  return {
    key: "k", category: "C", name: "n", ecu: "750/40", did: "2270", localId: null, byteIndex: 0, mask: "FF",
    requiresBitSupportCheck: false, options: [], numeric: null, popular: false, ...over,
  };
}

describe("settingValueLabel", () => {
  const onOff = setting({ options: [{ value: 1, label: "On" }, { value: 0, label: "Off" }] });

  it("option settings show the option label", () => {
    expect(settingValueLabel(onOff, 1)).toBe("On");
    expect(settingValueLabel(onOff, 0)).toBe("Off");
  });

  it("value not among options: shows the raw value instead of guessing", () => {
    expect(settingValueLabel(onOff, 3)).toBe("Other (raw value 3)");
  });

  it("numeric settings show the number", () => {
    expect(settingValueLabel(setting({ numeric: { min: 1, max: 11 } }), 6)).toBe("6");
  });

  it("shows — when not read", () => {
    expect(settingValueLabel(onOff, null)).toBe("—");
    expect(settingValueLabel(onOff, undefined)).toBe("—");
  });
});

describe("ecusWithSettings", () => {
  const ecu = (id: string): ToyotaEcu => ({ id, tx: id.slice(0, 3), sub: null, name: id, protocol: "uds" });

  it("keeps only ECUs with settings, in catalog order", () => {
    const ecus = [ecu("7B0"), ecu("750/40"), ecu("7C4"), ecu("750/90")];
    const settings = [setting({ ecu: "750/90" }), setting({ ecu: "750/40" }), setting({ ecu: "750/40" })];
    expect(ecusWithSettings(ecus, settings).map((e) => e.id)).toEqual(["750/40", "750/90"]);
  });
});

describe("scanTally", () => {
  it("progress = done / total regardless of each ECU's status", () => {
    expect(scanTally(["ok", "offline", "malformed", "ok"], 8)).toEqual({ done: 4, total: 8, percent: 50 });
  });

  it("not started: all 0", () => {
    expect(scanTally([], 14)).toEqual({ done: 0, total: 14, percent: 0 });
  });

  it("progress is 0 when total is 0, no NaN", () => {
    expect(scanTally([], 0).percent).toBe(0);
  });
});

describe("previewRaw", () => {
  it("changes only masked bits, other bits and bytes kept as is", () => {
    // 0x5F = 0101 1111, mask 0x30 = 0011 0000, write 2 → bits 5..4 = 10 → 0110 1111 = 0x6F
    expect(previewRaw("0A5F", 1, "30", 2)).toBe("0A6F");
  });

  it("full-byte mask replaces that byte", () => {
    expect(previewRaw("0A5F", 0, "FF", 6)).toBe("065F");
  });

  it("output is uppercase without spaces", () => {
    expect(previewRaw("0a 5f", 1, "0F", 0)).toBe("0A50");
  });

  it("returns input unchanged when the byte index is out of range", () => {
    expect(previewRaw("0A", 3, "FF", 1)).toBe("0A");
  });
});

describe("dtcStatusTags", () => {
  const labels = (status: number | null) => dtcStatusTags(status).map((t) => t.label);

  it("confirmed and not current = history (0x28: bit3 + bit5)", () => {
    expect(labels(0x28)).toEqual(["History"]);
  });

  it("current + confirmed (0x09: bit0 + bit3)", () => {
    expect(labels(0x09)).toEqual(["Current", "Confirmed"]);
  });

  it("pending (0x04: bit2)", () => {
    expect(labels(0x04)).toEqual(["Pending"]);
  });

  it("all bits set (0x8D: bit0/2/3/7)", () => {
    expect(labels(0x8d)).toEqual(["Current", "Confirmed", "Pending", "MIL requested"]);
  });

  it("no relevant bits: no tags", () => {
    expect(labels(0)).toEqual([]);
  });

  it("CAN-type ECU codes have no status: shown as confirmed", () => {
    expect(labels(null)).toEqual(["Confirmed"]);
  });

  it("current and pending use warning colors, history uses neutral", () => {
    expect(dtcStatusTags(0x01)[0].tone).toBe("danger");
    expect(dtcStatusTags(0x04)[0].tone).toBe("warn");
    expect(dtcStatusTags(0x28)[0].tone).toBe("muted");
  });
});

describe("groupDtcs", () => {
  const dtc = (code: string, status: number | null): ToyotaDtc => ({ code, status, text: "" });

  it("FTB 87 non-current codes go to history comm loss, the rest stay in the list", () => {
    const g = groupDtcs([dtc("U0131-87", 0x28), dtc("U0163-87", 0x08), dtc("B1234-13", 0x28), dtc("U0100-87", 0x09)]);
    expect(g.history.map((d) => d.code)).toEqual(["U0131-87", "U0163-87"]);
    expect(g.shown.map((d) => d.code)).toEqual(["B1234-13", "U0100-87"]);
  });

  it("codes without FTB (CAN type) are not grouped", () => {
    const g = groupDtcs([dtc("B2799", null)]);
    expect(g.history).toEqual([]);
    expect(g.shown).toHaveLength(1);
  });
});

describe("dtcDescription", () => {
  it("uses the description when present, otherwise No description", () => {
    expect(dtcDescription({ code: "U0131-87", status: 0x28, text: "Lost communication with power steering control module (missing message)" }))
      .toBe("Lost communication with power steering control module (missing message)");
    expect(dtcDescription({ code: "P0A80-00", status: 0x08, text: "" })).toBe("No description");
  });
});

describe("dtcSummary / sortEcusByDtcCount / dtcSummaryText", () => {
  const scan = (ecu: string, codes: string[]): ToyotaDtcScan => ({
    ecu, status: "ok", protocol: "uds", dtcs: codes.map((code) => ({ code, status: 0x28, text: "" })),
  });
  const scans = [scan("7B0", []), scan("7C4", ["U0131-87", "U0163-87"]), scan("750/40", ["B1000-00"])];

  it("counts scanned ECUs, ECUs with faults and total DTCs", () => {
    expect(dtcSummary(scans)).toEqual({ ecuCount: 3, faultyEcuCount: 2, codeCount: 3, rejectedEcuCount: 0 });
  });

  it("sorts by DTC count descending, ties keep catalog order", () => {
    const ecus = ["7B0", "7C4", "750/40", "7C0"].map((id) => ({ id }));
    expect(sortEcusByDtcCount(ecus, scans).map((e) => e.id)).toEqual(["7C4", "750/40", "7B0", "7C0"]);
  });

  it("home page summary, three cases", () => {
    expect(dtcSummaryText(null)).toBe("Not scanned yet");
    expect(dtcSummaryText([scan("7B0", [])])).toBe("Last scan: no trouble codes found");
    expect(dtcSummaryText(scans)).toBe("Last scan: 3 DTCs in 2 ECUs");
  });

  it("ECUs that refuse DTC read don't count as fault-free: counted separately and noted in the summary", () => {
    const rejected: ToyotaDtcScan = { ecu: "7C0", status: "ok", protocol: "uds", dtcs: [], readError: "NRC 11" };
    expect(dtcSummary([...scans, rejected])).toMatchObject({ faultyEcuCount: 2, rejectedEcuCount: 1 });
    expect(dtcSummaryText([scan("7B0", []), rejected])).toBe("Last scan: no trouble codes found (1 ECU refused DTC read)");
    expect(dtcSummaryText([...scans, rejected])).toBe("Last scan: 3 DTCs in 2 ECUs (1 ECU refused DTC read)");
  });
});

describe("liveCards", () => {
  const item = (key: string, name: string, over: Partial<ToyotaLiveItem> = {}): ToyotaLiveItem =>
    ({ key, name, unit: "", options: null, needsEngineRunning: false, ...over });
  const val = (key: string, value: number | null, text: string, error?: string): ToyotaLiveValue => ({ key, value, text, error });

  it("numeric items: large text + small unit, engine-running items are flagged", () => {
    const cards = liveCards(
      [item("rpm", "Engine speed", { unit: "rpm", needsEngineRunning: true }), item("v", "12V", { unit: "V" })],
      [val("v", 14.248, "14.25"), val("rpm", 0, "0")],
    );
    expect(cards).toEqual([
      { key: "rpm", name: "Engine speed", value: "0", unit: "rpm", needsEngineRunning: true },
      { key: "v", name: "12V", value: "14.25", unit: "V", needsEngineRunning: false },
    ]);
  });

  it("odometer unit merges into the odometer card, no separate card", () => {
    const cards = liveCards(
      [item("car_tool_mileage", "Odometer (cluster reading)"), item("car_tool_mileage_unit", "Odometer unit (1 = km)")],
      [val("car_tool_mileage", 13875, "13875"), val("car_tool_mileage_unit", 1, "km")],
    );
    expect(cards).toEqual([
      { key: "car_tool_mileage", name: "Odometer (cluster reading)", value: "13,875", unit: "km", needsEngineRunning: false },
    ]);
  });

  it("item errored or not returned: shows — without unit", () => {
    const cards = liveCards([item("a", "A", { unit: "V" }), item("b", "B", { unit: "°C" })], [val("a", null, "", "No response")]);
    expect(cards.map((c) => [c.value, c.unit])).toEqual([["—", ""], ["—", ""]]);
  });
});

// Vectors from backend tests/test_toyota_coding.py::TestValueBits; both sides must extract values the same way
describe("settingValueFromRaw", () => {
  it("takes the masked bits of byte byteIndex and shifts them to the lowest bit", () => {
    expect(settingValueFromRaw("00b4", 1, "30")).toBe(3);
  });

  it("full-byte mask takes that byte", () => {
    expect(settingValueFromRaw("0A5F", 1, "FF")).toBe(0x5f);
  });

  it("raw with spaces and mixed case works", () => {
    expect(settingValueFromRaw("00 B4", 1, "30")).toBe(3);
  });

  it("multi-byte mask: only bits in byte byteIndex count, shift is by the lowest set bit", () => {
    expect(settingValueFromRaw("00b4", 1, "0F30")).toBe(3);
  });

  it("data too short: no such byte gives null", () => {
    expect(settingValueFromRaw("01", 1, "FF")).toBeNull();
  });
});

describe("settingValuesAfterRawChange", () => {
  // 750/B5 DID 2009 is shared by two settings: the high and low nibbles of byte 0
  const high = setting({ key: "high", ecu: "750/B5", did: "2009", byteIndex: 0, mask: "F0" });
  const low = setting({ key: "low", ecu: "750/B5", did: "2009", byteIndex: 0, mask: "0F" });
  const otherDid = setting({ key: "otherDid", ecu: "750/B5", did: "200A", byteIndex: 0, mask: "FF" });
  const otherEcu = setting({ key: "otherEcu", ecu: "750/40", did: "2009", byteIndex: 0, mask: "FF" });
  const all = [high, low, otherDid, otherEcu];
  const scanned = {
    high: { value: 1, raw: "12" }, low: { value: 2, raw: "12" },
    otherDid: { value: 9, raw: "09" }, otherEcu: { value: 8, raw: "08" },
  };

  it("all scanned settings on the same ECU and DID get the new raw and recomputed values; other DIDs / ECUs untouched", () => {
    expect(settingValuesAfterRawChange(all, high, "52", scanned)).toEqual({
      high: { value: 5, raw: "52" }, low: { value: 2, raw: "52" },
    });
  });

  it("unscanned sibling settings don't appear out of nowhere", () => {
    expect(settingValuesAfterRawChange(all, high, "52", { high: scanned.high })).toEqual({ high: { value: 5, raw: "52" } });
  });

  it("Toyota CAN groups by localId", () => {
    const a = setting({ key: "a", ecu: "7C0", did: null, localId: "21", byteIndex: 0, mask: "FF" });
    const b = setting({ key: "b", ecu: "7C0", did: null, localId: "21", byteIndex: 1, mask: "0F" });
    const c = setting({ key: "c", ecu: "7C0", did: null, localId: "22", byteIndex: 0, mask: "FF" });
    const known = { a: { value: 0, raw: "0000" }, b: { value: 0, raw: "0000" }, c: { value: 7, raw: "07" } };
    expect(settingValuesAfterRawChange([a, b, c], a, "0A03", known)).toEqual({
      a: { value: 10, raw: "0A03" }, b: { value: 3, raw: "0A03" },
    });
  });

  it("siblings unreadable from a too-short new raw stay as is (not written)", () => {
    const tail = setting({ key: "tail", ecu: "750/B5", did: "2009", byteIndex: 3, mask: "FF" });
    const known = { ...scanned, tail: { value: 4, raw: "12000004" } };
    expect(settingValuesAfterRawChange([high, tail], high, "52", known)).toEqual({ high: { value: 5, raw: "52" } });
  });
});

describe("dtcScanState", () => {
  const scan = (over: Partial<ToyotaDtcScan>): ToyotaDtcScan => ({ ecu: "7B0", status: "ok", protocol: "uds", dtcs: [], ...over });

  it("has DTCs → faulty", () => {
    expect(dtcScanState(scan({ dtcs: [{ code: "U0131-87", status: 0x28, text: "" }] }))).toBe("faulty");
  });

  it("good response and no codes → clear", () => {
    expect(dtcScanState(scan({}))).toBe("clear");
  });

  it("good response but ECU refused DTC read (readError) → rejected, not fault-free", () => {
    expect(dtcScanState(scan({ readError: "NRC 11" }))).toBe("rejected");
  });

  it("no response / bad response keep the scan status", () => {
    expect(dtcScanState(scan({ status: "offline", readError: "x" }))).toBe("offline");
    expect(dtcScanState(scan({ status: "malformed" }))).toBe("malformed");
  });

  it("not scanned (undefined) → unscanned", () => {
    expect(dtcScanState(undefined)).toBe("unscanned");
  });
});

describe("onlineEcuText", () => {
  it("never probed: —", () => {
    expect(onlineEcuText({})).toBe("—");
  });

  it("online / probed", () => {
    expect(onlineEcuText({ "7B0": true, "7C4": false, "750/40": true })).toBe("2 / 3");
  });
});

describe("ecuProtocolText", () => {
  it("one label per protocol", () => {
    expect(ecuProtocolText("uds")).toBe("UDS");
    expect(ecuProtocolText("toyota_can")).toBe("Toyota CAN (legacy)");
  });
});

describe("restoreToast", () => {
  it("read-back verified: ok, with setting name and restored value", () => {
    expect(restoreToast("Door open reminder", "Off", true)).toEqual({ message: "Restored \"Door open reminder\" → Off", tone: "ok" });
  });

  it("read-back verification failed: warn", () => {
    expect(restoreToast("Door open reminder", "Off", false)).toEqual({ message: "Restored, but read-back verification failed", tone: "warn" });
  });
});
