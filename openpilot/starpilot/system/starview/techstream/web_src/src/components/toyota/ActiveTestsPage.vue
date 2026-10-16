<script setup lang="ts">
/** StarView: Toyota Active Tests (output tests) for the body / comfort modules.
 *
 * One test at a time. "Hold" mode (default): the output runs while a button is held and stops on release. "Tap" mode:
 * tap to start, tap again (or Stop) to stop - for checking a lamp from outside. Either way the page checks in every
 * second; the comma stops the test if the page goes quiet for 3 s, and after 60 s at most.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ChevronDown, ChevronRight, Hand, Search, Square } from "lucide-vue-next";
import { api } from "@/lib/api";
import type { ToyotaTest, ToyotaTestEcu, ToyotaTestStatus } from "@/lib/schema";
import { toast } from "@/lib/store";
import { errorText } from "@/lib/toyota";
import { currentSessionView, requireActive, touch } from "@/lib/toyotaSession";
import { cn } from "@/lib/utils";
import Badge from "../ui/Badge.vue";
import Button from "../ui/Button.vue";

const MANY = 8;               // more choices than this: a picker plus one hold button

const ecus = ref<ToyotaTestEcu[]>([]);
const tests = ref<ToyotaTest[]>([]);
const loading = ref(true);
const query = ref("");
const mode = ref<"hold" | "tap">("hold");
const open = reactive<Record<string, boolean>>({});
const picked = reactive<Record<string, string>>({});
const status = ref<ToyotaTestStatus>({ active: null, error: "" });
/** what the user is asking for right now (key = ecu|id|choice), null when nothing */
const wanted = ref<string | null>(null);
const starting = ref(false);
/** per module: what the car really has (checked when the module is opened), and "show everything anyway" */
const checks = reactive<Record<string, "checking" | { status: "ok" | "offline"; have: Set<string> }>>({});
const showAll = reactive<Record<string, boolean>>({});

async function check(id: string): Promise<void> {
  if (checks[id] || !currentSessionView.value.canUseDiagnostics) return;
  checks[id] = "checking";
  try {
    const r = await api.toyotaTestCheck(id);
    checks[id] = { status: r.status, have: new Set(r.have) };
  } catch (e) {
    delete checks[id];
    toast(errorText(e), "error");
  }
}
function toggle(id: string): void {
  open[id] = !open[id];
  if (open[id]) void check(id);
}
const offline = (id: string) => { const c = checks[id]; return !!c && c !== "checking" && c.status === "offline"; };
const checked = (id: string) => { const c = checks[id]; return c && c !== "checking" && c.status === "ok" ? c : null; };

const keyOf = (t: ToyotaTest, choice: string | null) => `${t.ecu}|${t.id}|${choice ?? ""}`;
const activeKey = computed(() => {
  const a = status.value.active;
  return a ? `${a.ecu}|${a.id}|${a.choice ?? ""}` : null;
});

onMounted(async () => {
  try {
    const r = await api.toyotaTests();
    ecus.value = r.ecus;
    tests.value = r.tests;
    const first = r.ecus.find((e) => e.name === "Main Body")?.id ?? r.ecus[0]?.id;
    if (first) { open[first] = true; void check(first); }
  } catch (e) {
    toast(errorText(e), "error");
  } finally {
    loading.value = false;
  }
});

const groups = computed(() => {
  const q = query.value.trim().toLowerCase();
  const first = ["Main Body", "Combination Meter"];
  return [...ecus.value]
    .sort((a, b) => (first.indexOf(a.name) + 1 || 99) - (first.indexOf(b.name) + 1 || 99) || a.name.localeCompare(b.name))
    .map((e) => {
      const all = tests.value.filter((t) => t.ecu === e.id);
      const c = checked(e.id);
      const fitted = c && !showAll[e.id] ? all.filter((t) => c.have.has(t.id)) : all;
      const hit = !q || e.name.toLowerCase().includes(q) ? fitted : fitted.filter((t) => t.name.toLowerCase().includes(q));
      return { ecu: e, tests: hit, total: all.length, have: c ? c.have.size : null };
    })
    .filter((g) => g.tests.length || (!q && g.have === 0));
});
const shown = computed(() => groups.value.reduce((n, g) => n + g.tests.length, 0));
const isOpen = (id: string) => !!query.value.trim() || !!open[id];

// ---- running ----
let pingTimer: ReturnType<typeof setInterval> | undefined;

function setStatus(s: ToyotaTestStatus): void {
  const wasRunning = !!status.value.active;
  status.value = s;
  if (wasRunning && !s.active && s.error) toast(s.error, "warn");
  if (!s.active && !starting.value) wanted.value = null;
  if (s.active) {
    touch();
    if (!pingTimer) pingTimer = setInterval(() => void ping(), 1000);
  } else if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = undefined;
  }
}

