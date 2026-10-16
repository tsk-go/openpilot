/** TechStream page stack: home → feature page → subpage. Clears toasts left by the previous page on navigation. */
import { computed, ref } from "vue";
import { clearToasts } from "./store";

export type ToyotaPageName =
  | "home" | "custom" | "customCat" | "dtc" | "dtcEcu" | "live" | "liveTool" | "battery" | "backups" | "tests";

export interface ToyotaPageEntry {
  page: ToyotaPageName;
  /** Subpage argument: category id / ECU id / live data topic id */
  arg?: string;
}

const stack = ref<ToyotaPageEntry[]>([{ page: "home" }]);

export const currentPage = computed(() => stack.value[stack.value.length - 1]);
export const canGoBack = computed(() => stack.value.length > 1);

export function goTo(page: ToyotaPageName, arg?: string): void {
  clearToasts();
  stack.value.push({ page, arg });
  window.scrollTo(0, 0);
}

export function goBack(): void {
  if (stack.value.length <= 1) return;
  clearToasts();
  stack.value.pop();
}

export function resetToHome(): void {
  clearToasts();
  stack.value = [{ page: "home" }];
}
