/** API client.
 *
 * Backend contract: see ROUTES in lanlinkd.py. Key points:
 *  - No auth: single user on the LAN accesses it directly (no Authorization header, no login page)
 *  - Successful writes return 204 with no body; errors return {"error": "..."}
 *  - A blocked param returns 403 instead of being silently skipped (unlike upstream, see FRONTEND_SPEC.md §1)
 */
import type {
  BluetoothStatus, Capabilities, DiagnosticsReport, ParamValues, SettingsSchema,
  SoftwareStatus, StatusSnapshot, ToyotaBackup, ToyotaCatalog, ToyotaCustomizationScan, ToyotaDtcClearResult,
  ToyotaDtcScan, ToyotaLiveValue, ToyotaSession, ToyotaWriteResult, VehicleState, WifiStatus,
} from "./schema";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** StarView: starviewd wants the tablet's session pass on every API call. The StarView app gives the page a fresh one
 *  through its JavaScript bridge (window.StarView.session()); the ?s= the page was opened with is the fallback. */
function sessionPass(): string {
  try {
    const bridge = (window as unknown as { StarView?: { session?: () => string } }).StarView;
    const s = bridge?.session?.();
    if (s) return s;
  } catch {
    /* no bridge (plain browser) */
  }
  return new URLSearchParams(location.search).get("s") ?? "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const pass = sessionPass();
  if (pass) headers["X-StarView-Session"] = pass;

  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers as object) } });

  if (res.status === 204) return null as T;

  const body = await res.json().catch(() => ({}) as Record<string, unknown>);
  if (!res.ok) {
    const msg = typeof body.error === "string" ? body.error : `HTTP ${res.status}`;
    throw new ApiError(msg, res.status);
  }
  return body as T;
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  // ---- Bulk reads (like upstream getParams / getParamsMetadata) ----
  settingsUi: () => request<SettingsSchema>("/api/settings_ui"),
  capabilities: () => request<Capabilities>("/api/capabilities"),
  allParams: () => request<ParamValues>("/api/params/_all"),
  status: () => request<StatusSnapshot>("/api/status"),
  // The diagnostics page polls separately, not merged into /api/status
  diagnostics: () => request<DiagnosticsReport>("/api/diagnostics"),

  // ---- Single-key write ----
  putParam: (key: string, value: string) =>
    request<null>(`/api/params/${encodeURIComponent(key)}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    }),
  getParam: (key: string) => request<{ value: string }>(`/api/params/${encodeURIComponent(key)}`),

  // ---- vehicle ----
  vehicle: () => request<VehicleState>("/api/vehicle"),
  // Empty name = clear the manual selection and go back to auto-detect
  selectVehicle: (name: string) => post<null>("/api/vehicle/select", { name }),

  // ---- bluetooth ----
  // On 503 the body is a degraded snapshot derived from params; request throws ApiError (message is the error field)
  bluetooth: () => request<BluetoothStatus>("/api/bluetooth"),
  // Operation names match backend OPERATIONS: power/scan/stop_scan/pair/connect/disconnect/
  // forget/select_audio/test_audio/pairing_response
  bluetoothOp: (operation: string, body?: Record<string, unknown>) =>
    post<{ message?: string; audio_test_delay_ms?: number }>(
      `/api/bluetooth/${encodeURIComponent(operation)}`, body),

  // ---- wifi ----
  wifi: () => request<WifiStatus>("/api/wifi"),
  wifiOp: (operation: string, body: Record<string, unknown>) =>
    post<Record<string, unknown>>(`/api/wifi/${encodeURIComponent(operation)}`, body),

  // ---- software (updater) ----
  software: () => request<SoftwareStatus>("/api/software"),
  softwareOp: (action: string) =>
    post<null>(`/api/software/${encodeURIComponent(action)}`),

  // ---- Toyota diagnostics (outside diagnostic mode everything except session, catalog, backups returns 409 {"error": ...}) ----
  toyotaSession: () => request<ToyotaSession>("/api/toyota/session"),
  toyotaEnter: () => post<ToyotaSession>("/api/toyota/session/enter"),
  toyotaExit: () => post<null>("/api/toyota/session/exit"),
  toyotaCatalog: () => request<ToyotaCatalog>("/api/toyota/catalog"),
  // Scans are called one ECU at a time by the frontend, following the catalog ECU list
  toyotaScanCustomizations: (ecu: string) => post<ToyotaCustomizationScan>("/api/toyota/customizations/scan", { ecu }),
  toyotaWrite: (key: string, value: number, before: string) =>
    post<ToyotaWriteResult>(`/api/toyota/customizations/${encodeURIComponent(key)}/write`, { value, before }),
  toyotaBackups: () => request<{ backups: ToyotaBackup[] }>("/api/toyota/backups"),
  toyotaRestore: (id: string) =>
    post<ToyotaWriteResult>(`/api/toyota/backups/${encodeURIComponent(id)}/restore`),
  toyotaScanDtc: (ecu: string) => post<ToyotaDtcScan>("/api/toyota/dtc/scan", { ecu }),
  toyotaClearDtc: (ecus: string[]) =>
    post<{ results: ToyotaDtcClearResult[] }>("/api/toyota/dtc/clear", { ecus }),
  toyotaReadLive: (keys: string[]) => post<{ values: ToyotaLiveValue[] }>("/api/toyota/live/read", { keys }),

  // ---- logs ----
  logs: () => request<unknown>("/api/logs"),
};
