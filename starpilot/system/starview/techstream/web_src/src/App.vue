<script setup lang="ts">
/** StarView TechStream: toyopilot's Toyota diagnostics panel on its own (their LANLink app shell, sidebar and the
 *  other panels are left out). Served by starviewd at /techstream/ and shown in the StarView tablet app. */
import ToyotaPanel from "./components/toyota/ToyotaPanel.vue";
import Toasts from "./components/Toasts.vue";
</script>

<template>
  <div class="h-dvh overflow-y-auto bg-sl-bg px-4 py-5">
    <ToyotaPanel />
  </div>
  <Toasts />
</template>
