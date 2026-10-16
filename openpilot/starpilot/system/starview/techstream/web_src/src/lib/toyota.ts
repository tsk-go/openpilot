/** Pure logic for the TechStream (Toyota diagnostics) page: hex diff highlighting, session state and countdown.
 *  API and types are in schema.ts (backend: toyota_diag_api.py). */
import type { ToyotaDtc, ToyotaDtcScan, ToyotaEcu, ToyotaLiveItem, ToyotaLiveValue, ToyotaScanStatus, ToyotaSession, ToyotaSetting } from "./schema";

/** badge / text colour tones (from LANLink's diagnostics.ts, which TechStream doesn't otherwise use) */
export type Tone = "accent" | "warn" | "danger" | "muted";

/** "1 item" / "3 items" */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

// ---- Hex diff ----

export interface HexByte {
  byte: string;
  changed: boolean;
}

function toBytes(hex: string): string[] {
  const clean = hex.replace(/\s+/g, "").toUpperCase();
  return clean.match(/.{1,2}/g) ?? [];
}

/** Byte-by-byte compare of before / after; if lengths differ, the shorter side is not padded and extra bytes count as changed. */
export function hexDiff(before: string, after: string): { before: HexByte[]; after: HexByte[] } {
  const a = toBytes(before);
  const b = toBytes(after);
  const mark = (own: string[], other: string[]): HexByte[] =>
    own.map((byte, i) => ({ byte, changed: byte !== other[i] }));
  return { before: mark(a, b), after: mark(b, a) };
}

// ---- Session ----

export interface SessionView {
  label: string;
  tone: Tone;
  detail: string;
  canEnter: boolean;
  canExit: boolean;
  canUseDiagnostics: boolean;
}

/** Session state -> badge / button availability. A null session means no data yet: nothing is clickable.
 *  The backend has no error state: a failed entry returns to idle with an error, allowing retry and /exit cleanup. */
export function sessionView(session: ToyotaSession | null): SessionView {
  switch (session?.state) {
    case "entering":
      return { label: "Entering", tone: "warn", detail: "", canEnter: false, canExit: false, canUseDiagnostics: false };
    case "active":
      return { label: "Diagnostic mode", tone: "accent", detail: "", canEnter: false, canExit: true, canUseDiagnostics: true };
    case "idle":
      return session.error
        ? { label: "Not active", tone: "danger", detail: session.error, canEnter: true, canExit: true, canUseDiagnostics: false }
        : { label: "Not active", tone: "muted", detail: "", canEnter: true, canExit: false, canUseDiagnostics: false };
    default:
      return { label: "Not active", tone: "muted", detail: "", canEnter: false, canExit: false, canUseDiagnostics: false };
  }
}

/** Seconds left before idle auto-exit: the device's idleRemainingS minus the seconds elapsed locally since it was received
 *  (the browser clock is not compared with device time, to avoid clock skew between the two). */
export function idleRemainingS(session: ToyotaSession | null, elapsedS: number): number | null {
  if (session?.state !== "active" || session.idleRemainingS === undefined) return null;
  return Math.max(0, session.idleRemainingS - elapsedS);
}

