<script setup lang="ts">
/** Setting bottom sheet: pick a value → confirm "old → new" → backup / write / verify → "Saved" toast with "Undo".
 *
 * Stages: pick (option list / numeric slider, collapsible technical details) → confirm → running → close.
 * The backend does backup, write and read-back verification in one request with no intermediate progress, so the three steps in running advance on a timer,
 * and the last step keeps spinning until the response arrives.
 */
import { computed, onUnmounted, ref, watch } from "vue";
import { Check, Circle, Loader2 } from "lucide-vue-next";
import { api } from "@/lib/api";
import type { ToyotaSetting } from "@/lib/schema";
import { toast } from "@/lib/store";
import { ecuProtocolText, errorText, previewRaw, restoreToast, settingValueLabel } from "@/lib/toyota";
import { applyWriteResult, invalidateCustomizationScan, toyotaData } from "@/lib/toyotaData";
import { requireActive } from "@/lib/toyotaSession";
import { cn } from "@/lib/utils";
import Button from "../ui/Button.vue";
import Sheet from "../ui/Sheet.vue";
import HexDiff from "./HexDiff.vue";

const props = defineProps<{ setting: ToyotaSetting | null }>();
const emit = defineEmits<{ close: [] }>();

const STEPS = ["Backing up", "Writing", "Verifying"];

const stage = ref<"pick" | "confirm" | "running">("pick");
const picked = ref(0);
const activeStep = ref(0);
let stepTimer: ReturnType<typeof setInterval> | undefined;

const entry = computed(() => (props.setting ? toyotaData.customization.values[props.setting.key] : undefined));
const ecu = computed(() => toyotaData.catalog?.ecus.find((e) => e.id === props.setting?.ecu));
const current = computed(() => entry.value?.value);
const label = (v: number | undefined) => (props.setting ? settingValueLabel(props.setting, v) : "");

// Reset to the pick stage each time it opens; the numeric slider starts at the current value
watch(() => props.setting, (s) => {
  stage.value = "pick";
  picked.value = s ? (toyotaData.customization.values[s.key]?.value ?? s.numeric?.min ?? 0) : 0;
});
onUnmounted(() => clearInterval(stepTimer));

function pick(value: number): void {
  picked.value = value;
  if (value === current.value) emit("close");
  else stage.value = "confirm";
}

const protocolText = computed(() => (ecu.value ? ecuProtocolText(ecu.value.protocol) : ""));
const addressText = computed(() => `0x${ecu.value?.tx}${ecu.value?.sub ? ` · sub-address 0x${ecu.value.sub}` : ""}`);
const afterRaw = computed(() => {
  const s = props.setting;
  return s && entry.value ? previewRaw(entry.value.raw, s.byteIndex, s.mask, picked.value) : "";
});

async function apply(): Promise<void> {
  const s = props.setting;
  const before = entry.value;
  if (!s || !before || !requireActive()) return;
  stage.value = "running";
  activeStep.value = 0;
  stepTimer = setInterval(() => { activeStep.value = Math.min(activeStep.value + 1, STEPS.length - 1); }, 700);
  try {
    const r = await api.toyotaWrite(s.key, picked.value, before.raw);
    applyWriteResult(s, r.after);
    toast(r.verified ? "Saved" : "Written, but read-back verification failed", r.verified ? "ok" : "warn", {
      label: "Undo",
      run: () => void undo(s, r.backupId),
    });
  } catch (e) {
    toast(errorText(e), "error");
  } finally {
    clearInterval(stepTimer);
    emit("close");
  }
}

async function undo(s: ToyotaSetting, backupId: string): Promise<void> {
  if (!requireActive()) return;
  try {
    const r = await api.toyotaRestore(backupId);
    applyWriteResult(s, r.after);
    const restored = restoreToast(s.name, settingValueLabel(s, r.value), r.verified);
    toast(restored.message, restored.tone);
  } catch (e) {
    // If undo fails the value in the car is uncertain, so make the Customize page rescan next time
    invalidateCustomizationScan();
    toast(errorText(e), "error");
  }
}
</script>