async function ping(): Promise<void> {
  try { setStatus(await api.toyotaTestPing()); } catch { /* next one, or the comma stops it after 3 s */ }
}

async function start(t: ToyotaTest, choice: string | null): Promise<void> {
  if (!requireActive()) return;
  const key = keyOf(t, choice);
  wanted.value = key;
  starting.value = true;
  try {
    const s = await api.toyotaTestStart(t.ecu, t.id, choice);
    starting.value = false;
    setStatus(s);
    if (wanted.value !== key) await stop();          // let go before the module answered
  } catch (e) {
    starting.value = false;
    wanted.value = null;
    toast(errorText(e), "error");
  }
}

async function stop(): Promise<void> {
  wanted.value = null;
  if (starting.value) return;                         // start() stops it as soon as it's running
  try { setStatus(await api.toyotaTestStop()); } catch (e) { toast(errorText(e), "error"); }
}

// press-and-hold with pointer capture, so a finger sliding a little doesn't count as letting go
function down(ev: PointerEvent, t: ToyotaTest, choice: string | null): void {
  if (mode.value !== "hold") return;
  (ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId);
  void start(t, choice);
}
function up(): void {
  if (mode.value === "hold" && wanted.value) void stop();
}
function tap(t: ToyotaTest, choice: string | null): void {
  if (mode.value !== "tap") return;
  if (activeKey.value === keyOf(t, choice) || wanted.value === keyOf(t, choice)) void stop();
  else void start(t, choice);
}

const isLive = (t: ToyotaTest, c: string | null) => activeKey.value === keyOf(t, c);
const isPending = (t: ToyotaTest, c: string | null) => starting.value && wanted.value === keyOf(t, c);
const pickOf = (t: ToyotaTest) => picked[`${t.ecu}|${t.id}`] ?? t.choices[0];

onBeforeUnmount(() => {
  if (pingTimer) clearInterval(pingTimer);
  if (status.value.active || wanted.value) void api.toyotaTestStop().catch(() => undefined);
});

