/** Type definitions for settings_ui.json.
 *
 * Shape taken from the measured schema (locally 9 panels / 71 items, rule structure same as upstream).
 * Key point: sliders have **no** separate widget type: upstream page.schema.json's
 * widget enum only has toggle/option/multiple_button/button/info, and `option` forks
 * into a slider or a dropdown depending on whether it has min/max/step. See FRONTEND_SPEC.md §3.
 */

export type Widget = "toggle" | "option" | "multiple_button" | "button" | "info";

export interface Rule {
  type:
    | "param"
    | "param_compare"
    | "capability"
    | "offroad_only"
    | "not_engaged"
    | "any"
    | "all"
    | "not";
  key?: string;
  field?: string;
  equals?: unknown;
  op?: "<" | "<=" | ">" | ">=" | "==" | "!=";
  value?: number;
  condition?: Rule;
  conditions?: Rule[];
}

export interface OptionChoice {
  value: number | string;
  label: string;
  enablement?: Rule[];
  visibility?: Rule[];
}

/** Unit: a string ("meters") or split by unit system (follows IsMetric) */
export type Unit = string | { metric: string; imperial: string };

export interface Item {
  key: string;
  widget: Widget;
  title: string;
  description?: string;
  /** Long warning text (e.g. the usage notes for AutoLaneChangeTimer) */
  details?: string;
  /** Title suffix that changes with another param, e.g. "(Real-Time & Offline)" / "(Offline Only)" */
  title_param_suffix?: { param: string; values: Record<string, string> };
  options?: OptionChoice[];
  min?: number;
  max?: number;
  step?: number;
  unit?: Unit;
  /** Inline expandable child settings (shown when the parent is on), e.g. BlinkerPauseLateralControl */
  sub_items?: Item[];
  enablement?: Rule[];
  visibility?: Rule[];
  /** Items the schema declares as not remotely changeable (AdbEnabled/SshEnabled); the backend also returns 403 */
  blocked?: boolean;
  /** Takes effect only after a power cycle */
  needs_onroad_cycle?: boolean;
  /** Injected by the backend's settings.mark_missing_keys: this param does not exist on the device.
   *  Note the underscore prefix, matching the output of settings.py. */
  _missing?: boolean;
}

export interface SubPanel {
  id: string;
  label: string;
  /** Prerequisite toggle for the drawer; a null trigger_condition means it can always be opened */
  trigger_key?: string;
  trigger_condition?: Rule | null;
  items: Item[];
}

export interface Section {
  id?: string;
  title?: string;
  description?: string;
  items?: Item[];
  sub_panels?: SubPanel[];
  enablement?: Rule[];
  visibility?: Rule[];
}

export interface Panel {
  id: string;
  label: string;
  icon?: string;
  order?: number;
  description?: string;
  /** Marked by upstream as cloud-configurable; only displayed locally */
  remote_configurable?: boolean;
  sections: Section[];
}

/** Car-specific settings grouped by brand, chosen by capabilities.brand */
export interface VehicleBrandSettings {
  title: string;
  items: Item[];
}

export interface SettingsSchema {
  schema_version: string;
  panels: Panel[];
  vehicle_settings?: Record<string, VehicleBrandSettings>;
}

/** /api/capabilities: 19 fields, see status_snapshot.build_capabilities */
export type Capabilities = Record<string, string | number | boolean>;

/** /api/params/_all: key -> canonical string (BOOL is "1"/"0") */
export type ParamValues = Record<string, string>;

/** /api/status snapshot (declares only the fields the frontend actually uses).
 *
 * Of the three telemetry groups device / car / gps, car and gps are still deliberately not modeled: that data is
 * already on the car screen. device is modeled for the "Status" page (CPU/GPU load and temperature),
 * with fields following the device section of status_snapshot.build_snapshot().
 *
 * Polling itself can't stop: paramsVersion is the only way to notice settings changed on the car screen.
 */
