"""USB hub power: the comma switches its own USB-C port off a while after the car turns off, so the hub stops running
on the car battery.

The hub has its own supply, but that only runs with the car on. With the car off the hub falls back to the 5 V on the
comma's USB-C port and keeps the tablet charging, the radio dongle, the RTK receiver and the Pico running from the
car battery through the comma - until the battery is low enough for the comma's own low-voltage shutdown, and again
after every wake. The port's 5 V is the PMIC's OTG regulator: /sys/kernel/debug/regulator/smb2-vbus/enable (root; comma's
own chestnut flash.py power-cycles the eGPU with it). "0" = the hub and everything on it go dark, "1" = back.

Rules (HubPower.tick, every 0.5 s from starviewd's hub_power_thread):
  * car on (ignition, or openpilot started) -> port on, at once. Never off while the car is on.
  * car off after a drive -> off after the delay (tablet: 1 min - 5 h, default 5 min). The key fob's after-park window
    and StarLock's window close need the hub (radio dongle, Pico), so they last as long as the delay.
  * the comma woke up with the car already off (a CAN wake, or the low-voltage restart loop) -> off after
    min(delay, BOOT_DELAY_S): nothing needs the hub then.
  * port off and the car's CAN bus wakes after being quiet >= WAKE_QUIET_S (unlocked, a door opened) -> port on early,
    so the hub and tablet are up before the car starts; off again after the delay if it doesn't.
  * no pandaStates for 10 s -> port on (don't keep it off blind). StarView starting -> port on.
  * the comma's port working as a USB device (StarPort on a head unit, a PC with adb) -> left alone.
Settings: /data/starview/hub_power.json {"on": true, "delay_min": 5}, re-read when it changes.
"""
import json
import os
import time

VBUS = "/sys/kernel/debug/regulator/smb2-vbus/enable"
CFG = "/data/starview/hub_power.json"
DEFAULT_DELAY_MIN = 5
MIN_DELAY_MIN, MAX_DELAY_MIN = 1, 300
BOOT_DELAY_S = 60.0
WAKE_QUIET_S = 30.0
STALE_S = 10.0


def clamp_delay(v) -> int:
  try:
    return max(MIN_DELAY_MIN, min(MAX_DELAY_MIN, int(round(float(v)))))
  except (TypeError, ValueError):
    return DEFAULT_DELAY_MIN


