"""StarLock auto-lock / auto-unlock: the car locks itself when you walk away and (optionally) unlocks when you come back.

What it uses, all from the comma's side:
  - card writes DRIVER_DOOR ({"n", "driver": "open"/"shut", "any_open", "park", "closes": driver's door closes so
    far}) only when one of them changes
  - the Bluetooth signal of the phone StarLock keeps connected, read with `btmgmt conn-info` (bluez caches it 1-3 s)
  - the owner's settings, saved by StarLock in CONFIG

Auto-lock: the driver's door closes in Park (engine on: card only runs while openpilot is started) with the phone
connected -> armed for ARM_S. The first reading below lock_dbm, or the phone dropping off, locks (StarLock's horn
pattern). A door opening or leaving Park disarms. No phone connected when the door closes -> never armed, so a dead or
forgotten phone can't lock anyone out.
Auto-unlock (only after an auto-lock, within unlock_min): the phone must first go away (below away_dbm, or off), then
come back above unlock_dbm -> unlock. Same disarming.

Costs nothing until armed: one stat() of each file every IDLE_S. Armed: one btmgmt call per reading.
"""
import json
import os
import re
import subprocess
import threading
import time

CONFIG = "/data/starview/autolock.json"
DRIVER_DOOR = "/dev/shm/starview_driver_door"
ARM_S = 60.0          # how long after the door closes it keeps looking for the walk-away
ARMED_S = 0.5         # reading interval while armed for the lock
WATCH_S = 1.0         # reading interval while waiting to unlock
IDLE_S = 0.5          # file checks while started
OFF_S = 2.0           # openpilot not started, or both switched off

DEFAULTS = {"lock": False, "unlock": False, "lock_dbm": -52, "away_dbm": -75, "unlock_dbm": -62, "unlock_min": 30,
            "sound": "horn", "lock_beeps": None, "unlock_beeps": None}
DBM = (-100, -30)


def _beeps(v):
  if v is None:
    return None
  if (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v)):
    return [int(x) for x in v]
  raise ValueError("bad beeps")


def validate(raw: dict, base: dict | None = None) -> dict:
  """Merge raw onto base (defaults) with every field checked; raises ValueError on anything out of range."""
  out = dict(base or DEFAULTS)
  if not isinstance(raw, dict):
    raise ValueError("bad settings")
  for k, v in raw.items():
    if k not in DEFAULTS:
      raise ValueError(f"unknown setting {k}")
    if k in ("lock", "unlock"):
      if not isinstance(v, bool):
        raise ValueError(f"bad {k}")
      out[k] = v
    elif k.endswith("_dbm"):
      if isinstance(v, bool) or not isinstance(v, int) or not DBM[0] <= v <= DBM[1]:
        raise ValueError(f"bad {k}")
      out[k] = v
    elif k == "unlock_min":
      if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 120:
        raise ValueError("bad unlock_min")
      out[k] = v
    elif k == "sound":
      if v not in ("horn", "buzzer", "none"):
        raise ValueError("bad sound")
      out[k] = v
    else:
      out[k] = _beeps(v)
  if out["unlock_dbm"] <= out["away_dbm"]:
    raise ValueError("the unlock line must be stronger than the walk-away line")
  return out


def load_config(path: str = CONFIG) -> dict:
  try:
    with open(path) as f:
      return validate(json.load(f))
  except (OSError, ValueError, TypeError):
    return dict(DEFAULTS)


def save_config(new: dict, path: str = CONFIG) -> dict:
  cfg = validate(new, load_config(path))
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(cfg, f)
  os.replace(tmp, path)
  return cfg