export interface DeviceStatus {
  /** Onroad state as decided by manager (hardwared's started bit), unrelated to ignition */
  started?: boolean;
  /** cereal NetworkType enum (0 none / 1 wifi / … / 6 ethernet) */
  networkType?: number;
  cpuTempC?: number[];
  gpuTempC?: number[];
  memoryTempC?: number;
  maxTempC?: number;
  memoryUsagePercent?: number;
  cpuUsagePercent?: number[];
  gpuUsagePercent?: number;
  freeSpacePercent?: number;
  powerDrawW?: number;
  fanSpeedPercentDesired?: number;
  thermalStatus?: number; // 0 ok / 2 overheated / 3 critical
}

/** Last N frames of modelV2.big: 1 = frame from the big model, 0 = small-model fallback; oldest first */
export interface ModelStatus {
  bigEnabled?: boolean;
  linkState?: string; // BigmodelLinkState: connecting/connected/blip/restart/lost
  frames?: number[];
  timing?: ModelTiming;
}

export interface P50P90 {
  p50: number;
  p90: number;
}

/** Last N frames of C4 on-device timing breakdown (from eof, chained along the critical path, total = until modeld receives it) and small-model reason counts */
export interface ModelTiming {
  window: number;
  stagesMs: Record<
    "capture" | "warp" | "pairWait" | "encode" | "send" | "replyWait" | "network" | "total",
    P50P90
  > | null;
  sources: Record<"off" | "big" | "warmup" | "linkDown" | "timeout" | "late" | "zeroOutput", number>;
  deadlineMs: number | null;
}

/** Auto-tune result for one speed bin (m/s); calPerc is that bin's learning progress (null for old caches without this field) */
export interface TorqueBin {
  center: number;
  lo: number;
  hi: number;
  latAccelFactor: number;
  friction: number;
  valid: boolean;
  calPerc: number | null;
}

/** torqued's lateralTorqueParameters (live message or the LiveTorqueParameters cache on disk) */
export interface TorqueLearned {
  valid: boolean;
  useParams: boolean;
  latAccelFactor: number;
  friction: number;
  latAccelOffset: number;
  latAccelFactorRaw: number;
  frictionRaw: number;
  calPerc: number;
  totalPoints: number;
  decay: number;
  resets: number;
  bins: TorqueBin[];
}

/** Lateral torque auto-tune card (status_snapshot.build_torque_status) */
export interface TorqueStatus {
  source: "live" | "cache" | "none";
  learned: TorqueLearned | null;
  offline: { lateralControl: string; latAccelFactor: number | null; friction: number | null };
  toggles: { EnforceTorqueControl: boolean; LiveTorqueParamsToggle: boolean; SpeedDependentTorqueToggle: boolean };
}

export interface StatusSnapshot {
  stale?: boolean;
  paramsVersion?: string | null;
  system?: { version?: string; branch?: string; commit?: string; ignition?: boolean };
  device?: DeviceStatus;
  model?: ModelStatus;
  torque?: TorqueStatus;
  capabilities?: Capabilities;
}

/** Vehicle fingerprint state (GET /api/vehicle, see vehicle_api.vehicle_state) */
export interface VehicleState {
  /** manual = selected by the user; auto = automatic fingerprinting; none = not identified */
  source: "manual" | "auto" | "none";
  name: string;
  platform: string;
  brand: string;
  fingerprinted: boolean;
  detected: {
    platform?: string;
    brand?: string;
    vin?: string;
    steer_control_type?: string;
    pcm_cruise?: boolean;
    openpilot_longitudinal?: boolean;
    alpha_long_available?: boolean;
    enable_bsm?: boolean;
    radar_unavailable?: boolean;
    mass_kg?: number;
    wheelbase_m?: number;
  };
  choices: string[];
}

/** /api/bluetooth: serialized form of BluetoothStatus (see bluetooth_api.status_payload).
 *  Fields map one-to-one to the dataclass in sunnypilot/system/bluetooth/protocol.py. */
export interface BluetoothDevice {
  address: string;
  name: string;
  paired: boolean;
  trusted: boolean;
  connected: boolean;
  blocked: boolean;
  rssi: number | null;
  uuids: string[];
  audio: boolean;
  controller: boolean;
}

/** Pairing request from the daemon's bluez agent (confirmation/authorization only need confirming,
 *  pin/passkey need a number entered; display_only is shown without a response) */
export interface BluetoothPrompt {
  id: string;
  kind: "confirmation" | "authorization" | "pin" | "passkey" | (string & {});
  name?: string;
  value?: string;
  display_only?: boolean;
  address?: string;
}

