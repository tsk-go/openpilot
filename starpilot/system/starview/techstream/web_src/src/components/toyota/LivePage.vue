<script setup lang="ts">
/** Live data page: 3 topics + a hybrid battery entry; a topic page is a big-number grid refreshed every 1 s, with pause / resume.
 *  The odometer unit is merged into the odometer card; in Ready the engine often isn't running, so engine items carry an "Engine must be running" tag. */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { BatteryCharging, ChevronRight, Pause, Play } from "lucide-vue-next";
import { api } from "@/lib/api";
import type { ToyotaLiveValue } from "@/lib/schema";
import { BATTERY_12V_KEY, errorText, liveCards, plural } from "@/lib/toyota";
import { iconByName } from "@/lib/toyotaIcons";
import { currentPage, goTo } from "@/lib/toyotaNav";
import { toyotaData } from "@/lib/toyotaData";
import { touch } from "@/lib/toyotaSession";
import { toast } from "@/lib/store";
import { cn } from "@/lib/utils";
import Badge from "../ui/Badge.vue";
import Button from "../ui/Button.vue";

const REFRESH_MS = 1000;

const catalog = computed(() => toyotaData.catalog!);
const tool = computed(() => catalog.value.liveTools.find((t) => t.id === currentPage.value.arg));
const items = computed(() =>
  (tool.value?.keys ?? []).flatMap((k) => catalog.value.live.filter((i) => i.key === k)),
);
const values = ref<ToyotaLiveValue[]>([]);
const paused = ref(false);
const cards = computed(() => liveCards(items.value, values.value));

let timer: ReturnType<typeof setInterval> | undefined;
let reading = false;
let errorShown = false;

async function refresh(): Promise<void> {
  if (reading || paused.value || document.visibilityState !== "visible" || !tool.value) return;
  reading = true;
  try {
    values.value = (await api.toyotaReadLive(tool.value.keys)).values;
    errorShown = false;
    touch();
  } catch (e) {
    // Only notify once for consecutive failures, rather than a toast every second
    if (!errorShown) toast(errorText(e), "error");
    errorShown = true;
  } finally {
    reading = false;
  }
}

// The topic list and topic page are the same component instance (entering a topic doesn't remount), so the timer starts on mount; switching topics clears old values and reads immediately
watch(tool, () => {
  values.value = [];
  void refresh();
});
onMounted(() => {
  void refresh();
  timer = setInterval(() => void refresh(), REFRESH_MS);
});
onUnmounted(() => clearInterval(timer));
</script>

<template>
  <!-- Topic page -->
  <div v-if="tool" class="flex flex-col gap-2.5">
    <div :class="cn('grid grid-cols-2 gap-2.5', paused && '[&_b]:text-sl-text-2')">
      <div v-for="c in cards" :key="c.key" class="sl-card px-3 py-3.5">
        <b class="sl-tabular block text-[28px] leading-tight text-sl-text-1">
          {{ c.value }}<small v-if="c.unit" class="ml-1 text-[14px] font-medium text-sl-text-2">{{ c.unit }}</small>
        </b>
        <span class="text-[13px] text-sl-text-2">{{ c.name }}</span>
        <Badge v-if="c.needsEngineRunning" kind="warn" class="ml-1.5 normal-case">Engine must be running</Badge>
      </div>
    </div>
    <div class="flex items-center justify-between gap-3 px-1">
      <span class="text-[12px] text-sl-text-3">Refreshes every 1 s{{ paused ? " (paused)" : "" }}</span>
      <Button @click="paused = !paused"><component :is="paused ? Play : Pause" />{{ paused ? "Resume" : "Pause" }}</Button>
    </div>
    <p v-if="items.some((i) => i.key === BATTERY_12V_KEY)" class="px-1 text-[12px] text-sl-text-3">
      12V voltage: IG-ON shows the 12V battery, Ready shows charging.
    </p>
  </div>

  <!-- Overview -->
  <div v-else class="flex flex-col gap-2.5">
    <p class="text-[14px] text-sl-text-2">View live vehicle data by topic.</p>
    <button
      v-for="t in catalog.liveTools"
      :key="t.id"
      type="button"
      class="sl-card flex w-full items-center gap-3.5 p-3.5 text-left hover:bg-sl-surface-2"
      @click="goTo('liveTool', t.id)"
    >
      <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-sl-accent-muted text-sl-accent">
        <component :is="iconByName(t.icon)" class="size-5" />
      </span>
      <span class="flex-1">
        <b class="block text-[16px] text-sl-text-1">{{ t.name }}</b>
        <span class="text-[13px] text-sl-text-2">{{ plural(t.keys.length, "item") }}</span>
      </span>
      <ChevronRight class="size-5 text-sl-text-3" />
    </button>
    <button
      type="button"
      class="sl-card flex w-full items-center gap-3.5 p-3.5 text-left hover:bg-sl-surface-2"
      @click="goTo('battery')"
    >
      <span class="grid size-11 shrink-0 place-items-center rounded-xl bg-sl-accent-muted text-sl-accent">
        <BatteryCharging class="size-5" />
      </span>
      <span class="flex-1">
        <b class="block text-[16px] text-sl-text-1">Hybrid battery</b>
        <span class="text-[13px] text-sl-text-2">Voltage and resistance of 12 blocks, with health check</span>
      </span>
      <ChevronRight class="size-5 text-sl-text-3" />
    </button>
  </div>
</template>