<template>
  <Sheet
    :open="setting !== null"
    :title="stage === 'pick' ? (setting?.name ?? '') : stage === 'confirm' ? 'Confirm change' : 'Applying change'"
    :description="stage === 'pick' ? ecu?.name : stage === 'confirm' ? setting?.name : undefined"
    :persistent="stage === 'running'"
    @update:open="(v) => { if (!v) emit('close'); }"
  >
    <template v-if="setting">
      <!-- Pick value -->
      <template v-if="stage === 'pick'">
        <div v-if="setting.numeric" class="mt-4">
          <div class="my-3 flex justify-center">
            <i class="sl-tabular rounded-lg bg-sl-accent-muted px-4 py-1.5 text-[20px] font-semibold not-italic text-sl-accent">{{ picked }}</i>
          </div>
          <input v-model.number="picked" type="range" :min="setting.numeric.min" :max="setting.numeric.max" class="w-full accent-sl-accent" />
          <div class="flex justify-between text-[12px] text-sl-text-2"><span>{{ setting.numeric.min }}</span><span>{{ setting.numeric.max }}</span></div>
          <Button variant="accent" class="mt-3 w-full" @click="pick(picked)">Select this value</Button>
        </div>
        <template v-else>
          <button
            v-for="o in setting.options"
            :key="o.value"
            type="button"
            :class="cn('mt-2 flex w-full items-center gap-3 rounded-[10px] border bg-sl-surface-2 px-3 py-3 text-left', o.value === current ? 'border-sl-accent' : 'border-sl-border')"
            @click="pick(o.value)"
          >
            <Check v-if="o.value === current" class="size-[18px] shrink-0 text-sl-accent" />
            <Circle v-else class="size-[18px] shrink-0 text-sl-border-strong" />
            <span class="text-[15px] text-sl-text-1">{{ o.label }}</span>
            <span v-if="o.value === current" class="ml-auto text-[12px] text-sl-accent">Current</span>
          </button>
        </template>
      </template>

      <!-- Confirm -->
      <template v-else-if="stage === 'confirm'">
        <div class="my-4 flex flex-wrap items-center justify-center gap-2.5 text-[17px]">
          <i class="rounded-lg bg-sl-surface-3 px-3 py-1.5 not-italic text-sl-text-1">{{ label(current) }}</i>
          <span class="text-sl-text-3">→</span>
          <i class="rounded-lg bg-sl-accent-muted px-3 py-1.5 font-semibold not-italic text-sl-accent">{{ label(picked) }}</i>
        </div>
        <p class="text-center text-[13px] text-sl-text-2">A backup is made first; you can undo anytime.</p>
        <p class="mt-1 text-center text-[13px] text-sl-warn">Make sure the vehicle is in IG-ON (not Ready)</p>
        <div class="mt-4 flex gap-2.5">
          <Button class="flex-1" @click="stage = 'pick'">Cancel</Button>
          <Button variant="accent" class="flex-1" @click="apply">Confirm change</Button>
        </div>
      </template>

      <!-- Writing -->
      <ul v-else class="my-3 flex flex-col">
        <li
          v-for="(t, i) in STEPS"
          :key="t"
          :class="cn('flex items-center gap-2.5 py-2 text-[15px]', i < activeStep ? 'text-sl-accent' : i === activeStep ? 'text-sl-text-1' : 'text-sl-text-3')"
        >
          <Check v-if="i < activeStep" class="size-4" />
          <Loader2 v-else-if="i === activeStep" class="size-4 animate-spin" />
          <Circle v-else class="size-4" />
          {{ t }}
        </li>
      </ul>

      <!-- Technical details (hidden while writing) -->
      <details v-if="stage !== 'running' && ecu" class="sl-card mt-4 px-3.5 py-3">
        <summary class="cursor-pointer text-[13px] text-sl-text-2">Technical details</summary>
        <table class="mt-2 w-full text-[12px]">
          <tbody class="[&_td]:border-b [&_td]:border-sl-border [&_td]:py-1 [&_td:first-child]:w-[36%] [&_td:first-child]:text-sl-text-3 [&_td:last-child]:font-mono [&_td:last-child]:text-sl-text-1">
            <tr><td>ECU</td><td class="!font-sans">{{ ecu.name }}</td></tr>
            <tr><td>Protocol</td><td class="!font-sans">{{ protocolText }}</td></tr>
            <tr><td>Request address</td><td>{{ addressText }}</td></tr>
            <tr><td>{{ setting.did ? "DID" : "Local ID" }}</td><td>{{ setting.did ?? setting.localId }}</td></tr>
            <tr><td>Byte / mask</td><td>byte {{ setting.byteIndex }} · mask 0x{{ setting.mask }}</td></tr>
            <tr><td>Current raw value</td><td class="break-all">{{ entry?.raw }}</td></tr>
          </tbody>
        </table>
        <div v-if="stage === 'confirm' && entry" class="mt-3"><HexDiff :before="entry.raw" :after="afterRaw" /></div>
      </details>
    </template>
  </Sheet>
</template>
