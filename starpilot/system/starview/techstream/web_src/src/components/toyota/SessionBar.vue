<script setup lang="ts">
/** Diagnostic session bar: not active / entering / active (idle countdown) / exiting.
 *
 * Entering diagnostic mode pauses openpilot, so a confirm dialog comes first.
 * Tapping a feature while not active increments shakeTick, which replays the shake animation here.
 */
import { computed, ref, watch } from "vue";
import { Loader2, LogOut, Power } from "lucide-vue-next";
import { countdownText } from "@/lib/toyota";
import { enter, exit, remainingS, sessionBusy, sessionNow, shakeTick, currentSessionView } from "@/lib/toyotaSession";
import { cn } from "@/lib/utils";
import Button from "../ui/Button.vue";
import ConfirmDialog from "./ConfirmDialog.vue";

const confirmOpen = ref(false);
const shaking = ref(false);

const entering = computed(() => sessionNow.value?.state === "entering");
const exiting = computed(() => sessionBusy.value && sessionNow.value?.state === "active");
const active = computed(() => sessionNow.value?.state === "active" && !exiting.value);

const title = computed(() => {
  if (entering.value) return "Entering…";
  if (exiting.value) return "Exiting…";
  return active.value ? "Diagnostic mode on" : "Diagnostic mode off";
});
const subtitle = computed(() => {
  if (entering.value) return "Stopping pandad, starting diagnostic session";
  if (exiting.value) return "Restoring pandad";
  if (active.value && remainingS.value !== null) return `Auto-exits after ${countdownText(remainingS.value)} idle · pandad stopped`;
  return currentSessionView.value.detail || "pandad running normally, vehicle features unaffected";
});

watch(shakeTick, () => {
  shaking.value = false;
  // Set it back on the next frame so the same class replays the animation
  requestAnimationFrame(() => { shaking.value = true; });
});

async function confirmEnter(): Promise<void> {
  await enter();
  confirmOpen.value = false;
}
</script>

<template>
  <section
    :class="cn('sl-card flex items-center gap-3 px-4 py-3', shaking && 'animate-sl-shake')"
    @animationend="shaking = false"
  >
    <span
      :class="cn('size-2.5 shrink-0 rounded-full', active ? 'bg-sl-accent shadow-[0_0_10px] shadow-sl-accent' : entering || exiting ? 'animate-pulse bg-sl-warn' : 'bg-sl-text-3')"
    />
    <div class="flex min-w-0 flex-1 flex-col">
      <span class="text-[15px] font-semibold text-sl-text-1">{{ title }}</span>
      <span :class="cn('truncate text-[12px]', currentSessionView.detail && !active ? 'text-sl-danger' : 'sl-tabular text-sl-text-3')">{{ subtitle }}</span>
    </div>
    <Loader2 v-if="entering || exiting" class="size-4 shrink-0 animate-spin text-sl-text-3" />
    <Button v-else-if="active" variant="danger" :disabled="!currentSessionView.canExit || sessionBusy" @click="exit">
      <LogOut />Exit
    </Button>
    <Button v-else variant="accent" :disabled="!currentSessionView.canEnter || sessionBusy" @click="confirmOpen = true">
      <Power />Enter
    </Button>

    <ConfirmDialog v-model:open="confirmOpen" title="Enter diagnostic mode" confirm-text="Enter" :busy="sessionBusy" @confirm="confirmEnter">
      <p>openpilot pauses while in diagnostic mode (pandad stops and the device treats the car as off). It resumes automatically on exit or idle timeout.</p>
      <p class="text-sl-warn">Make sure the vehicle is off, or in P and fully stopped.</p>
    </ConfirmDialog>
  </section>
</template>
