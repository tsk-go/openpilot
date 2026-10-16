/** Module-level state of the TechStream diagnostic session: polling, idle countdown, enter / exit.
 *
 * The session state is polled from /api/toyota/session every 2 s (paused while the browser page is hidden).
 * State lives in a module rather than a component: every page in the stack reads it, and so does the session bar.
 */
import { computed, reactive, ref } from "vue";
import { api } from "./api";
import { toast } from "./store";
import type { ToyotaSession } from "./schema";
import { errorText, idleRemainingS, sessionView } from "./toyota";

const state = reactive({
  session: null as ToyotaSession | null,
  /** An enter / exit request is in progress */
  busy: false,
  /** Seconds elapsed locally since the device data was received, used to count down the idle timer */
  elapsedS: 0,
});

/** Incremented when a feature is tapped while not in diagnostic mode; the session bar replays its shake animation on change */
export const shakeTick = ref(0);

export const sessionNow = computed(() => state.session);
export const sessionBusy = computed(() => state.busy);
export const currentSessionView = computed(() => sessionView(state.session));
export const remainingS = computed(() => idleRemainingS(state.session, state.elapsedS));

let fetchedAtMs = Date.now();
let polling = false;
let selfExiting = false;

/** Each time device data arrives, reset the local countdown origin; the next poll corrects it naturally */
function setSession(next: ToyotaSession): void {
  const wasActive = state.session?.state === "active";
  state.session = next;
  fetchedAtMs = Date.now();
  state.elapsedS = 0;
  if (wasActive && next.state === "idle" && !selfExiting) toast("Idle timeout, diagnostic mode exited automatically", "warn");
}

/** Any action resets the idle timer (the backend refreshes it on every diagnostic request too); the next poll corrects it */
export function touch(): void {
  if (state.session?.state !== "active") return;
  state.session = { ...state.session, idleRemainingS: state.session.idleTimeoutS };
  fetchedAtMs = Date.now();
  state.elapsedS = 0;
}

export async function poll(): Promise<void> {
  if (polling || document.visibilityState !== "visible") return;
  polling = true;
  try {
    setSession(await api.toyotaSession());
  } catch (e) {
    // On failure keep the previous frame; only notify if we never got data
    if (!state.session) toast(errorText(e), "error");
  } finally {
    polling = false;
  }
}

export async function enter(): Promise<boolean> {
  if (state.busy) return false;
  state.busy = true;
  // Entering can take over ten seconds; meanwhile polling can show entering
  state.session = { ...(state.session ?? { idleTimeoutS: 0 }), state: "entering" };
  try {
    setSession(await api.toyotaEnter());
    return true;
  } catch (e) {
    toast(errorText(e), "error");
    await poll();
    return false;
  } finally {
    state.busy = false;
  }
}

export async function exit(): Promise<void> {
  if (state.busy) return;
  state.busy = true;
  selfExiting = true;
  try {
    await api.toyotaExit();
    setSession(await api.toyotaSession());
    toast("Diagnostic mode exited, openpilot will resume", "ok");
  } catch (e) {
    toast(errorText(e), "error");
    await poll();
  } finally {
    selfExiting = false;
    state.busy = false;
  }
}

/** Gate before feature entry / writes: if not in diagnostic mode, shake the session bar and notify */
export function requireActive(): boolean {
  if (state.session?.state === "active") return true;
  toast("Enter diagnostic mode first", "warn");
  shakeTick.value++;
  return false;
}

let pollTimer: ReturnType<typeof setInterval> | undefined;
let clockTimer: ReturnType<typeof setInterval> | undefined;
let watchers = 0;

/** Called when the panel mounts; returns a stop function. Multiple simultaneous mounts share one set of timers */
export function startSessionWatch(): () => void {
  if (watchers++ === 0) {
    void poll();
    pollTimer = setInterval(() => void poll(), 2000);
    clockTimer = setInterval(() => { state.elapsedS = (Date.now() - fetchedAtMs) / 1000; }, 1000);
  }
  return () => {
    if (--watchers > 0) return;
    clearInterval(pollTimer);
    clearInterval(clockTimer);
  };
}
