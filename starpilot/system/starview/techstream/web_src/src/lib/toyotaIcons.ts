/** Lucide icon names (kebab-case) in the catalog → components. The catalog is a fixed set of Sienna data,
 *  so only the icons it uses are registered (lucide is not imported wholesale); unregistered names fall back to a generic icon. */
import {
  Armchair, Bell, BatteryCharging, CircleGauge, CloudRain, DoorOpen, FlipHorizontal2, Gauge, KeyRound,
  LampCeiling, Lightbulb, List, Lock, Megaphone, PackageOpen, PanelTop, Radar, ShieldCheck, Siren, Snowflake,
  Settings2, SunMoon, Thermometer,
} from "lucide-vue-next";
import type { Component } from "vue";

const ICONS: Record<string, Component> = {
  armchair: Armchair,
  bell: Bell,
  "battery-charging": BatteryCharging,
  "circle-gauge": CircleGauge,
  "cloud-rain": CloudRain,
  "door-open": DoorOpen,
  "flip-horizontal-2": FlipHorizontal2,
  gauge: Gauge,
  "key-round": KeyRound,
  "lamp-ceiling": LampCeiling,
  lightbulb: Lightbulb,
  list: List,
  lock: Lock,
  megaphone: Megaphone,
  "package-open": PackageOpen,
  "panel-top": PanelTop,
  radar: Radar,
  "shield-check": ShieldCheck,
  siren: Siren,
  snowflake: Snowflake,
  "sun-moon": SunMoon,
  thermometer: Thermometer,
};

export function iconByName(name: string): Component {
  return ICONS[name] ?? Settings2;
}
