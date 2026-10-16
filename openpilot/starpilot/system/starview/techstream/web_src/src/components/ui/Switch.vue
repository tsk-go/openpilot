<script setup lang="ts">
/** Switch (shadcn-vue Switch style).
 *  reka-ui SwitchRoot/Thumb provide accessibility and keyboard interaction; class names follow the official shadcn-vue
 *  conventions (data-state driven + semantic tokens), size kept at 44×26.
 */
import { SwitchRoot, SwitchThumb } from "reka-ui";
import { cn } from "@/lib/utils";

const props = defineProps<{
  modelValue: boolean;
  disabled?: boolean;
  /** Write in progress: stays visible but ignores new input, avoiding races from rapid taps */
  pending?: boolean;
  ariaLabel?: string;
}>();

const emit = defineEmits<{ "update:modelValue": [boolean] }>();
</script>

<template>
  <SwitchRoot
    :model-value="props.modelValue"
    :disabled="props.disabled || props.pending"
    :aria-label="props.ariaLabel"
    :class="
      cn(
        'peer inline-flex h-[26px] w-[44px] shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-sm transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        'data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
        (props.disabled || props.pending) && 'cursor-not-allowed opacity-50',
      )
    "
    @update:model-value="emit('update:modelValue', $event)"
  >
    <SwitchThumb
      :class="
        cn(
          'pointer-events-none block size-[22px] rounded-full bg-background shadow-lg ring-0',
          'transition-transform duration-200 ease-out will-change-transform',
          props.modelValue ? 'translate-x-[18px]' : 'translate-x-0',
          props.pending && 'animate-pulse',
        )
      "
    />
  </SwitchRoot>
</template>
