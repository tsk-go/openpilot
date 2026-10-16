<script setup lang="ts">
/** Button. Three looks: accent (primary action), surface (default), ghost (secondary). */
import { cn } from "@/lib/utils";

const props = withDefaults(
  defineProps<{
    variant?: "accent" | "surface" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    disabled?: boolean;
    title?: string;
  }>(),
  { variant: "surface", size: "md" },
);

const VARIANTS = {
  accent: "bg-sl-accent text-sl-accent-text hover:bg-sl-accent-hover font-semibold",
  surface: "bg-sl-surface-3 text-sl-text-1 hover:bg-sl-border ring-1 ring-inset ring-sl-border",
  ghost: "bg-transparent text-sl-text-2 hover:bg-sl-surface-2 hover:text-sl-text-1",
  danger: "bg-sl-danger/12 text-sl-danger ring-1 ring-inset ring-sl-danger/30 hover:bg-sl-danger/20",
} as const;

const SIZES = {
  sm: "h-8 px-3 text-[13px] rounded-md gap-1.5",
  // The car display is a touchscreen; primary buttons must be at least 40px tall or they're hard to hit
  md: "h-10 px-4 text-sm rounded-lg gap-2",
  lg: "h-12 px-5 text-base rounded-lg gap-2",
} as const;
</script>

<template>
  <button
    type="button"
    :disabled="props.disabled"
    :title="props.title"
    :class="
      cn(
        'inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap',
        'transition-colors duration-150 active:scale-[0.98]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        '[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
        'disabled:pointer-events-none disabled:opacity-40',
        VARIANTS[props.variant],
        SIZES[props.size],
      )
    "
  >
    <slot />
  </button>
</template>
