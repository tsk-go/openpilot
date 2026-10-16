/** Global state.
 *
 * The data flow is deliberately "bulk fetch + version-driven refresh", matching upstream (see FRONTEND_SPEC.md §1):
 * one /api/settings_ui + /api/capabilities + /api/params/_all fetches everything,
 * then a change of paramsVersion in /api/status reveals changes made **on the device**
 * (if a setting is changed on the car screen, the web page must follow).
 *
 * Writes are optimistic: update locally first, then send the request; on failure roll back and notify. LAN latency is low,
 * but params.put(block=True) has to hit disk, so optimistic updates keep toggles responsive.
 */
import { computed, reactive, readonly } from "vue";
import { api, ApiError } from "./api";
import type {
  Capabilities,
  Item,
  Panel,
  ParamValues,
  SettingsSchema,
  StatusSnapshot,
} from "./schema";

type ToastAction = { label: string; run: () => void };
type Toast = { id: number; text: string; kind: "ok" | "warn" | "error"; action?: ToastAction };

const state = reactive({
  ready: false,
  loading: false,
  error: "" as string,

  schema: null as SettingsSchema | null,
  caps: {} as Capabilities,
  params: {} as ParamValues,
  status: null as StatusSnapshot | null,

  paramsVersion: null as string | null | undefined,
  connected: false,
  pending: new Set<string>(),
  toasts: [] as Toast[],
});

export const store = state;
export const stateRO = readonly(state);

let toastSeq = 0;
/** Toasts with an action button stay longer, giving the user time to "Undo"; dismissed immediately on click */
export function toast(text: string, kind: Toast["kind"] = "ok", action?: ToastAction): void {
  const id = ++toastSeq;
  state.toasts.push({ id, text, kind, action });
  setTimeout(() => dismissToast(id), action ? 9000 : kind === "error" ? 6000 : 3000);
}

export function dismissToast(id: number): void {
  const i = state.toasts.findIndex((t) => t.id === id);
  if (i >= 0) state.toasts.splice(i, 1);
}

/** Clears toasts left by the previous page on navigation (especially an "Undo" that is no longer valid) */
export function clearToasts(): void {
  state.toasts.splice(0);
}

/** Panel list sorted by schema order; Maps is not in the local schema (excluded by requirement) */
export const panels = computed<Panel[]>(() => {
  const p = state.schema?.panels ?? [];
  return [...p].sort((a, b) => (a.order ?? 99) - (b.order ?? 99) || a.id.localeCompare(b.id));
});

export function panelById(id: string): Panel | undefined {
  return panels.value.find((p) => p.id === id);
}

/** Full load: called once after login */
export async function loadAll(): Promise<void> {
  state.loading = true;
  state.error = "";
  try {
    const [schema, caps, params] = await Promise.all([
      api.settingsUi(),
      api.capabilities(),
      api.allParams(),
    ]);
    state.schema = schema;
    state.caps = caps;
    state.params = params;
    state.ready = true;
  } catch (e) {
    state.error = e instanceof Error ? e.message : String(e);
    throw e;
  } finally {
    state.loading = false;
  }
}

export async function refreshParams(): Promise<void> {
  state.params = await api.allParams();
}

export async function refreshCapabilities(): Promise<void> {
  state.caps = await api.capabilities();
}

/** Status polling: also uses paramsVersion to detect changes on the device */
export async function pollStatus(): Promise<void> {
  try {
    const s = await api.status();
    state.status = s;
    state.connected = true;

    const seen = state.paramsVersion;
    if (s.paramsVersion !== undefined && s.paramsVersion !== seen) {
      const first = seen === null || seen === undefined;
      state.paramsVersion = s.paramsVersion;
      // The first time only records the baseline; later changes mean settings were changed on the car and must be synced
      if (!first && state.ready) {
        await Promise.all([refreshParams(), refreshCapabilities()]);
      }
    }
  } catch (e) {
    state.connected = false;
  }
}

// ---- Param read / write ----

export function rawValue(key: string): string | undefined {
  return state.params[key];
}

export function boolValue(key: string): boolean {
  return state.params[key] === "1";
}

export function numValue(key: string, fallback = 0): number {
  const n = Number(state.params[key]);
  return Number.isFinite(n) ? n : fallback;
}

export function isPending(key: string): boolean {
  return state.pending.has(key);
}

/** Optimistic write; on failure roll back and show the reason returned by the device */
export async function writeParam(key: string, value: string): Promise<boolean> {
  const previous = state.params[key];
  state.params[key] = value;
  state.pending.add(key);
  try {
    await api.putParam(key, value);
    return true;
  } catch (e) {
    // Roll back: the device rejected it (403 blocked / 400 type mismatch / 404 unknown key)
    if (previous === undefined) delete state.params[key];
    else state.params[key] = previous;

    const msg = e instanceof ApiError ? describeWriteError(e, key) : String(e);
    toast(msg, "error");
    return false;
  } finally {
    state.pending.delete(key);
  }
}

function describeWriteError(e: ApiError, key: string): string {
  switch (e.status) {
    case 403:
      // We deliberately return 403 instead of silently skipping like upstream, so explain it clearly here
      return `"${key}" is protected by the device and can't be changed remotely`;
    case 400:
      return `Invalid value for "${key}"`;
    case 404:
      return `"${key}" does not exist on the device`;
    case 429:
      return "Too many requests, try again later";
    default:
      return `Failed to write "${key}": ${e.message}`;
  }
}

export async function toggleParam(key: string): Promise<void> {
  await writeParam(key, boolValue(key) ? "0" : "1");
}

// ---- Search (like sunnylink's ⌘K settings search) ----

export interface SearchHit {
  panel: Panel;
  item: Item;
  subPanelLabel?: string;
}

export function searchSettings(query: string): SearchHit[] {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const hits: SearchHit[] = [];
  for (const panel of panels.value) {
    for (const section of panel.sections ?? []) {
      for (const item of section.items ?? []) {
        if (matches(item, q)) hits.push({ panel, item });
      }
      for (const sub of section.sub_panels ?? []) {
        for (const item of sub.items ?? []) {
          if (matches(item, q)) hits.push({ panel, item, subPanelLabel: sub.label });
        }
      }
    }
  }
  return hits.slice(0, 40);
}

function matches(item: Item, q: string): boolean {
  return (
    item.title?.toLowerCase().includes(q) ||
    item.key?.toLowerCase().includes(q) ||
    (item.description?.toLowerCase().includes(q) ?? false)
  );
}
