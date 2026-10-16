<script setup lang="ts">
/** Hybrid battery page: verdict card, 6 stat cards, two bar charts, a collapsible "How it's judged", and re-read.
 *  Battery readings are just 24 live data items (12 block voltages + 12 block resistances), reusing live/read with no separate backend endpoint.
 *  SOC and battery temperature can't be read on this car, so the page doesn't show them. */
import { computed, onMounted, ref } from "vue";
import { CircleAlert, CircleCheck, Loader2, RefreshCw, TriangleAlert } from "lucide-vue-next";
import { api } from "@/lib/api";
import { analyzeBattery, batteryBlocksFromValues, BATTERY_LEVEL_LABEL, DANGER_DIFF_V, WARN_DIFF_V, type BatteryLevel } from "@/lib/battery";
import { toast } from "@/lib/store";
import { errorText, formatNumber } from "@/lib/toyota";
import { toyotaData } from "@/lib/toyotaData";
import { cn } from "@/lib/utils";
import BarChart from "../ui/BarChart.vue";
import Button from "../ui/Button.vue";

const loading = ref(false);
const failed = ref(false);
const analysis = computed(() => toyotaData.battery.analysis);

async function read(): Promise<void> {
  const battery = toyotaData.catalog?.battery;
  if (!battery || loading.value) return;
  loading.value = true;
  try {
    const keys = battery.blocks.flatMap((b) => [b.voltageKey, b.resistanceKey]);
    const { values } = await api.toyotaReadLive(keys);
    const readings = batteryBlocksFromValues(battery, values);
    toyotaData.battery.analysis = readings ? analyzeBattery(readings) : null;
    failed.value = !readings;
  } catch (e) {
    failed.value = true;
    toast(errorText(e), "error");
  } finally {
    loading.value = false;
  }
}

onMounted(() => { if (!analysis.value) void read(); });

const LEVEL: Record<BatteryLevel, { icon: typeof CircleCheck; color: string; border: string }> = {
  ok: { icon: CircleCheck, color: "text-sl-accent", border: "border-l-sl-accent" },
  warn: { icon: TriangleAlert, color: "text-sl-warn", border: "border-l-sl-warn" },
  danger: { icon: CircleAlert, color: "text-sl-danger", border: "border-l-sl-danger" },
};

const meanV2 = computed(() => (analysis.value ? analysis.value.blocks.reduce((s, b) => s + b.voltagePerTwoModules, 0) / analysis.value.blocks.length : 0));
const voltageChart = computed(() => {
  const a = analysis.value!;
  const edgeTone = a.diff > DANGER_DIFF_V ? "danger" : a.diff > WARN_DIFF_V ? "warn" : "accent";
  return {
    values: a.blocks.map((b) => b.voltagePerTwoModules),
    tones: a.blocks.map((b) => (a.lowBlocks.includes(b) ? "danger" : b === a.min || b === a.max ? edgeTone : "accent")),
    marks: a.blocks.map((b) => (b === a.max ? "High" : b === a.min ? "Low" : "")),
    lo: Math.floor((meanV2.value - 0.7) * 10) / 10,
    hi: Math.ceil((meanV2.value + 0.5) * 10) / 10,
  };
});
const resistanceChart = computed(() => {
  const a = analysis.value!;
  return {
    values: a.blocks.map((b) => b.resistance),
    tones: a.blocks.map((b) => (a.highResistanceBlocks.includes(b) ? "warn" : "info")),
    marks: a.blocks.map(() => ""),
    hi: Math.max(30, Math.ceil(a.resistanceMaxBlock.resistance / 5) * 5),
  };
});
const wholeBlocks = computed(() => analysis.value?.blocks.filter((b) => b.modules === 4).length ?? 0);
const halfBlocks = computed(() => analysis.value?.blocks.filter((b) => b.modules === 2).length ?? 0);
const moduleCount = computed(() => analysis.value?.blocks.reduce((s, b) => s + b.modules, 0) ?? 0);
</script>