export interface BluetoothStatus {
  available: boolean;
  enabled: boolean;
  powered: boolean;
  discovering: boolean;
  offroad: boolean;
  selected_audio: string;
  pairing_address: string;
  devices: BluetoothDevice[];
  prompt: BluetoothPrompt | null;
  error: string;
}

/** /api/wifi: one connectable network (serialized form from lanlinkd wl_worker) */
export interface WifiNetwork {
  ssid: string;
  rssi: number | null;
  security: string;
  saved: boolean;
}

/** IPv4 overview of the current connection profile (shape of wifi_manager.get_ipv4_settings) */
export interface WifiIpv4 {
  method: string;
  addresses: string[];
  gateway: string;
  dns: string[];
}

export interface WifiStatus {
  available: boolean;
  offroad: boolean;
  connecting: string | null;
  connected: string | null;
  ipv4: WifiIpv4;
  networks: WifiNetwork[];
  error: string;
}

/** /api/software: serialized updater status params (see software_api.status) */
export interface SoftwareDescription {
  version: string;
  branch: string;
  commit: string;
  date: string;
}

export interface SoftwareStatus {
  version: string;
  branch: string;
  commit: string;
  current: SoftwareDescription | null;
  updaterState: string;
  updateAvailable: boolean;
  fetchAvailable: boolean;
  failedCount: number;
  failed: boolean;
  newVersion: SoftwareDescription | null;
  targetBranch: string;
  availableBranches: string[];
  offroad: boolean;
}

/** /api/diagnostics: diagnostics page (camera mounting, drift, weaving, steering capability).
 *  Driving stats cover only the current drive (reset when started goes false to true, kept after parking). */
export interface DiagnosticsReport {
  drive: { started: boolean; seconds: number };   // seconds = seconds elapsed in this drive (0 if not driven yet)
  camera: CameraDiag | null;                       // null if never calibrated (no cache and no live data)
  drift: DriftDiag;
  weave: WeaveDiag;
  steering: SteeringDiag;
  bsm: BsmDiag;
}
export interface CameraDiag {
  source: "live" | "cache";
  calStatus: "uncalibrated" | "calibrated" | "invalid" | "recalibrating";
  calPerc: number;                 // 0–100
  pitchDeg: number;                // >0 device points down
  yawDeg: number;                  // >0 device points left
  limits: { pitchUpDeg: number; pitchDownDeg: number; yawDeg: number };  // all positive
  cameraOffsetM: number;           // current CameraOffset, >0 = device left of center
}
export interface DriftDiag {
  seconds: number;                 // seconds of valid straight-road samples
  carOffsetM: number | null;       // average, >0 car is right of center; null with no samples
  planOffsetM: number | null;      // average, >0 plan is right of center
  angleOffsetDeg: number | null;   // paramsd angleOffsetAverageDeg (live or cached)
  angleOffsetValid: boolean | null;
  accurateAngle: "ready" | "pending" | "unknown" | "n/a";  // Toyota high-precision steering angle; n/a for non-Toyota; unknown if no carState received this drive
  latAccelOffset: number | null;   // m/s², offset learned by torqued
  torqueCalPerc: number | null;    // torqued learning progress 0–100; offset not yet trustworthy below 100
}
export interface WeaveDiag {
  seconds: number;                 // seconds of straight-road samples (same basis as drift)
  windows: number;                 // number of 10 s windows evaluated
  weaveWindows: number;            // of those, windows judged as weaving
  medianP2pM: number | null;       // median peak-to-peak across windows
  medianPeriodS: number | null;    // median period across windows (windows with no estimable period excluded)
  trace: (number | null)[];        // last 30 s, 4 Hz, 120 points, meters, >0 right; null = sampling conditions not met
  lateralDelayS: number | null;    // lateral delay learned by lagd
  factoryDelayS: number | null;    // CarParams.steerActuatorDelay
}
export interface SteeringDiag {
  control: "torque" | "angle" | "";
  activeSeconds: number;           // seconds with lateral control active and speed > 5 m/s
  curveSeconds: number;            // of those, seconds in curves
  saturatedCurveSeconds: number;   // seconds in curves while saturated
  usage: number[] | null;          // torque control: seconds in five |output| bins [0,.2) [.2,.4) [.4,.6) [.6,.8) [.8,1]; null for angle
  epsTempFaults: number;
  epsPermanent: boolean;
  maxLatAccel: number | null;      // max |curvature·v²| reached while active, m/s²
}
export interface BsmDiag {
  available: boolean | null;       // CarParams.enableBsm; null if the car model was never identified
  leftEvents: number;              // left blind-spot triggers this drive (rising edges)
  rightEvents: number;
  leftOccupied: boolean;           // whether the latest frame has a car in the blind spot; after parking, the last frame of the previous drive
  rightOccupied: boolean;
  watchSeconds: number;            // seconds this drive at ≥ 16 km/h (BSM only works above this speed)
}