const btnCls = (live: boolean, pending: boolean) => cn(
  "select-none touch-none rounded-lg px-3.5 h-10 text-[14px] ring-1 ring-inset transition-colors",
  live ? "bg-sl-accent text-sl-accent-text ring-sl-accent font-semibold"
    : pending ? "bg-sl-accent/25 text-sl-text-1 ring-sl-accent/50"
      : "bg-sl-surface-3 text-sl-text-1 ring-sl-border active:bg-sl-border",
);
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- running bar -->
    <div :class="cn('sl-card flex items-center gap-3 px-3.5 py-3', status.active ? 'ring-1 ring-sl-accent' : '')">
      <span :class="cn('size-2.5 shrink-0 rounded-full', status.active ? 'animate-pulse bg-sl-accent' : 'bg-sl-surface-3')" />
      <span class="min-w-0 flex-1 text-[14px]">
        <template v-if="status.active">
          <b class="text-sl-text-1">{{ status.active.name }}</b>
          <span v-if="status.active.choice" class="text-sl-text-2"> · {{ status.active.choice }}</span>
          <span class="sl-tabular text-sl-text-3"> · {{ Math.round(status.active.runningS) }} s</span>
        </template>
        <span v-else-if="starting" class="text-sl-text-2">Starting…</span>
        <span v-else class="text-sl-text-3">Nothing running</span>
      </span>
      <Button variant="danger" size="sm" :disabled="!status.active && !starting" @click="stop"><Square />Stop</Button>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-lg bg-sl-surface-2 p-1 ring-1 ring-inset ring-sl-border">
        <button
          v-for="m in (['hold', 'tap'] as const)"
          :key="m"
          type="button"
          :class="cn('h-8 rounded-md px-3 text-[13px]', mode === m ? 'bg-sl-surface-3 text-sl-text-1 font-semibold ring-1 ring-sl-border' : 'text-sl-text-3')"
          @click="stop(); mode = m"
        >
          {{ m === "hold" ? "Hold to run" : "Tap on / tap off" }}
        </button>
      </div>
      <label class="flex h-10 min-w-[200px] flex-1 items-center gap-2 rounded-lg bg-sl-surface-2 px-3 ring-1 ring-inset ring-sl-border">
        <Search class="size-4 text-sl-text-3" />
        <input v-model="query" type="search" placeholder="Search tests (horn, lock, window, lamp…)"
               class="min-w-0 flex-1 bg-transparent text-[14px] text-sl-text-1 outline-none placeholder:text-sl-text-3" />
      </label>
    </div>

    <p class="text-[12px] leading-relaxed text-sl-text-3">
      <Hand class="mr-1 inline size-3.5 align-[-2px]" />
      {{ mode === "hold" ? "Press and hold a button - the output runs while you hold it and stops when you let go." : "Tap to start, tap again or Stop to end it." }}
      Stops by itself after 60 s or if this page goes quiet. Park with the car in IG-ON; keep hands and pets clear of doors, windows and mirrors.
    </p>

    <div v-if="loading" class="sl-card p-5 text-center text-[14px] text-sl-text-3">Loading…</div>
    <div v-else-if="!groups.length" class="sl-card p-5 text-center text-[14px] text-sl-text-3">No tests match “{{ query }}”</div>
    <p v-else-if="query.trim()" class="px-1 text-[12px] text-sl-text-3">{{ shown }} {{ shown === 1 ? "test" : "tests" }}</p>

    <div v-for="g in groups" :key="g.ecu.id" class="sl-card overflow-hidden">
      <button type="button" class="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-sl-surface-2" @click="toggle(g.ecu.id)">
        <span class="min-w-0 flex-1">
          <span class="block text-[15px] text-sl-text-1">{{ g.ecu.name }}</span>
          <span class="block text-[12px] text-sl-text-3">{{ g.ecu.id.replace("/", " · ") }}</span>
        </span>
        <Badge v-if="checks[g.ecu.id] === 'checking'" kind="info">Checking…</Badge>
        <Badge v-else-if="offline(g.ecu.id)">No response</Badge>
        <Badge v-else :kind="g.have !== null ? 'accent' : 'muted'">{{ g.have !== null && !showAll[g.ecu.id] ? `${g.tests.length} on this car` : g.tests.length === g.total ? g.total : `${g.tests.length} of ${g.total}` }}</Badge>
        <component :is="isOpen(g.ecu.id) ? ChevronDown : ChevronRight" class="size-4 shrink-0 text-sl-text-3" />
      </button>

      <div v-if="isOpen(g.ecu.id)" class="divide-y divide-sl-border border-t border-sl-border">
        <div v-if="g.have !== null" class="flex items-center justify-between gap-3 px-3.5 py-2 text-[12px] text-sl-text-3">
          <span>{{ showAll[g.ecu.id] ? `All ${g.total} of Toyota's tests for this module - the ones your car doesn't have will just say so` : `${g.have} of Toyota's ${g.total} are fitted to your car (motor / routine tests can't be checked ahead, so they stay listed)` }}</span>
          <button type="button" class="shrink-0 text-sl-accent" @click="showAll[g.ecu.id] = !showAll[g.ecu.id]">{{ showAll[g.ecu.id] ? "Only mine" : "Show all" }}</button>
        </div>
        <div v-for="t in g.tests" :key="t.id" class="flex flex-wrap items-center gap-x-3 gap-y-2 px-3.5 py-2.5">
          <span class="min-w-[180px] flex-1 text-[14px] text-sl-text-1">{{ t.name }}</span>

          <!-- routine, or a test with no fixed value -->
          <button v-if="!t.choices.length" type="button" :class="btnCls(isLive(t, null), isPending(t, null))"
                  @pointerdown="down($event, t, null)" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
                  @click="tap(t, null)" @contextmenu.prevent>
            {{ isLive(t, null) ? "Running" : mode === "hold" ? "Hold to run" : "Run" }}
          </button>

          <!-- a few choices: one button each -->
          <div v-else-if="t.choices.length <= MANY" class="flex flex-wrap gap-1.5">
            <button v-for="c in t.choices" :key="c" type="button" :class="btnCls(isLive(t, c), isPending(t, c))"
                    @pointerdown="down($event, t, c)" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
                    @click="tap(t, c)" @contextmenu.prevent>
              {{ c }}
            </button>
          </div>

          <!-- many choices: pick one, then hold -->
          <div v-else class="flex items-center gap-1.5">
            <select :value="pickOf(t)" class="h-10 rounded-lg bg-sl-surface-3 px-2 text-[14px] text-sl-text-1 ring-1 ring-inset ring-sl-border"
                    @change="picked[`${t.ecu}|${t.id}`] = ($event.target as HTMLSelectElement).value">
              <option v-for="c in t.choices" :key="c" :value="c">{{ c }}</option>
            </select>
            <button type="button" :class="btnCls(isLive(t, pickOf(t)), isPending(t, pickOf(t)))"
                    @pointerdown="down($event, t, pickOf(t))" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
                    @click="tap(t, pickOf(t))" @contextmenu.prevent>
              {{ isLive(t, pickOf(t)) ? "Running" : mode === "hold" ? "Hold" : "Run" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
