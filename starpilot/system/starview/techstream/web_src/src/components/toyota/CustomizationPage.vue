<script setup lang="ts">
/** Customize page: on entry scans current values ECU by ECU (progress bar) → 8 popular items + category entries; a category subpage lists that category's settings.
 *
 * Only items actually read in the scan are shown (not shown if the ECU is offline or the car doesn't support it).
 * Tapping a setting row opens SettingSheet; picking a value does backup → write → verify.
 */
import { computed, onMounted, ref } from "vue";
import { ChevronRight, RefreshCw } from "lucide-vue-next";
import type { ToyotaSetting } from "@/lib/schema";
import { scanTally, settingValueLabel, plural } from "@/lib/toyota";
import { iconByName } from "@/lib/toyotaIcons";
import { currentPage, goTo } from "@/lib/toyotaNav";
import { customizationScanTotal, scanCustomizations, toyotaData } from "@/lib/toyotaData";
import Button from "../ui/Button.vue";
import SettingSheet from "./SettingSheet.vue";

const scan = computed(() => toyotaData.customization);
const catalog = computed(() => toyotaData.catalog!);
const tally = computed(() => scanTally(scan.value.statuses, customizationScanTotal()));

onMounted(() => { if (scan.value.state === "idle") void scanCustomizations(); });

const readable = computed(() => catalog.value.settings.filter((s) => s.key in scan.value.values));
const popular = computed(() => readable.value.filter((s) => s.popular));
const categories = computed(() =>
  catalog.value.categories
    .map((c) => ({ ...c, count: readable.value.filter((s) => s.category === c.id).length }))
    .filter((c) => c.count > 0),
);
const categorySettings = computed(() => readable.value.filter((s) => s.category === currentPage.value.arg));

const editing = ref<ToyotaSetting | null>(null);
const valueText = (s: ToyotaSetting) => settingValueLabel(s, scan.value.values[s.key]?.value);
</script>

<template>
  <div v-if="scan.state !== 'done'" class="sl-card p-5 text-center">
    <b class="text-[15px] text-sl-text-1">Reading ECU <span class="sl-tabular">{{ tally.done }}/{{ tally.total }}</span></b>
    <p class="mt-1 text-[13px] text-sl-text-2">Reading {{ catalog.settings.length }} current settings (including CAN window items)</p>
    <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-sl-surface-3">
      <div class="h-full bg-sl-accent transition-[width] duration-100" :style="{ width: `${tally.percent}%` }" />
    </div>
  </div>

  <template v-else>
    <!-- Category subpage -->
    <div v-if="currentPage.page === 'customCat'" class="sl-card divide-y divide-sl-border overflow-hidden">
      <button
        v-for="s in categorySettings"
        :key="s.key"
        type="button"
        class="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-sl-surface-2"
        @click="editing = s"
      >
        <span class="flex-1 text-[15px] text-sl-text-1">{{ s.name }}</span>
        <span class="max-w-[44%] text-right text-[14px] font-semibold text-sl-accent">{{ valueText(s) }}</span>
      </button>
    </div>

    <!-- Overview: popular + all categories -->
    <div v-else class="flex flex-col gap-3">
      <p class="text-[14px] text-sl-text-2">Change hidden/adjustable vehicle features with one tap. Every change is backed up first and can be undone.</p>
      <p class="text-[12px] text-sl-text-3">Read: IG-ON or Ready · Change / Clear: use IG-ON, don't go to Ready</p>

      <div v-if="!readable.length" class="sl-card p-5 text-center text-[13px] text-sl-text-2">
        No customization items were read.
        <template v-if="scan.unreachable.length">ECUs with no response or a bad response: {{ scan.unreachable.map((e) => e.name).join(", ") }}.</template>
      </div>

      <template v-else>
        <template v-if="popular.length">
          <h2 class="mx-1 mt-2 text-[13px] font-semibold tracking-wide text-sl-text-2">Popular</h2>
          <div class="sl-card divide-y divide-sl-border overflow-hidden">
            <button
              v-for="s in popular"
              :key="s.key"
              type="button"
              class="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-sl-surface-2"
              @click="editing = s"
            >
              <span class="flex-1 text-[15px] text-sl-text-1">{{ s.name }}</span>
              <span class="max-w-[44%] text-right text-[14px] font-semibold text-sl-accent">{{ valueText(s) }}</span>
            </button>
          </div>
        </template>

        <h2 class="mx-1 mt-2 text-[13px] font-semibold tracking-wide text-sl-text-2">All categories</h2>
        <div class="sl-card divide-y divide-sl-border overflow-hidden">
          <button
            v-for="c in categories"
            :key="c.id"
            type="button"
            class="flex w-full items-center gap-3 px-3.5 py-3 text-left hover:bg-sl-surface-2"
            @click="goTo('customCat', c.id)"
          >
            <component :is="iconByName(c.icon)" class="size-5 shrink-0 text-sl-text-2" />
            <span class="flex-1 text-[15px] text-sl-text-1">{{ c.name }}</span>
            <span class="text-[13px] text-sl-text-3">{{ plural(c.count, "item") }}</span>
            <ChevronRight class="size-4 text-sl-text-3" />
          </button>
        </div>
      </template>

      <Button class="self-center" @click="scanCustomizations"><RefreshCw />Read again</Button>
    </div>
  </template>

  <SettingSheet :setting="editing" @close="editing = null" />
</template>
