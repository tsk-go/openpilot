/** Data shared by the TechStream pages: the catalog and the results of each scan.
 *
 * Kept in a module because the page stack destroys pages you leave: going back from a category subpage to the Customize page must not rescan.
 * After exiting diagnostic mode (or an idle timeout) resetScanData() clears all scan results, since values in the car may have been changed elsewhere.
 */
import { reactive } from "vue";
import { api, ApiError } from "./api";
import type { BatteryAnalysis } from "./battery";
import type { ToyotaCatalog, ToyotaDtcScan, ToyotaEcu, ToyotaScanStatus, ToyotaSetting } from "./schema";
import { ecusWithSettings, errorText, settingValuesAfterRawChange } from "./toyota";

export const toyotaData = reactive({
  catalog: null as ToyotaCatalog | null,
  catalogError: "",
  /** ECU id → whether it responded to the latest probe (updated by both customization and DTC scans); ECUs never probed are not in the map */
  ecuAnswered: {} as Record<string, boolean>,
  customization: {
    state: "idle" as "idle" | "scanning" | "done",
    /** Status of ECUs scanned so far; length = number done */
    statuses: [] as ToyotaScanStatus[],
    /** ECUs with no response / bad response, used after the scan to explain to the user why items are missing */
    unreachable: [] as ToyotaEcu[],
    /** Setting key → current value and the raw data at scan time (sent as `before` on write to verify the ECU data wasn't changed elsewhere) */
    values: {} as Record<string, { value: number; raw: string }>,
    /** StarView: also list items the ECUs didn't report as supported, so they can be tried */
    showUnlisted: false,
    /** keys read with "Try reading" although the ECU didn't list them */
    probed: {} as Record<string, boolean>,
  },
  dtc: {
    state: "idle" as "idle" | "scanning" | "done",
    /** DTCs of the ECUs scanned so far, in catalog order */
    scans: [] as ToyotaDtcScan[],
  },
  battery: {
    /** Latest assessment; null if never read or the reading was incomplete */
    analysis: null as BatteryAnalysis | null,
  },
});

let catalogLoading = false;

export async function loadCatalog(): Promise<void> {
  if (catalogLoading || toyotaData.catalog) return;
  catalogLoading = true;
  toyotaData.catalogError = "";
  try {
    toyotaData.catalog = await api.toyotaCatalog();
  } catch (e) {
    toyotaData.catalogError = errorText(e);
  } finally {
    catalogLoading = false;
  }
}

/** Total number of ECUs to scan (only those with settings) */
export function customizationScanTotal(): number {
  const c = toyotaData.catalog;
  return c ? ecusWithSettings(c.ecus, c.settings).length : 0;
}

/** Session gone (exit or idle timeout): a partial scan must not be shown as a scan result */
function isSessionGone(e: unknown): boolean {
  return e instanceof ApiError && e.status === 409;
}

/** Reads current setting values ECU by ECU. A single ECU failure is recorded and the scan continues; if the session is gone (409) it aborts and the scan is discarded (back to idle). */
export async function scanCustomizations(): Promise<void> {
  const catalog = toyotaData.catalog;
  const c = toyotaData.customization;
  if (!catalog || c.state === "scanning") return;
  c.state = "scanning";
  c.statuses = [];
  c.unreachable = [];
  c.values = {};
  c.probed = {};
  for (const ecu of ecusWithSettings(catalog.ecus, catalog.settings)) {
    try {
      const r = await api.toyotaScanCustomizations(ecu.id);
      c.statuses.push(r.status);
      toyotaData.ecuAnswered[ecu.id] = r.status === "ok";
      if (r.status !== "ok") c.unreachable.push(ecu);
      for (const it of r.items) c.values[it.key] = { value: it.value, raw: it.raw };
    } catch (e) {
      if (isSessionGone(e)) {
        c.state = "idle";
        return;
      }
      c.statuses.push("offline");
      toyotaData.ecuAnswered[ecu.id] = false;
      c.unreachable.push(ecu);
    }
  }
  c.state = "done";
}

/** Reads DTCs ECU by ECU (all 41). Failed ECUs are recorded as no response and the scan continues; if the session is gone (409) it aborts and the scan is discarded (back to idle). */
export async function scanDtcs(): Promise<void> {
  const catalog = toyotaData.catalog;
  const d = toyotaData.dtc;
  if (!catalog || d.state === "scanning") return;
  d.state = "scanning";
  d.scans = [];
  for (const ecu of catalog.ecus) {
    try {
      d.scans.push(await api.toyotaScanDtc(ecu.id));
    } catch (e) {
      if (isSessionGone(e)) {
        d.state = "idle";
        return;
      }
      d.scans.push({ ecu: ecu.id, status: "offline", protocol: ecu.protocol, dtcs: [] });
    }
    toyotaData.ecuAnswered[ecu.id] = d.scans[d.scans.length - 1].status === "ok";
  }
  d.state = "done";
}

/** StarView: read one unlisted item directly. On success it joins the scan values (so the normal sheet / write path works);
 *  an ECU that doesn't have it throws ApiError (404 "... doesn't have this setting"). Nothing is written. */
export async function probeSetting(key: string): Promise<void> {
  const r = await api.toyotaProbe(key);
  const c = toyotaData.customization;
  c.values[key] = { value: r.value, raw: r.raw };
  c.probed[key] = true;
}

/** ECUs that cleared successfully get their list emptied locally; whether codes were really cleared, or the fault is still present, takes a rescan to know */
export async function clearDtcs(ecuIds: string[]): Promise<{ ecu: string; ok: boolean; error?: string }[]> {
  const { results } = await api.toyotaClearDtc(ecuIds);
  for (const r of results) {
    const scan = toyotaData.dtc.scans.find((s) => s.ecu === r.ecu);
    if (r.ok && scan) scan.dtcs = [];
  }
  return results;
}

/** After a write / undo the ECU's whole data block becomes afterRaw: sibling settings on the same ECU and DID / localId are updated too,
 *  otherwise their raw goes stale and the next write is rejected by the backend as changed data (409). */
export function applyWriteResult(setting: ToyotaSetting, afterRaw: string): void {
  const c = toyotaData.customization;
  Object.assign(c.values, settingValuesAfterRawChange(toyotaData.catalog?.settings ?? [], setting, afterRaw, c.values));
}

/** Invalidates the scan: something other than a write (a backup restore) changed values in the car, so the Customize page rescans next time */
export function invalidateCustomizationScan(): void {
  toyotaData.customization.state = "idle";
}

export function resetScanData(): void {
  toyotaData.ecuAnswered = {};
  const c = toyotaData.customization;
  c.state = "idle";
  c.statuses = [];
  c.unreachable = [];
  c.values = {};
  c.probed = {};
  toyotaData.dtc.state = "idle";
  toyotaData.dtc.scans = [];
  toyotaData.battery.analysis = null;
}
