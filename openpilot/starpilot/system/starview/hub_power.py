"""USB hub power: the comma switches its own USB-C port off a while after the car turns off, so the hub stops running
on the car battery.

The hub has its own supply, but that only runs with the car on. With the car off the hub falls back to the 5 V on the
comma's USB-C port and keeps the tablet charging, the radio dongle, the RTK receiver and the Pico running from the
car battery through the comma - until the battery is low enough for the comma's own low-voltage shutdown, and again
after every wake. The port's 5 V is the PMIC's OTG regulator: /sys/kernel/debug/regulator/smb2-vbus/enable (root only:
debugfs is 0700, and starviewd runs as the comma user, so reads and writes go through `sudo -n` like offline mode's
ip rules; comma's own chestnut flash.py power-cycles the eGPU with it). "0" = the hub and everything on it go dark.

Rules (HubPower.tick, every 0.5 s from starviewd's hub_power_thread; the car on/off is the ignition, never "offroad"):
  * car on (ignition, or openpilot started) -> port on, at once. Never off while the car is on.
  * car off after a drive -> off after the delay (tablet: 1 min - 5 h, default 5 min). The key fob's after-park window
    and StarLock's window close need the hub (radio dongle, Pico), so they last as long as the delay.
  * the log archive still copying to the USB stick when the delay is up -> on until it finishes, at most
    ARCHIVE_EXTRA_S more (patch 73): the stick is on the hub, and a copy cut off by the delay left drives behind until
    the comma deleted them. A low battery still turns it off at once.
  * the comma woke up with the car already off (a CAN wake, or the low-voltage restart loop) -> off after
    min(delay, BOOT_DELAY_S): nothing needs the hub then.
  * car off and the battery (panda voltage, smoothed over LOW_V_TAU_S) below the comma's own low-voltage cutoff
    (Parked Power's, 11.8 V on stock) + HUB_MARGIN_MV for LOW_V_S -> off at once, delay or not: the hub is the big
    load, so it goes first and the comma lasts.
  * port off and the car's CAN bus wakes after being quiet >= WAKE_QUIET_S (unlocked, a door opened) -> port on early,
    so the hub and tablet are up before the car starts; off again after the delay if it doesn't.
  * no pandaStates for 10 s -> port on (don't keep it off blind). StarView starting -> port on.
  * the comma's port working as a USB device (StarPort on a head unit, a PC with adb) -> left alone.
Settings: /data/starview/hub_power.json {"on": true, "delay_min": 5}, re-read when it changes.
"""
import json
import os
import subprocess
import time

VBUS = "/sys/kernel/debug/regulator/smb2-vbus/enable"
CFG = "/data/starview/hub_power.json"
DEFAULT_DELAY_MIN = 5
MIN_DELAY_MIN, MAX_DELAY_MIN = 1, 300
BOOT_DELAY_S = 60.0
WAKE_QUIET_S = 30.0
STALE_S = 10.0
HUB_MARGIN_MV = 200          # the hub goes off 0.2 V above the comma's own cutoff
LOW_V_S = 60.0               # smoothed voltage below that for this long
LOW_V_TAU_S = 10.0
STOCK_CUTOFF_TENTHS = 118
ARCHIVE_EXTRA_S = 20 * 60.0   # the log copy may keep the hub on this long past the delay

_open = open                 # tests swap it to act like the comma user (PermissionError on debugfs)


def clamp_delay(v) -> int:
  try:
    return max(MIN_DELAY_MIN, min(MAX_DELAY_MIN, int(round(float(v)))))
  except (TypeError, ValueError):
    return DEFAULT_DELAY_MIN


def _sudo(args, data=None):
  """(returncode, stdout) of `sudo -n <args>`; (-1, "") when sudo can't run."""
  try:
    r = subprocess.run(["sudo", "-n", *args], input=data, capture_output=True, text=True, timeout=5)
    return r.returncode, r.stdout
  except (OSError, subprocess.SubprocessError):
    return -1, ""