// ---- TechStream Toyota diagnostics (/api/toyota/*, backend in toyota_diag_api.py) ----

export interface ToyotaSession {
  state: "idle" | "entering" | "active";
  error?: string;                  // reason the last entry failed (state returns to idle after a failure)
  idleTimeoutS: number;
  lastActivity?: number;           // device unix seconds
  idleRemainingS?: number;         // idle auto-exit seconds remaining as computed by the device; only present once active
}
/** Catalog (GET /api/toyota/catalog): Sienna Gen 4 only, served by the backend from sienna_catalog.json */
export interface ToyotaEcu {
  id: string;                      // "750/40" (gateway sub-address) or "7B0"
  tx: string;
  sub: string | null;
  name: string;
  protocol: "uds" | "toyota_can";
}
export interface ToyotaCategory { id: string; name: string; icon: string }  // icon = lucide icon name (kebab-case)
export interface ToyotaOption { value: number; label: string }
export interface ToyotaSetting {
  key: string;
  category: string;
  name: string;
  ecu: string;                     // ToyotaEcu.id
  did: string | null;              // UDS uses did, Toyota CAN uses localId (hex string)
  localId: string | null;
  byteIndex: number;
  mask: string;
  requiresBitSupportCheck: boolean;
  options: ToyotaOption[];         // empty for numeric settings
  numeric: { min: number; max: number } | null;
  popular: boolean;
}
export interface ToyotaLiveItem {
  key: string;
  name: string;
  unit: string;
  options: ToyotaOption[] | null;
  needsEngineRunning: boolean;
}
export interface ToyotaLiveTool { id: string; name: string; icon: string; keys: string[] }
export interface ToyotaBatteryBlock { voltageKey: string; resistanceKey: string; modules: number }
export interface ToyotaCatalog {
  ecus: ToyotaEcu[];
  categories: ToyotaCategory[];
  settings: ToyotaSetting[];
  liveTools: ToyotaLiveTool[];
  live: ToyotaLiveItem[];
  battery: { ecu: string; blocks: ToyotaBatteryBlock[] };
}

/** Per-ECU scan result status: no response / bad ISO-TP response / OK */
export type ToyotaScanStatus = "offline" | "malformed" | "ok";
export interface ToyotaCustomizationScan {
  ecu: string;
  status: ToyotaScanStatus;
  items: { key: string; value: number; raw: string }[];  // raw = whole payload hex (for CAN type, the expanded data)
  supported?: number;              // details: supported count / read count
  read?: number;
  readError?: string;
}
export interface ToyotaWriteResult {
  key: string; value: number; verified: boolean; backupId: string; before: string; after: string;
}
export interface ToyotaBackup {
  id: string;
  time: number;                    // device unix seconds
  key: string;
  name: string;
  ecu: string;
  before: { value: number; label: string };
  after?: { value: number; label: string };
  restored?: boolean;
}
export interface ToyotaDtc {
  code: string;                    // "U0131-87"
  status: number | null;           // UDS status byte; Toyota CAN codes have no status
  text: string;                    // description assembled by the backend from the catalog; empty if not found
}
export interface ToyotaDtcScan {
  ecu: string;
  status: ToyotaScanStatus;
  protocol: string;
  dtcs: ToyotaDtc[];
  readError?: string;              // when the ECU refuses the DTC read (e.g. "NRC 11"); dtcs is empty
}
export interface ToyotaDtcClearResult { ecu: string; ok: boolean; error?: string }
export interface ToyotaLiveValue { key: string; value: number | null; text: string; error?: string }
