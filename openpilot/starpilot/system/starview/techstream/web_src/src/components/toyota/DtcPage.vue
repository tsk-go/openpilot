<script setup lang="ts">
/** Trouble codes page: per-ECU scan (progress) → three stat cards, "Faults only", ECU list (sorted by DTC count, descending), rescan, clear all. */
import { computed, onMounted, ref } from "vue";
import { ChevronRight, RefreshCw } from "lucide-vue-next";
import { dtcScanState, dtcSummary, scanTally, sortEcusByDtcCount } from "@/lib/toyota";
import { goTo } from "@/lib/toyotaNav";
import { scanDtcs, toyotaData } from "@/lib/toyotaData";
import { cn } from "@/lib/utils";
import Badge from "../ui/Badge.vue";
import Button from "../ui/Button.vue";
import Switch from "../ui/Switch.vue";
import DtcClearButton from "./DtcClearButton.vue";

const dtc = computed(() => toyotaData.dtc);
const ecus = computed(() => toyotaData.catalog!.ecus);
const tally = computed(() => scanTally(dtc.value.scans.map((s) => s.status), ecus.value.length));
const summary = computed(() => dtcSummary(dtc.value.scans));
const onlyFaulty = ref(false);

onMounted(() => { if (dtc.value.state === "idle") void scanDtcs(); });

const scanOf = (id: string) => dtc.value.scans.find((s) => s.ecu === id);
const rows = computed(() =>
  sortEcusByDtcCount(ecus.value, dtc.value.scans)
    .map((e) => ({ ecu: e, scan: scanOf(e.id) }))
    .filter((r) => !onlyFaulty.value || r.scan?.dtcs.length),
);
const faultyEcuIds = computed(() => dtc.value.scans.filter((s) => s.dtcs.length).map((s) => s.ecu));
</script>

<template>
  <div v-if="dtc.state !== 'done'" class="sl-card p-5 text-center">
    <b class="text-[15px] text-sl-text-1">Scanning ECU <span class="sl-tabular">{{ tally.done }}/{{ tally.total }}</span></b>
    <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-sl-surface-3">
      <div class="h-full bg-sl-accent transition-[width] duration-100" :style="{ width: `${tally.percent}%` }" />
    </div>
  </div>

  <div v-else class="flex flex-col gap-3">
    <p class="text-[12px] text-sl-text-3">Read: IG-ON or Ready · Change / Clear: use IG-ON, don't go to Ready</p>

    <div class="grid grid-cols-3 gap-2">
      <div class="sl-card px-1.5 py-3 text-center">
        <b class="block text-[26px] leading-tight text-sl-text-1">{{ summary.ecuCount }}</b>
        <span class="text-[12px] text-sl-text-2">ECUs scanned</span>
      </div>
      <div class="sl-card px-1.5 py-3 text-center">
        <b :class="cn('block text-[26px] leading-tight', summary.faultyEcuCount ? 'text-sl-danger' : 'text-sl-accent')">{{ summary.faultyEcuCount }}</b>
        <span class="text-[12px] text-sl-text-2">ECUs with faults</span>
      </div>
      <div class="sl-card px-1.5 py-3 text-center">
        <b :class="cn('block text-[26px] leading-tight', summary.codeCount ? 'text-sl-danger' : 'text-sl-accent')">{{ summary.codeCount }}</b>
        <span class="text-[12px] text-sl-text-2">Total DTCs</span>
      </div>
    </div>

    <label class="flex items-center justify-between px-1 py-1 text-[15px] text-sl-text-1">
      Faults only
      <Switch v-model="onlyFaulty" aria-label="Faults only" />
    </label>

    <div class="sl-card divide-y divide-sl-border overflow-hidden">
      <button
        v-for="r in rows"
        :key="r.ecu.id"
        type="button"
        class="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-sl-surface-2"
        @click="goTo('dtcEcu', r.ecu.id)"
      >
        <span class="min-w-0 flex-1">
          <span class="block text-[15px] text-sl-text-1">{{ r.ecu.name }}</span>
          <span class="block text-[12px] text-sl-text-3">{{ r.ecu.id.replace("/", " · ") }}</span>
        </span>
        <span v-if="r.scan?.dtcs.length" class="grid h-6 min-w-6 place-items-center rounded-full bg-sl-danger px-1.5 text-[13px] font-bold text-black">{{ r.scan.dtcs.length }}</span>
        <Badge v-else-if="r.scan?.status === 'offline'">No response</Badge>
        <Badge v-else-if="r.scan?.status === 'malformed'" kind="warn">Bad response</Badge>
        <Badge v-else-if="dtcScanState(r.scan) === 'rejected'" kind="warn">Read refused</Badge>
        <Badge v-else kind="accent">No faults</Badge>
        <ChevronRight class="size-4 shrink-0 text-sl-text-3" />
      </button>
    </div>

    <div class="flex gap-2.5">
      <Button class="flex-1" @click="scanDtcs"><RefreshCw />Scan again</Button>
      <DtcClearButton class="flex-1" label="Clear all" :ecu-ids="faultyEcuIds" />
    </div>
  </div>
</template>
