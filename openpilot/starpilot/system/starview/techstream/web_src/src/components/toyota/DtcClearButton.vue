<script setup lang="ts">
/** "Clear trouble codes" button + confirm dialog: shared by the DTC page (clear all) and the single-ECU page (clear this ECU). */
import { computed, ref } from "vue";
import { Eraser } from "lucide-vue-next";
import { toast } from "@/lib/store";
import { errorText, plural } from "@/lib/toyota";
import { clearDtcs, toyotaData } from "@/lib/toyotaData";
import { requireActive } from "@/lib/toyotaSession";
import Button from "../ui/Button.vue";
import ConfirmDialog from "./ConfirmDialog.vue";

const props = defineProps<{ label: string; ecuIds: string[] }>();

const open = ref(false);
const busy = ref(false);

const codeCount = computed(() =>
  toyotaData.dtc.scans.filter((s) => props.ecuIds.includes(s.ecu)).reduce((n, s) => n + s.dtcs.length, 0),
);

async function clear(): Promise<void> {
  if (busy.value || !requireActive()) return;
  busy.value = true;
  try {
    const results = await clearDtcs(props.ecuIds);
    const failed = results.filter((r) => !r.ok);
    if (failed.length) toast(`${plural(failed.length, "ECU")} failed to clear: ${failed[0].error ?? "ECU refused"}`, "error");
    else toast("Cleared. If the fault is still present, it will reappear on the next scan");
  } catch (e) {
    toast(errorText(e), "error");
  } finally {
    busy.value = false;
    open.value = false;
  }
}
</script>

<template>
  <Button variant="danger" :disabled="!codeCount" @click="open = true"><Eraser />{{ label }}</Button>

  <ConfirmDialog v-model:open="open" title="Clear trouble codes" confirm-text="Clear" danger :busy="busy" @confirm="clear">
    <p>This will clear {{ plural(codeCount, "trouble code") }} from {{ plural(ecuIds.length, "ECU") }}.</p>
    <p>Clearing only deletes the records, <b class="text-sl-text-1">it does not fix the fault</b>. If the fault is still present, the code will reappear.</p>
    <p class="text-sl-warn">Make sure the vehicle is in IG-ON (not Ready)</p>
  </ConfirmDialog>
</template>
