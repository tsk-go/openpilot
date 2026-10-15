<script setup lang="ts">
/** Customize page: on entry scans current values ECU by ECU (progress bar) → 8 popular items + category entries; a category subpage lists that category's settings.
 *
 * Only items actually read in the scan are shown (not shown if the ECU is offline or the car doesn't support it).
 * StarView: "Show items the car didn't list" also lists the rest of a responding ECU's catalog items, greyed; tapping one
 * reads it directly (probeSetting) and, if the ECU has it after all, opens the normal sheet.
 * Tapping a setting row opens SettingSheet; picking a value does backup → write → verify.
 */
import { computed, onMounted, ref } from "vue";
import { ChevronRight, RefreshCw } from "lucide-vue-next";
import type { ToyotaSetting } from "@/lib/schema";
import { scanTally, settingValueLabel, plural } from "@/lib/toyota";
import { iconByName } from "@/lib/toyotaIcons";
import { currentPage, goTo } from "@/lib/toyotaNav";
import { customizationScanTotal, probeSetting, scanCustomizations, toyotaData } from "@/lib/toyotaData";
import { toast } from "@/lib/store";
import { errorText } from "@/lib/toyota";
import { requireActive } from "@/lib/toyotaSession";
import Button from "../ui/Button.vue";
import Switch from "../ui/Switch.vue";
import SettingSheet from "./SettingSheet.vue";

const scan = computed(() => toyotaData.customization);
const catalog = computed(() => toyotaData.catalog!);
const tally = computed(() => scanTally(scan.value.statuses, customizationScanTotal()));

onMounted(() => { if (scan.value.state === "idle") void scanCustomizations(); });

const readable = computed(() => catalog.value.settings.filter((s) => s.key in scan.value.values));
const popular = computed(() => readable.value.filter((s) => s.popular));
/** catalog items of ECUs that answered the scan but didn't list them */
const unlisted = computed(() =>
  scan.value.showUnlisted ? catalog.value.settings.filter((s) => !(s.key in scan.value.values) && toyotaData.ecuAnswered[s.ecu]) : [],
);
const shown = computed(() => [...readable.value, ...unlisted.value]);
const categories = computed(() =>
  catalog.value.categories
    .map((c) => ({ ...c, count: shown.value.filter((s) => s.category === c.id).length }))
    .filter((c) => c.count > 0),
);
const categorySettings = computed(() => readable.value.filter((s) => s.category === currentPage.value.arg));
const categoryUnlisted = computed(() => unlisted.value.filter((s) => s.category === currentPage.value.arg));
const ecuName = (s: ToyotaSetting) => catalog.value.ecus.find((e) => e.id === s.ecu)?.name ?? s.ecu;

const trying = ref("");
async function tryRead(s: ToyotaSetting): Promise<void> {
  if (trying.value || !requireActive()) return;
  trying.value = s.key;
  try {
    await probeSetting(s.key);
    toast(`${ecuName(s)} answered - it has this setting after all`, "ok");
    editing.value = s;
  } catch (e) {
    toast(errorText(e), "error");
  } finally {
    trying.value = "";
  }
}

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
        <span class="flex-1 text-[15px] text-sl-text-1">
          {{ s.name }}
          <span v-if="scan.probed[s.key]" class="ml-1 text-[12px] text-sl-warn">not listed by the car</span>
        </span>
        <span class="max-w-[44%] text-right text-[14px] font-semibold text-sl-accent">{{ valueText(s) }}</span>
      </button>
      <button
        v-for="s in categoryUnlisted"
        :key="s.key"
        type="button"
        class="flex w-full items-center gap-3 px-3.5 py-3 text-left opacity-60 hover:bg-sl-surface-2"
        :disabled="!!trying"
        @click="tryRead(s)"
      >
        <span class="flex-1 text-[15px] text-sl-text-1">
          {{ s.name }}
          <span class="block text-[12px] text-sl-text-3">{{ ecuName(s) }} didn't list it · tap to try reading it</span>
        </span>
        <span class="text-right text-[13px] font-semibold text-sl-text-2">{{ trying === s.key ? "Reading…" : "Try" }}</span>
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
        <label class="flex items-center justify-between gap-3 px-1 py-1 text-[15px] text-sl-text-1">
          <span>
            Show items the car didn't list
            <span class="block text-[12px] text-sl-text-3">Greyed; tapping one asks the ECU for it directly. Nothing is written unless you then change it.</span>
          </span>
          <Switch v-model="scan.showUnlisted" aria-label="Show items the car didn't list" />
        </label>
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
