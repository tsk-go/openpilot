<script setup lang="ts">
/** Modal dialog (shadcn-vue Dialog style): reka-ui headless primitives + sl theme.
 *
 * Usage: v-model:open controls visibility, title is required, content goes in the default slot.
 * Portal renders into body: re-renders of the parent (e.g. WifiPanel polling every 2s) don't affect the overlay;
 * closing via ESC / overlay click / the X in the top right is handled by DialogRoot/DialogClose,
 * and focus trapping and restoration come for free.
 */
import {
  DialogClose,
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from "reka-ui";
import { X } from "lucide-vue-next";

const props = defineProps<{
  open: boolean;
  title: string;
}>();

const emit = defineEmits<{ "update:open": [boolean] }>();
</script>

<template>
  <DialogRoot
    :open="props.open"
    @update:open="(v: boolean) => emit('update:open', v)"
  >
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/80" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2.5rem)] max-w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-sl-border bg-sl-surface p-5 shadow-lg shadow-black/40 focus:outline-none"
      >
        <DialogTitle class="text-[15px] font-semibold text-sl-text-1">
          {{ title }}
        </DialogTitle>
        <slot />
        <DialogClose
          class="absolute right-4 top-4 grid size-7 place-items-center rounded-md text-sl-text-3 opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Close"
        >
          <X class="size-4" />
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