<template>
  <div v-if="!analysis" class="sl-card flex flex-col items-center gap-3 p-6 text-center text-[13px] text-sl-text-2">
    <Loader2 v-if="loading" class="size-5 animate-spin text-sl-text-3" />
    <template v-else>
      <p class="text-sl-danger">{{ failed ? "Failed to read the battery (hybrid battery ECU did not respond or readings were incomplete)" : "Not read yet" }}</p>
      <Button @click="read"><RefreshCw />Read again</Button>
    </template>
  </div>

  <div v-else class="flex flex-col gap-3">
    <section :class="cn('sl-card flex items-start gap-3.5 border-l-4 p-4', LEVEL[analysis.level].border)">
      <component :is="LEVEL[analysis.level].icon" :class="cn('mt-0.5 size-8 shrink-0', LEVEL[analysis.level].color)" />
      <div>
        <b :class="cn('text-[20px]', LEVEL[analysis.level].color)">{{ BATTERY_LEVEL_LABEL[analysis.level].text }}</b>
        <p class="mt-0.5 text-[13px] text-sl-text-2">{{ analysis.levelReason }}</p>
      </div>
    </section>
    <p class="mx-1 text-[12px] text-sl-text-3">Read in Ready if possible; readings right after a drive reveal weak blocks better</p>

    <div class="grid grid-cols-2 gap-2">
      <div class="sl-card col-span-2 px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Total voltage (sum of 12 blocks)</div>
        <b class="sl-tabular text-[16px] text-sl-text-1">{{ formatNumber(analysis.total, 1) }} V</b>
        <span class="ml-2 text-[12px] text-sl-text-2">Nominal 288 V; slightly higher at rest is normal</span>
      </div>
      <div class="sl-card col-span-2 px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Battery layout</div>
        <b class="text-[16px] text-sl-text-1">{{ wholeBlocks }} full + {{ halfBlocks }} half blocks = {{ moduleCount }} modules</b>
        <div class="text-[12px] text-sl-text-2">Full block 4 modules / half block 2 modules</div>
      </div>
      <div class="sl-card px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Voltage spread (per 2 modules)</div>
        <b class="sl-tabular text-[16px] text-sl-text-1">{{ formatNumber(analysis.diff, 2) }} V</b>
      </div>
      <div class="sl-card px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Resistance avg / max</div>
        <b class="sl-tabular text-[16px] text-sl-text-1">{{ formatNumber(analysis.resistanceAvg, 1) }} / {{ analysis.resistanceMaxBlock.resistance }} mΩ</b>
      </div>
      <div class="sl-card px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Highest block</div>
        <b class="sl-tabular text-[16px] text-sl-text-1">#{{ analysis.max.blockNumber }} · {{ formatNumber(analysis.max.voltagePerTwoModules, 2) }} V</b>
      </div>
      <div class="sl-card px-3 py-2.5">
        <div class="text-[12px] text-sl-text-2">Lowest block</div>
        <b class="sl-tabular text-[16px] text-sl-text-1">#{{ analysis.min.blockNumber }} · {{ formatNumber(analysis.min.voltagePerTwoModules, 2) }} V</b>
      </div>
    </div>

    <BarChart
      title="Block voltages (per 2 modules)"
      subtitle="Y axis is truncated, for comparing blocks only; half blocks as measured, full blocks ÷2"
      :digits="2"
      v-bind="voltageChart"
    />
    <BarChart
      title="Block resistance (mΩ)"
      subtitle="Full / half blocks are compared within their class; more than 20% above the class average is shown in yellow"
      :digits="0"
      :lo="0"
      v-bind="resistanceChart"
    />

    <details class="sl-card px-3.5 py-3">
      <summary class="cursor-pointer font-semibold text-sl-text-1">How it's judged</summary>
      <ul class="mt-2 list-disc space-y-1 pl-[18px] text-[14px] text-sl-text-2">
        <li>Each block's voltage is first normalized "per 2 modules": half blocks (2 modules) unchanged, full blocks (4 modules) ÷2.</li>
        <li><b class="text-sl-accent">Healthy</b>: max − min ≤ {{ WARN_DIFF_V }} V.</li>
        <li><b class="text-sl-warn">Caution</b>: {{ WARN_DIFF_V }} – {{ DANGER_DIFF_V }} V.</li>
        <li><b class="text-sl-danger">Abnormal</b>: &gt; {{ DANGER_DIFF_V }} V, or any block more than 1 V below the average of the others.</li>
        <li>Resistance: full and half blocks are averaged separately; any block more than 20% above its class average → Caution.</li>
      </ul>
      <p class="mt-2 text-[14px] text-sl-text-2">
        <b>Limitations:</b> There are no official Toyota thresholds; this judges by block-to-block spread and is for reference only. These are resting/parked readings; differences under load (acceleration, hill climbs, fast charge/discharge) reveal problems better. Battery SOC and temperature can't currently be read on this car.
      </p>
    </details>

    <Button variant="accent" class="w-full" :disabled="loading" @click="read">
      <Loader2 v-if="loading" class="animate-spin" /><RefreshCw v-else />
      {{ loading ? "Reading hybrid battery…" : "Read again" }}
    </Button>
    <p class="mx-1 text-[12px] text-sl-text-3">Source: hybrid battery ECU (0x{{ toyotaData.catalog!.battery.ecu }})</p>
  </div>
</template>
