<script setup lang="ts">
/** Trouble codes for one ECU: code, description, status tags; history comm-loss codes are grouped together; clear this ECU. */
import { computed } from "vue";
import { CircleCheck } from "lucide-vue-next";
import { dtcDescription, dtcScanState, dtcStatusTags, ecuProtocolText, groupDtcs } from "@/lib/toyota";
import { currentPage } from "@/lib/toyotaNav";
import { toyotaData } from "@/lib/toyotaData";
import Badge from "../ui/Badge.vue";
import DtcClearButton from "./DtcClearButton.vue";

const ecu = computed(() => toyotaData.catalog!.ecus.find((e) => e.id === currentPage.value.arg)!);
const scan = computed(() => toyotaData.dtc.scans.find((s) => s.ecu === ecu.value.id));
const groups = computed(() => groupDtcs(scan.value?.dtcs ?? []));
</script>

<template>
  <div class="flex flex-col gap-3">
    <p class="mx-1 text-[13px] text-sl-text-2">{{ ecuProtocolText(ecu.protocol) }} · {{ ecu.id.replace("/", " sub-address ") }}</p>

    <div v-if="scan?.status !== 'ok'" class="sl-card p-5 text-center text-[13px] text-sl-text-2">
      {{ scan?.status === "malformed" ? "Bad response from this ECU, skipped" : "No response from this ECU (offline or not powered)" }}
    </div>
    <div v-else-if="dtcScanState(scan) === 'rejected'" class="sl-card p-5 text-center text-[13px] text-sl-text-2">
      ECU refused DTC read ({{ scan.readError }})
    </div>
    <div v-else-if="!scan.dtcs.length" class="sl-card flex flex-col items-center gap-1 p-5 text-[15px] text-sl-text-1">
      <CircleCheck class="size-8 text-sl-accent" />
      No trouble codes in this ECU
    </div>

    <template v-else>
      <div v-if="groups.shown.length" class="sl-card divide-y divide-sl-border overflow-hidden">
        <div v-for="d in groups.shown" :key="d.code" class="px-3.5 py-3">
          <b class="font-mono text-[15px] text-sl-text-1">{{ d.code }}</b>
          <div class="mt-0.5 text-[13px] text-sl-text-2">{{ dtcDescription(d) }}</div>
          <div class="mt-1 flex flex-wrap gap-1">
            <Badge v-for="t in dtcStatusTags(d.status)" :key="t.label" :kind="t.tone">{{ t.label }}</Badge>
          </div>
        </div>
      </div>

      <details v-if="groups.history.length" class="sl-card px-3.5 py-3">
        <summary class="cursor-pointer text-[15px] font-semibold text-sl-text-1">History comm loss ({{ groups.history.length }})</summary>
        <p class="mt-1 text-[13px] text-sl-text-2">Most likely history left over from unplugging harnesses or a power loss</p>
        <div class="mt-2 divide-y divide-sl-border">
          <div v-for="d in groups.history" :key="d.code" class="py-2">
            <b class="font-mono text-[14px] text-sl-text-1">{{ d.code }}</b>
            <div class="mt-0.5 text-[13px] text-sl-text-2">{{ dtcDescription(d) }}</div>
          </div>
        </div>
      </details>

      <DtcClearButton class="w-full" label="Clear this ECU" :ecu-ids="[ecu.id]" />
    </template>
  </div>
</template>