export function countdownText(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Any thrown value -> message text. An ApiError's message is already the server's {"error"} text. */
export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** Number display: fixed decimals, thousands separators in the integer part (odometer). */
export function formatNumber(n: number, digits: number): string {
  return n.toLocaleString("zh-CN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// ---- Live data display ----

export const BATTERY_12V_KEY = "car_tool_battery_voltage_engine";
export const MILEAGE_KEY = "car_tool_mileage";
export const MILEAGE_UNIT_KEY = "car_tool_mileage_unit";

/** The three items read for the home page vehicle card: 12V voltage, odometer, odometer unit */
export const HOME_LIVE_KEYS = [BATTERY_12V_KEY, MILEAGE_KEY, MILEAGE_UNIT_KEY] as const;

/** Display text for one live data item: the backend formats the number per the catalog precision (text); this only appends the unit. */
export function liveValueText(v: ToyotaLiveValue | undefined, unit = ""): string {
  if (!v || v.error || v.value === null) return "—";
  return unit ? `${v.text} ${unit}` : v.text;
}

/** The odometer unit is merged into the odometer card: the unit is a separate live data item (1 = km, 2 = mi); defaults to km if unreadable */
function mileageParts(mileage: ToyotaLiveValue | undefined, unit: ToyotaLiveValue | undefined): { value: string; unit: string } | null {
  if (!mileage || mileage.error || mileage.value === null) return null;
  return { value: formatNumber(mileage.value, 0), unit: unit?.text || "km" };
}

export function mileageText(mileage: ToyotaLiveValue | undefined, unit: ToyotaLiveValue | undefined): string {
  const parts = mileageParts(mileage, unit);
  return parts ? `${parts.value} ${parts.unit}` : "—";
}

// ---- Customization ----

export function ecuProtocolText(protocol: ToyotaEcu["protocol"]): string {
  return protocol === "toyota_can" ? "Toyota CAN (legacy)" : "UDS";
}

/** Toast after a successful undo / backup restore: warn if read-back verification failed instead of reporting "Restored". */
export function restoreToast(settingName: string, restoredLabel: string, verified: boolean): { message: string; tone: "ok" | "warn" } {
  return verified
    ? { message: `Restored "${settingName}" → ${restoredLabel}`, tone: "ok" }
    : { message: "Restored, but read-back verification failed", tone: "warn" };
}

/** Display text for a setting's current value: option label for option settings, the number itself for numeric settings. */
export function settingValueLabel(setting: ToyotaSetting, value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (setting.numeric) return String(value);
  return setting.options.find((o) => o.value === value)?.label ?? `Other (raw value ${value})`;
}

/** A customization scan only needs to query ECUs that have settings (querying others just waits out a timeout); keeps catalog order. */
export function ecusWithSettings(ecus: ToyotaEcu[], settings: ToyotaSetting[]): ToyotaEcu[] {
  const used = new Set(settings.map((s) => s.ecu));
  return ecus.filter((e) => used.has(e.id));
}

// ---- Scan progress ----

/** Home page "Online ECUs": responded / probed (customization and DTC scans probe different ECU sets, so responses are tracked per ECU for consistency). */
export function onlineEcuText(ecuAnswered: Record<string, boolean>): string {
  const probed = Object.values(ecuAnswered);
  return probed.length ? `${probed.filter(Boolean).length} / ${probed.length}` : "—";
}

export interface ScanTally {
  done: number;
  total: number;
  percent: number;
}

/** Per-ECU scan progress: how many scanned, how many total; percent is for the progress bar. */
export function scanTally(statuses: ToyotaScanStatus[], total: number): ScanTally {
  return { done: statuses.length, total, percent: total ? (statuses.length / total) * 100 : 0 };
}

/** Expected full data after a write (hex-compared with the current raw value in technical details):
 *  shifts value left to the mask's lowest set bit and replaces only the masked bits of byte byteIndex. */
export function previewRaw(raw: string, byteIndex: number, mask: string, value: number): string {
  const bytes = raw.replace(/\s+/g, "").toUpperCase().match(/.{1,2}/g) ?? [];
  if (byteIndex >= bytes.length) return bytes.join("");
  const m = parseInt(mask, 16);
  const shift = Math.log2(m & -m);
  const next = (parseInt(bytes[byteIndex], 16) & ~m) | ((value << shift) & m);
  bytes[byteIndex] = next.toString(16).toUpperCase().padStart(2, "0");
  return bytes.join("");
}

/** Extracts a setting's value from the full raw data, with the same semantics as extract_value in backend toyota/coding.py:
 *  the masked bits of byte byteIndex shifted down to the lowest bit. Returns null if the data has no such byte. */
export function settingValueFromRaw(raw: string, byteIndex: number, mask: string): number | null {
  const bytes = toBytes(raw);
  if (byteIndex >= bytes.length) return null;
  const maskBits = parseInt(mask, 16);
  const shift = Math.log2(maskBits & -maskBits);
  return (parseInt(bytes[byteIndex], 16) & maskBits) >> shift;
}

/** Settings on the same ECU and same DID (UDS) / localId (Toyota CAN) share one raw block.
 *  After `changed` is written or restored the whole block becomes newRaw: returns the new {value, raw} for every scanned setting in that block.
 *  Settings whose value can't be read from the new raw are not returned (left as is). */
export function settingValuesAfterRawChange(
  settings: ToyotaSetting[],
  changed: ToyotaSetting,
  newRaw: string,
  scannedValues: Record<string, { value: number; raw: string }>,
): Record<string, { value: number; raw: string }> {
  const sharesData = (s: ToyotaSetting) => s.ecu === changed.ecu && (s.did ?? s.localId) === (changed.did ?? changed.localId);
  const updated: Record<string, { value: number; raw: string }> = {};
  for (const s of settings.filter(sharesData)) {
    const value = settingValueFromRaw(newRaw, s.byteIndex, s.mask);
    if (s.key in scannedValues && value !== null) updated[s.key] = { value, raw: newRaw };
  }
  return updated;
}

// ---- Trouble codes ----

export interface DtcTag {
  label: string;
  tone: Tone;
}

/** UDS status byte -> tags: bit0 current, bit2 pending, bit3 confirmed, bit7 MIL requested;
 *  confirmed and not current = history. Toyota CAN codes have no status (null) and are treated as confirmed. */
export function dtcStatusTags(status: number | null): DtcTag[] {
  if (status === null) return [{ label: "Confirmed", tone: "muted" }];
  const current = (status & 0x01) !== 0;
  const pending = (status & 0x04) !== 0;
  const confirmed = (status & 0x08) !== 0;
  const mil = (status & 0x80) !== 0;
  const tags: DtcTag[] = [];
  if (current) tags.push({ label: "Current", tone: "danger" });
  if (confirmed && current) tags.push({ label: "Confirmed", tone: "danger" });
  if (pending) tags.push({ label: "Pending", tone: "warn" });
  if (confirmed && !current) tags.push({ label: "History", tone: "muted" });
  if (mil) tags.push({ label: "MIL requested", tone: "warn" });
  return tags;
}

/** Groups an ECU's "FTB 87 (missing message) and not current" codes together: usually history left over from unplugging harnesses or a power loss. */
export function groupDtcs(dtcs: ToyotaDtc[]): { shown: ToyotaDtc[]; history: ToyotaDtc[] } {
  const isHistoryLoss = (d: ToyotaDtc) => d.code.endsWith("-87") && d.status !== null && (d.status & 0x01) === 0;
  return { shown: dtcs.filter((d) => !isHistoryLoss(d)), history: dtcs.filter(isHistoryLoss) };
}

export function dtcDescription(d: ToyotaDtc): string {
  return d.text || "No description";
}

export type DtcScanState = ToyotaScanStatus | "faulty" | "clear" | "rejected" | "unscanned";

/** Display state of one ECU's DTC scan result. When an ECU refuses the DTC read the backend still returns status "ok", with only readError and empty dtcs,
 *  so it must not be shown as "No faults". undefined = this ECU was not scanned. */
export function dtcScanState(scan: ToyotaDtcScan | undefined): DtcScanState {
  if (!scan) return "unscanned";
  if (scan.status !== "ok") return scan.status;
  if (scan.readError) return "rejected";
  return scan.dtcs.length ? "faulty" : "clear";
}

export function dtcSummary(scans: ToyotaDtcScan[]): { ecuCount: number; faultyEcuCount: number; codeCount: number; rejectedEcuCount: number } {
  return {
    ecuCount: scans.length,
    faultyEcuCount: scans.filter((s) => s.dtcs.length > 0).length,
    codeCount: scans.reduce((n, s) => n + s.dtcs.length, 0),
    rejectedEcuCount: scans.filter((s) => dtcScanState(s) === "rejected").length,
  };
}

/** ECUs with more DTCs come first; ties keep catalog order (stable sort). Unscanned ECUs count as 0. */
export function sortEcusByDtcCount<T extends { id: string }>(ecus: T[], scans: ToyotaDtcScan[]): T[] {
  const count = (id: string) => scans.find((s) => s.ecu === id)?.dtcs.length ?? 0;
  return [...ecus].sort((a, b) => count(b.id) - count(a.id));
}

/** Caption for the home page "Trouble codes" entry; null scans means no scan yet */
export function dtcSummaryText(scans: ToyotaDtcScan[] | null): string {
  if (!scans) return "Not scanned yet";
  const { faultyEcuCount, codeCount, rejectedEcuCount } = dtcSummary(scans);
  const rejectedNote = rejectedEcuCount ? ` (${plural(rejectedEcuCount, "ECU")} refused DTC read)` : "";
  return (codeCount ? `Last scan: ${plural(codeCount, "DTC")} in ${plural(faultyEcuCount, "ECU")}` : "Last scan: no trouble codes found") + rejectedNote;
}

export interface LiveCard {
  key: string;
  name: string;
  value: string;
  unit: string;
  needsEngineRunning: boolean;
}

/** Data cards for one topic page: in items order; the odometer unit item is merged into the odometer card rather than shown separately; unreadable items show —. */
export function liveCards(items: ToyotaLiveItem[], values: ToyotaLiveValue[]): LiveCard[] {
  const byKey = new Map(values.map((v) => [v.key, v]));
  return items
    .filter((it) => it.key !== MILEAGE_UNIT_KEY)
    .map((it) => {
      const v = byKey.get(it.key);
      const base = { key: it.key, name: it.name, needsEngineRunning: it.needsEngineRunning };
      if (!v || v.error || v.value === null) return { ...base, value: "—", unit: "" };
      if (it.key === MILEAGE_KEY) return { ...base, ...mileageParts(v, byKey.get(MILEAGE_UNIT_KEY))! };
      return { ...base, value: v.text, unit: it.unit };
    });
}