class HubPower:
  def __init__(self, vbus: str = VBUS, cfg: str = CFG, device_mode=lambda: False, log=print, wall=time.time,  # noqa: TID251  wall: event times
               cutoff_tenths=lambda: STOCK_CUTOFF_TENTHS, sudo=_sudo, busy=lambda: False):
    self.vbus = vbus
    self.cfg_path = cfg
    self.device_mode = device_mode     # the port is a USB device (gadget) right now: not ours to switch
    self.log = log
    self.wall = wall
    self.cutoff_tenths = cutoff_tenths  # the comma's own low-voltage cutoff (Parked Power), in 0.1 V
    self.sudo = sudo
    self.busy = busy                   # the log archive is copying to the stick on the hub (looked at only when due off)
    self.held = False                  # kept on past the delay for that copy
    self.cut = False                   # we switched the port off
    self.car = None                    # True / False / None (no panda data)
    self.off_since = None              # monotonic time the car went off (or the comma woke with it off)
    self.boot_off = False              # the comma started with the car off: the short delay
    self._seen = False                 # had a car reading since StarView started
    self._quiet_since = None           # CAN bus silent since (monotonic), None while it talks
    self.volts_mv = None               # smoothed battery voltage
    self._v_t = None
    self._low_since = None
    self._cut_tenths = (None, STOCK_CUTOFF_TENTHS)   # (read at, value): Parked Power re-read every 30 s
    self._cfg = {"on": True, "delay_min": DEFAULT_DELAY_MIN}
    self._cfg_mtime = None
    self._can_switch = (None, False)   # (checked at, result)
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

  def hub_cutoff_mv(self, now: float) -> int:
    at, v = self._cut_tenths
    if at is None or now - at >= 30.0:
      try:
        v = int(self.cutoff_tenths())
      except Exception:
        v = STOCK_CUTOFF_TENTHS
      self._cut_tenths = (now, v)
    return v * 100 + HUB_MARGIN_MV

  # ------------------------------------------------------------------ the port
  def port(self):
    """True / False from the regulator, None when it can't be read (not a comma)."""
    try:
      with _open(self.vbus) as f:
        return f.read().strip() == "1"
    except PermissionError:
      rc, out = self.sudo(["cat", self.vbus])
      return (out.strip() == "1") if rc == 0 else None
    except OSError:
      return None

  def can_switch(self, now: float) -> bool:
    at, ok = self._can_switch
    if at is None or (not ok and now - at >= 60.0):
      if os.access(self.vbus, os.W_OK):
        ok = True
      else:
        ok = self.sudo(["test", "-w", self.vbus])[0] == 0
      self._can_switch = (now, ok)
    return ok

  def _write(self, on: bool, why: str) -> bool:
    val = "1\n" if on else "0\n"
    err = None
    try:
      with _open(self.vbus, "w") as f:
        f.write(val)
    except PermissionError:
      rc, _ = self.sudo(["tee", self.vbus], val)
      if rc != 0:
        err = f"sudo tee failed ({rc})"
    except OSError as e:
      err = str(e)
    if err is not None:
      if self.error is None:
        self.log(f"starview: hub power: can't switch the USB port ({err})")
      self.error = err[:120]
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

  def _voltage(self, now: float, mv):
    if mv is None or mv < 5000:
      return
    if self.volts_mv is None or self._v_t is None:
      self.volts_mv = float(mv)
    else:
      a = min(1.0, max(0.0, now - self._v_t) / LOW_V_TAU_S)
      self.volts_mv += (mv - self.volts_mv) * a
    self._v_t = now

  def tick(self, now: float, ignition, started: bool, can_active: bool = False, volts_mv=None):
    """ignition: True / False from pandaStates, None when it's stale. can_active: CAN traffic since the last tick
    (only looked at with the car off). volts_mv: the panda's battery voltage."""
    self._voltage(now, volts_mv)
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
      self.held = False
      self.off_since = None
      self.boot_off = False
      self._quiet_since = None
      self._low_since = None
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
    low = self.volts_mv is not None and self.volts_mv < self.hub_cutoff_mv(now)
    self._low_since = (self._low_since or now) if low else None
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
        self._low_since = None
      return
    if self.device_mode():
      return
    if self._low_since is not None and now - self._low_since >= LOW_V_S:
      self._write(False, f"battery low ({self.volts_mv / 1000:.1f} V)")
    elif now - self.off_since >= self.delay_s():
      if now - self.off_since < self.delay_s() + ARCHIVE_EXTRA_S and self._busy():
        if not self.held:
          self.held = True
          self.log("starview: hub power: kept on while the log copy finishes")
        return
      self.held = False
      self._write(False, f"car off {self._fmt(now - self.off_since)}")

  def _busy(self) -> bool:
    try:
      return bool(self.busy())
    except Exception:
      return False

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
            "can_switch": self.can_switch(now),
            "car": None if self.car is None else ("on" if self.car else "off"), "cut_in_s": cut_in,
            "battery_v": None if self.volts_mv is None else round(self.volts_mv / 1000.0, 2),
            "hub_cutoff_v": round(self.hub_cutoff_mv(now) / 1000.0, 1),
            "held_for_copy": self.held, "error": self.error, "events": list(reversed(self.events[-10:]))}