class PhoneSignal:
  """The comma's reading of the connected phone's Bluetooth signal (dBm), or None when no phone is connected."""
  CON = re.compile(r"([0-9A-Fa-f:]{17}) type (LE Random|LE Public|BR/EDR)")
  KIND = {"BR/EDR": "0", "LE Public": "1", "LE Random": "2"}

  def __init__(self, run=subprocess.run):
    self.run = run
    self.lock = threading.Lock()
    self.phone: tuple[str, str] | None = None

  def _btmgmt(self, *args) -> str:
    try:
      return self.run(["sudo", "-n", "btmgmt", *args], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
      return ""

  def _find(self):
    for addr, kind in self.CON.findall(self._btmgmt("con")):
      if kind != "BR/EDR":
        return addr, self.KIND[kind]
    return None

  def read(self) -> int | None:
    with self.lock:
      for attempt in (0, 1):
        if self.phone is None or attempt:
          self.phone = self._find()
          if self.phone is None:
            return None
        m = re.search(r"RSSI (-?\d+)", self._btmgmt("conn-info", "-t", self.phone[1], self.phone[0]))
        if m:
          return int(m.group(1))
        self.phone = None   # gone or a new address: look again once
      return None


class AutoLock:
  def __init__(self, door, signal, config_path=CONFIG, state_path=DRIVER_DOOR, clock=time.monotonic, log=lambda s: None):
    self.door = door                # (cmd, sound, beeps) -> {"ok", ...}
    self.signal = signal            # () -> dBm | None
    self.config_path, self.state_path = config_path, state_path
    self.clock, self.log = clock, log
    self.cfg = dict(DEFAULTS)
    self._cfg_mtime = None
    self._state_mtime = None
    self.state = None               # last DRIVER_DOOR seen
    self.phase = "idle"             # idle / armed / away / returning
    self.until = 0.0
    self.last = {"event": "", "dbm": None}

  def _reload(self):
    try:
      m = os.stat(self.config_path).st_mtime_ns
    except OSError:
      m = None
    if m != self._cfg_mtime:
      self._cfg_mtime = m
      self.cfg = load_config(self.config_path)

  def _door_event(self):
    """The newest DRIVER_DOOR, or None when it hasn't changed."""
    try:
      m = os.stat(self.state_path).st_mtime_ns
    except OSError:
      return None
    if m == self._state_mtime:
      return None
    self._state_mtime = m
    try:
      with open(self.state_path) as f:
        s = json.load(f)
    except (OSError, ValueError):
      return None
    prev, self.state = self.state, s
    return prev, s

  def _note(self, event):
    self.last["event"] = event
    self.log(f"autolock: {event}")

  def _act(self, cmd) -> bool:
    beeps = self.cfg["lock_beeps" if cmd == "lock" else "unlock_beeps"]
    r = self.door(cmd, self.cfg["sound"], beeps) or {}
    self._note(f"{cmd}: {r.get('result') or r.get('error') or '?'}")
    return bool(r.get("ok")) or str(r.get("result", "")).endswith("no answer from the car")

  def status(self) -> dict:
    return {"phase": self.phase, **self.last}

  def tick(self, started: bool) -> float:
    """One step; returns how long to wait before the next."""
    self._reload()
    if not started or not (self.cfg["lock"] or self.cfg["unlock"]):
      if self.phase != "idle":
        self._note("off")
      self.phase = "idle"
      return OFF_S
    now = self.clock()
    ev = self._door_event()
    if ev is not None:
      prev, s = ev
      if s.get("any_open") or not s.get("park"):
        if self.phase != "idle":
          self._note("a door opened or the car left Park: stopped")
        self.phase = "idle"
      elif (self.cfg["lock"] and prev is not None and s.get("driver") == "shut" and
            int(s.get("closes", 0)) > int(prev.get("closes", 0))):
        dbm = self.signal()
        self.last["dbm"] = dbm
        if dbm is None:
          self._note("driver's door closed, but no phone connected: not armed")
        else:
          self.phase, self.until = "armed", now + ARM_S
          self._note(f"driver's door closed, phone at {dbm} dBm: armed")
    if self.phase == "idle":
      return IDLE_S
    if now > self.until:
      self._note(f"{self.phase}: time's up")
      self.phase = "idle"
      return IDLE_S
    dbm = self.signal()
    self.last["dbm"] = dbm
    if self.phase == "armed":
      if dbm is None or dbm < self.cfg["lock_dbm"]:
        locked = self._act("lock")
        if locked and self.cfg["unlock"]:
          self.phase, self.until = "away", now + self.cfg["unlock_min"] * 60
        else:
          self.phase = "idle"
      return ARMED_S
    if self.phase == "away":
      if dbm is None or dbm < self.cfg["away_dbm"]:
        self.phase = "returning"
        self._note("you walked away: unlocks when you come back")
      return WATCH_S
    if self.phase == "returning" and dbm is not None and dbm > self.cfg["unlock_dbm"]:
      self._act("unlock")
      self.phase = "idle"
    return WATCH_S


def run(auto: AutoLock, started) -> None:
  while True:
    try:
      wait = auto.tick(bool(started()))
    except Exception as e:   # never let it die quietly: log and keep going
      auto.log(f"autolock: {e}")
      wait = OFF_S
    time.sleep(wait)
