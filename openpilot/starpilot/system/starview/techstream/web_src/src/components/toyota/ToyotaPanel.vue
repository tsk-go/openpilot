<script setup lang="ts">
/** TechStream (Toyota diagnostics) page: session bar + page stack.
 *
 * The catalog (/api/toyota/catalog) doesn't need diagnostic mode and is fetched on mount; pages render only once it's loaded.
 * When the session ends (manual exit or idle timeout), go back home and clear scan results: values in the car may have been changed elsewhere.
 */
import { computed, onMounted, onUnmounted, watch } from "vue";
import { ChevronLeft, Loader2 } from "lucide-vue-next";
import { clearToasts } from "@/lib/store";
import { canGoBack, currentPage, goBack, resetToHome } from "@/lib/toyotaNav";
import { loadCatalog, resetScanData, toyotaData } from "@/lib/toyotaData";
import { startSessionWatch, touch, currentSessionView } from "@/lib/toyotaSession";
import Button from "../ui/Button.vue";
import ActiveTestsPage from "./ActiveTestsPage.vue";
import BackupsPage from "./BackupsPage.vue";
import BatteryPage from "./BatteryPage.vue";
import CustomizationPage from "./CustomizationPage.vue";
import DtcEcuPage from "./DtcEcuPage.vue";
import DtcPage from "./DtcPage.vue";
import HomePage from "./HomePage.vue";
import LivePage from "./LivePage.vue";
import SessionBar from "./SessionBar.vue";

const PAGE_TITLES: Record<string, string> = {
  home: "Toyota diagnostics", custom: "Customize", dtc: "Trouble codes", live: "Live data", battery: "Hybrid battery", backups: "Backups",
  tests: "Active tests",
};

const title = computed(() => {
  const { page, arg } = currentPage.value;
  const catalog = toyotaData.catalog;
  if (page === "customCat") return catalog?.categories.find((c) => c.id === arg)?.name ?? "Customize";
  if (page === "dtcEcu") return catalog?.ecus.find((e) => e.id === arg)?.name ?? "Trouble codes";
  if (page === "liveTool") return catalog?.liveTools.find((t) => t.id === arg)?.name ?? "Live data";
  return PAGE_TITLES[page] ?? "Toyota diagnostics";
});

let stopWatch: (() => void) | undefined;
onMounted(() => {
  stopWatch = startSessionWatch();
  // Sheets / toasts render under body, so clicks can only be captured on document
  document.addEventListener("click", touch, true);
  void loadCatalog();
});
onUnmounted(() => {
  stopWatch?.();
  document.removeEventListener("click", touch, true);
  clearToasts();
});

// Backups doesn't need diagnostic mode, so ending the session while on the Backups page doesn't kick back to home
watch(() => currentSessionView.value.canUseDiagnostics, (on, wasOn) => {
  if (wasOn && !on) {
    resetScanData();
    if (currentPage.value.page !== "backups") resetToHome();
  }
});
</script>

<template>
  <div class="flex w-full flex-col gap-3">
    <SessionBar />

    <div v-if="!toyotaData.catalog" class="sl-card flex flex-col items-center gap-3 px-5 py-8 text-center text-[13px] text-sl-text-2">
      <template v-if="toyotaData.catalogError">
        <p class="text-sl-danger">{{ toyotaData.catalogError }}</p>
        <Button @click="loadCatalog">Retry</Button>
      </template>
      <Loader2 v-else class="size-5 animate-spin text-sl-text-3" />
    </div>

    <template v-else>
      <header v-if="canGoBack" class="flex items-center gap-1">
        <Button variant="ghost" size="sm" aria-label="Back" @click="goBack"><ChevronLeft />Back</Button>
        <h2 class="text-[17px] font-semibold text-sl-text-1">{{ title }}</h2>
      </header>

      <HomePage v-if="currentPage.page === 'home'" />
      <CustomizationPage v-else-if="currentPage.page === 'custom' || currentPage.page === 'customCat'" />
      <DtcPage v-else-if="currentPage.page === 'dtc'" />
      <DtcEcuPage v-else-if="currentPage.page === 'dtcEcu'" />
      <LivePage v-else-if="currentPage.page === 'live' || currentPage.page === 'liveTool'" />
      <BatteryPage v-else-if="currentPage.page === 'battery'" />
      <BackupsPage v-else-if="currentPage.page === 'backups'" />
      <ActiveTestsPage v-else-if="currentPage.page === 'tests'" />
    </template>
  </div>
</template>
