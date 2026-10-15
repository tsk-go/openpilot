<script setup lang="ts">
/** Home page: vehicle card (12V, odometer, online ECU count) + 5 feature entries.
 *
 * When not in diagnostic mode the first four entries are grayed out; tapping one shakes the session bar and shows a notice (Backups doesn't need diagnostic mode).
 */
import { computed, onMounted, ref, watch, type Component } from "vue";
import { Activity, Archive, BatteryCharging, CarFront, ChevronRight, Stethoscope, Wrench } from "lucide-vue-next";
import { api } from "@/lib/api";
import { BATTERY_LEVEL_LABEL } from "@/lib/battery";
import type { ToyotaLiveValue } from "@/lib/schema";
import { goTo, type ToyotaPageName } from "@/lib/toyotaNav";
import { BATTERY_12V_KEY, HOME_LIVE_KEYS, MILEAGE_KEY, MILEAGE_UNIT_KEY, dtcSummaryText, liveValueText, mileageText, onlineEcuText } from "@/lib/toyota";
import { toyotaData } from "@/lib/toyotaData";
import { requireActive, currentSessionView } from "@/lib/toyotaSession";
import { cn } from "@/lib/utils";
import Badge from "../ui/Badge.vue";

const vehicle = ref<Map<string, ToyotaLiveValue>>(new Map());
const catalog = computed(() => toyotaData.catalog);

async function readVehicle(): Promise<void> {
  try {
    const { values } = await api.toyotaReadLive([...HOME_LIVE_KEYS]);
    vehicle.value = new Map(values.map((v) => [v.key, v]));
  } catch {
    // The vehicle card is just extra info: if it can't be read show "—" and don't bother the user
  }
}

onMounted(() => { if (currentSessionView.value.canUseDiagnostics) void readVehicle(); });
watch(() => currentSessionView.value.canUseDiagnostics, (on) => { if (on) void readVehicle(); else vehicle.value = new Map(); });

const voltageText = computed(() => liveValueText(vehicle.value.get(BATTERY_12V_KEY), "V"));
const mileageDisplay = computed(() => mileageText(vehicle.value.get(MILEAGE_KEY), vehicle.value.get(MILEAGE_UNIT_KEY)));

const batteryLevel = computed(() => toyotaData.battery.analysis?.level);

interface Entry { page: ToyotaPageName; icon: Component; title: string; desc: string; needsSession: boolean }
const entries = computed<Entry[]>(() => [
  { page: "custom", icon: Wrench, title: "Customize", desc: `${catalog.value?.settings.length ?? 0} adjustable items · change by category with one tap`, needsSession: true },
  { page: "dtc", icon: Stethoscope, title: "Trouble codes", desc: dtcSummaryText(toyotaData.dtc.state === "done" ? toyotaData.dtc.scans : null), needsSession: true },
  { page: "live", icon: Activity, title: "Live data", desc: "Wheel speeds, engine & 12V, A/C", needsSession: true },
  { page: "battery", icon: BatteryCharging, title: "Hybrid battery", desc: "Voltage and resistance of 12 blocks", needsSession: true },
  { page: "backups", icon: Archive, title: "Backups", desc: "Backed up automatically before changes, restore anytime", needsSession: false },
]);

function open(e: Entry): void {
  if (e.needsSession && !requireActive()) return;
  goTo(e.page);
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <section class="sl-card flex flex-col gap-3 p-4">
      <div class="flex items-center gap-3">
        <CarFront class="size-9 shrink-0 text-sl-accent" />
        <div>
          <div class="text-[18px] font-semibold text-sl-text-1">Toyota Sienna Gen 4</div>
          <div class="text-[13px] text-sl-text-2">Hybrid · 2021+ · NiMH 288 V</div>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-2">
        <div class="rounded-lg bg-sl-surface-2 px-2.5 py-2">
          <div class="text-[12px] text-sl-text-2">12V voltage</div>
          <div class="sl-tabular text-[16px] font-semibold text-sl-text-1">{{ voltageText }}</div>
        </div>
        <div class="rounded-lg bg-sl-surface-2 px-2.5 py-2">
          <div class="text-[12px] text-sl-text-2">Odometer</div>
          <div class="sl-tabular text-[16px] font-semibold text-sl-text-1">{{ mileageDisplay }}</div>
        </div>
        <div class="rounded-lg bg-sl-surface-2 px-2.5 py-2">
          <div class="text-[12px] text-sl-text-2">Online ECUs</div>
          <div class="sl-tabular text-[16px] font-semibold text-sl-text-1">
            {{ onlineEcuText(toyotaData.ecuAnswered) }}
          </div>
        </div>
      </div>
      <p class="text-[12px] text-sl-text-3">12V voltage: IG-ON shows the 12V battery, Ready shows charging. Online ECUs: responded / probed, updated after a scan.</p>
    </section>

    <button
      v-for="e in entries"
      :key="e.page"
      type="button"
      :class="cn('sl-card flex w-full items-center gap-3.5 p-3.5 text-left transition-colors hover:bg-sl-surface-2', e.needsSession && !currentSessionView.canUseDiagnostics && 'opacity-40')"
      @click="open(e)"
    >
      <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-sl-accent-muted text-sl-accent">
        <component :is="e.icon" class="size-5" />
      </span>
      <span class="flex min-w-0 flex-1 flex-col">
        <b class="text-[16px] font-semibold text-sl-text-1">{{ e.title }}</b>
        <span class="text-[13px] text-sl-text-2">
          {{ e.desc }}
          <template v-if="e.page === 'battery' && batteryLevel">
            · Status <Badge :kind="BATTERY_LEVEL_LABEL[batteryLevel].tone">{{ BATTERY_LEVEL_LABEL[batteryLevel].text }}</Badge>
          </template>
        </span>
      </span>
      <ChevronRight class="size-5 shrink-0 text-sl-text-3" />
    </button>

    <p v-if="!currentSessionView.canUseDiagnostics" class="text-center text-[13px] text-sl-text-2">
      Tap "Enter" above to start diagnostic mode and use the first four features
    </p>
  </div>
</template>
