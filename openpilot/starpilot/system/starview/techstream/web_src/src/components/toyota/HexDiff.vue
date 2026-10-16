<script setup lang="ts">
/** Before / after hex, aligned byte by byte, with differing bytes highlighted. */
import { computed } from "vue";
import { hexDiff } from "@/lib/toyota";
import { cn } from "@/lib/utils";

const props = defineProps<{ before: string; after: string }>();
const diff = computed(() => hexDiff(props.before, props.after));
const rows = computed(() => [
  { label: "Before", bytes: diff.value.before },
  { label: "After", bytes: diff.value.after },
]);
</script>

<template>
  <div class="flex flex-col gap-2">
    <div v-for="r in rows" :key="r.label" class="flex flex-col gap-1">
      <span class="text-[11px] text-sl-text-3">{{ r.label }}</span>
      <div class="flex flex-wrap gap-1 font-mono text-[13px]">
        <span
          v-for="(b, i) in r.bytes"
          :key="i"
          :class="
            cn(
              'rounded px-1 py-0.5',
              b.changed ? 'bg-sl-warn/20 font-semibold text-sl-warn ring-1 ring-inset ring-sl-warn/40' : 'bg-sl-surface-3 text-sl-text-2',
            )
          "
        >{{ b.byte }}</span>
        <span v-if="!r.bytes.length" class="text-sl-text-3">(empty)</span>
      </div>
    </div>
  </div>
</template>
