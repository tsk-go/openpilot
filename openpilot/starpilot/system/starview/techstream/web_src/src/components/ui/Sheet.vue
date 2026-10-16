<script setup lang="ts">
/** Bottom sheet (the phone-style bottom sheet): reka-ui headless primitives + sl theme.
 *
 * Same pattern as Dialog.vue: v-model:open controls visibility, title is required, content goes in the default slot,
 * Portal renders into body. When persistent, overlay click / ESC / the X in the top right can't close it;
 * used while a write is in progress, since closing the sheet then hides the result and makes it look like nothing changed.
 */
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from "reka-ui";
import { X } from "lucide-vue-next";

const props = defineProps<{
  open: boolean;
  title: string;
  /** Small text under the title (e.g. the ECU the setting belongs to) */
  description?: string;
  persistent?: boolean;
}>();

const emit = defineEmits<{ "update:open": [boolean] }>();
</script>

<template>
  <DialogRoot :open="props.open" @update:open="(v: boolean) => emit('update:open', v)">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/70" />
      <DialogContent
        class="fixed inset-x-0 bottom-0 z-50 mx-auto max-h-[86vh] w-full overflow-y-auto rounded-t-2xl border border-b-0 border-sl-border-strong bg-sl-surface px-4 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-4 shadow-lg shadow-black/50 focus:outline-none data-[state=open]:animate-in data-[state=open]:slide-in-from-bottom data-[state=closed]:animate-out data-[state=closed]:slide-out-to-bottom"
        :aria-describedby="props.description ? undefined : ''"
        @escape-key-down="props.persistent && $event.preventDefault()"
        @interact-outside="props.persistent && $event.preventDefault()"
      >
        <DialogTitle class="pr-8 text-[17px] font-semibold text-sl-text-1">{{ props.title }}</DialogTitle>
        <DialogDescription v-if="props.description" class="text-[12px] text-sl-text-2">
          {{ props.description }}
        </DialogDescription>
        <slot />
        <DialogClose
          v-if="!props.persistent"
          class="absolute right-3 top-3 grid size-8 place-items-center rounded-md text-sl-text-3 opacity-70 transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Close"
        >
          <X class="size-4" />
        </DialogClose>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