class HubPower:
  def __init__(self, vbus: str = VBUS, cfg: str = CFG, device_mode=lambda: False, log=print, wall=time.time):  # noqa: TID251  wall: event times
    self.vbus = vbus
    self.cfg_path = cfg
    self.device_mode = device_mode     # the port is a USB device (gadget) right now: not ours to switch
    self.log = log
    self.wall = wall
    self.cut = False                   # we switched the port off
    self.car = None                    # True / False / None (no panda data)
    self.off_since = None              # monotonic time the car went off (or the comma woke with it off)
    self.boot_off = False              # the comma started with the car off: the short delay
    self._seen = False                 # had a car reading since StarView started
    self._quiet_since = None           # CAN bus silent since (monotonic), None while it talks
    self._cfg = {"on": True, "delay_min": DEFAULT_DELAY_MIN}
    self._cfg_mtime = None
    self.events = []                   # last 20 [{t, what, why}]
    self.error = None

  # ------------------------------------------------------------------ settings
  def config(self) -> dict:
    try:
      m = os.stat(self.cfg_path).st_mtime_ns
    except OSError:
      m = None
    if m != self._cfg_mtime:
      self._cfg_mtime = m
      c = {"on": True, "delay_min": DEFAULT_DELAY_MIN}
      if m is not None:
        try:
          with open(self.cfg_path) as f:
            d = json.load(f)
          c["on"] = bool(d.get("on", True))
          c["delay_min"] = clamp_delay(d.get("delay_min", DEFAULT_DELAY_MIN))
        except (OSError, ValueError, AttributeError):
          pass
      self._cfg = c
    return dict(self._cfg)

  def set_config(self, on=None, delay_min=None) -> dict:
    c = self.config()
    if on is not None:
      c["on"] = bool(on)
    if delay_min is not None:
      c["delay_min"] = clamp_delay(delay_min)
    tmp = self.cfg_path + ".tmp"
    os.makedirs(os.path.dirname(self.cfg_path) or ".", exist_ok=True)
    with open(tmp, "w") as f:
      json.dump(c, f)
    os.replace(tmp, self.cfg_path)
    self._cfg_mtime = None
    self.config()
    return self.status(time.monotonic())

  # ------------------------------------------------------------------ the port
  def port(self):
    """True / False from the regulator, None when it can't be read (not a comma, no root)."""
    try:
      with open(self.vbus) as f:
        return f.read().strip() == "1"
    except OSError:
      return None

  def _write(self, on: bool, why: str) -> bool:
    try:
      with open(self.vbus, "w") as f:
        f.write("1\n" if on else "0\n")
    except OSError as e:
      if self.error is None:
        self.log(f"starview: hub power: can't switch the USB port ({e})")
      self.error = str(e)[:120]
      return False
    self.error = None
    self.cut = not on
    self.events = (self.events + [{"t": self.wall(), "what": "on" if on else "off", "why": why}])[-20:]
    self.log(f"starview: hub power: USB port {'on' if on else 'off'} ({why})")
    return True

  def ensure_on(self, why: str):
    if self.cut or self.port() is False:
      self._write(True, why)

  # ------------------------------------------------------------------ the rules
  def delay_s(self) -> float:
    d = self.config()["delay_min"] * 60.0
    return min(d, BOOT_DELAY_S) if self.boot_off else d

  def tick(self, now: float, ignition, started: bool, can_active: bool = False):
    """ignition: True / False from pandaStates, None when it's stale. can_active: CAN traffic since the last tick
    (only looked at with the car off)."""
    car = None if ignition is None else bool(ignition or started)
    if started:
      car = True
    first = car is not None and not self._seen
    if car is not None:
      self._seen = True
    if car is None:
      self.car = None
      if self.cut:
        self._write(True, "no data from the car")
      return
    if car:
      self.car = True
      self.off_since = None
      self.boot_off = False
      self._quiet_since = None
      if self.cut:
        self._write(True, "car on")
      return
    # the car is off
    if self.off_since is None:
      self.off_since = now
      self.boot_off = first        # the comma woke with the car already off
    self.car = False
    woke = False
    if can_active:
      woke = self._quiet_since is not None and now - self._quiet_since >= WAKE_QUIET_S
      self._quiet_since = None
    elif self._quiet_since is None:
      self._quiet_since = now
    cfg = self.config()
    if not cfg["on"]:
      if self.cut:
        self._write(True, "switched off on the tablet")
      return
    if self.cut:
      if woke:
        self._write(True, "the car woke up")
        self.off_since = now
        self.boot_off = False
      return
    if self.device_mode():
      return
    if now - self.off_since >= self.delay_s():
      self._write(False, f"car off {self._fmt(now - self.off_since)}")

  @staticmethod
  def _fmt(s: float) -> str:
    m = int(round(s / 60.0))
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{max(m, 1)} min"

  def status(self, now: float) -> dict:
    cfg = self.config()
    port = self.port()
    cut_in = None
    if cfg["on"] and self.car is False and not self.cut and self.off_since is not None:
      cut_in = max(0, int(self.delay_s() - (now - self.off_since)))
    return {"ok": True, "on": cfg["on"], "delay_min": cfg["delay_min"], "min_delay": MIN_DELAY_MIN,
            "max_delay": MAX_DELAY_MIN, "port": None if port is None else ("on" if port else "off"),
            "can_switch": os.path.exists(self.vbus) and os.access(self.vbus, os.W_OK),
            "car": None if self.car is None else ("on" if self.car else "off"), "cut_in_s": cut_in,
            "error": self.error, "events": list(reversed(self.events[-10:]))}
