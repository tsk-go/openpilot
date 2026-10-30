"""Key fob while the car runs: the owner's fob, heard through an RTL-SDR dongle (fob_radio.py), does what the car
won't do with the engine on.

  Car on, in Park:  a press of Lock or Unlock flips the locks as soon as it's decoded (~0.6 s after the press) - by
                    the driver's door (unlocked -> lock), or the opposite of what the comma itself did in the last
                    TOGGLE_MEMORY_S (the car's lock state is read every 2 s and lags). A press within REPEAT_S of the
                    last one does nothing: pressing again because it seemed slow mustn't undo it. The fob's buttons look the same
                    over the air: that part is encrypted. Same path as StarLock's buttons (starviewd._door: card ->
                    door active test, in Park, standing still), with StarLock's horn / beep settings; a refusal (the
                    car just started) is tried once more.
  Car off (for 30 min after it turns off, like StarLock's Bluetooth, and still in Park): holding a button for
                    WINDOW_AFTER_S closes the windows - relay 3, the driver's door key held to lock
                    (PicoBlinker.window), which locks the doors too - for WINDOW_RUN_S, also after letting go: the fob
                    stops sending after ~5 s however long it's held, too short for the van to start. A short press of
                    a learned fob (a new code: a hold that fades for a moment comes back with the same one), the car
                    starting or leaving Park stops it; holding again keeps it closing. Which button is held can't be told, so the wait keeps
                    the briefly-held ones (slide doors, back door, panic) from doing it. Short presses are the car's
                    own business then.
  Driving:          the radio is off.

Only the fobs learned here (their fixed ID), and never the same code twice: every press sends a new code, so one the
comma has already heard (kept across reboots) is ignored. That stops a recorded press played back as it was - not a
forged one: the fixed ID goes out in the clear and the rest can't be checked without Toyota's key.

The radio runs as two niced processes (rtl_sdr | fob_radio, nice 10) only while one of the above can happen and the dongle is
plugged in; ~1.5 % of the comma while listening, nothing otherwise. rtl_sdr is built by /data/tools/rtl_build.sh
(not part of openpilot) - without it, or without the dongle, this stays off and says why.

Settings in CONFIG: {"on": bool, "ids": [9-hex-digit fob IDs]}. Every press it hears goes to EVENTS (one JSON line),
kept under EVENTS_MAX.
"""
import glob
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque

RTL_SDR = "/data/tools/rtl/bin/rtl_sdr"
CONFIG = "/data/starview/fob.json"
EVENTS = "/data/starview/fob/events.jsonl"
EVENTS_MAX = 256 * 1024
SEEN = "/data/starview/fob/seen.json"        # codes already heard (kept across reboots)
DRIVER_DOOR = "/dev/shm/starview_driver_door"
DONGLES = {("0bda", "2838"), ("0bda", "2832")}
LEARN_S = 60.0
TICK_S = 1.0
WINDOW_AFTER_S = 2.5                          # a hold must last this long before the windows start (see above)
WINDOW_RUN_S = 15.0                           # then the "key" is held this long: every window and the sunroof
WINDOW_PULSE_S = 0.25                         # keep-alive to the relay box (it lets go 1.2 s after the last)
TOGGLE_MEMORY_S = 10.0                        # the comma's own last lock / unlock beats the lagging lock state
REPEAT_S = 5.0                                # a press this soon after the last is the same wish again, not a flip
RETRY_S = (5.0, 15.0, 60.0)
NICE = 10                                     # it only runs parked: a press shouldn't wait behind openpilot's work
SAME_CODE_BITS = 20                           # codes closer than this (of 190 bits) are the same press


def load_config(path: str = CONFIG) -> dict:
  try:
    with open(path) as f:
      raw = json.load(f)
  except (OSError, ValueError):
    raw = {}
  ids = [str(i).lower() for i in raw.get("ids", []) if _valid_id(str(i))]
  return {"on": bool(raw.get("on", True)), "ids": list(dict.fromkeys(ids))}


def save_config(cfg: dict, path: str = CONFIG) -> dict:
  cfg = {"on": bool(cfg.get("on", True)), "ids": [i for i in cfg.get("ids", []) if _valid_id(i)]}
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path + ".tmp", "w") as f:
    json.dump(cfg, f)
  os.replace(path + ".tmp", path)
  return cfg


def _valid_id(s: str) -> bool:
  return len(s) == 9 and all(c in "0123456789abcdef" for c in s.lower())


def dongle_present(root: str = "/sys/bus/usb/devices") -> bool:
  for d in glob.glob(os.path.join(root, "*")):
    try:
      with open(os.path.join(d, "idVendor")) as f:
        v = f.read().strip().lower()
      with open(os.path.join(d, "idProduct")) as f:
        p = f.read().strip().lower()
    except OSError:
      continue
    if (v, p) in DONGLES:
      return True
  return False


class Park:
  """Park from card's DRIVER_DOOR (written only when the doors or Park change): one stat() per call."""
  def __init__(self, path: str = DRIVER_DOOR):
    self.path = path
    self.mtime = None
    self.park = False

  def __call__(self) -> bool:
    try:
      m = os.stat(self.path).st_mtime_ns
    except OSError:
      self.mtime, self.park = None, False
      return False
    if m != self.mtime:
      self.mtime = m
      try:
        with open(self.path) as f:
          self.park = bool(json.load(f).get("park"))
      except (OSError, ValueError):
        self.park = False
    return self.park


def _die_with_parent() -> None:
  """In the child: SIGTERM when starviewd goes away, so a radio never outlives it holding the dongle."""
  try:
    import ctypes
    import signal
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)   # PR_SET_PDEATHSIG
  except Exception:
    pass


class Radio:
  """rtl_sdr | fob_radio, both at the lowest priority; events() yields the radio's JSON lines until it stops."""
  def __init__(self, ids):
    self.rtl = subprocess.Popen(["nice", "-n", str(NICE), RTL_SDR, "-f", "313.22M", "-s", "2560000", "-g", "40", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, preexec_fn=_die_with_parent)
    try:
      self.lis = subprocess.Popen(["nice", "-n", str(NICE), sys.executable, "-m", "openpilot.starpilot.system.starview.fob_radio",
                                   *ids], stdin=self.rtl.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                  preexec_fn=_die_with_parent)
    except OSError:
      self.rtl.kill()
      self.rtl.wait(timeout=2)
      raise
    finally:
      self.rtl.stdout.close()

  def events(self):
    for line in self.lis.stdout:
      try:
        yield json.loads(line)
      except ValueError:
        continue

  def stop(self) -> None:
    for p in (self.rtl, self.lis):
      try:
        p.terminate()
      except OSError:
        pass
    for p in (self.rtl, self.lis):
      try:
        p.wait(timeout=2)
      except subprocess.TimeoutExpired:
        p.kill()
        p.wait(timeout=2)


class FobWatch:
  def __init__(self, started, after_off, door, lock_state, window, parked=None, dongle=dongle_present,
               radio=Radio, rtl_sdr=RTL_SDR, config_path=CONFIG, events_path=EVENTS, seen_path=SEEN,
               clock=time.monotonic, wall=time.time, log=lambda s: None, run_async=None,  # noqa: TID251  wall: log times
               sleep=time.sleep):
    self.started = started          # () -> bool: openpilot started (car on)
    self.after_off = after_off      # () -> bool: car off, but turned off recently (StarLock's Bluetooth still up)
    self.door = door                # (cmd) -> {"ok", "result"/"error"}  (with StarLock's sound settings)
    self.lock_state = lock_state    # () -> {"doors": {name: "locked"/"unlocked"/None} | None, ...}
    self.window = window            # (hold) -> {"ok", ...}
    self.parked = parked or Park()
    self.dongle = dongle
    self.radio_cls = radio
    self.rtl_sdr = rtl_sdr
    self.config_path, self.events_path, self.seen_path = config_path, events_path, seen_path
    self.clock, self.wall, self.log = clock, wall, log
    self.run_async = run_async or (lambda fn: threading.Thread(target=fn, name="starview-fob-act", daemon=True).start())
    self.lock = threading.RLock()
    self.cfg = load_config(config_path)
    self._cfg_mtime = self._mtime(config_path)
    self.others = 0                 # bursts that weren't a learned fob (other transmitters, other cars' fobs)
    self.radio = None
    self.radio_ids = None
    self.state = "off"              # off / listening / starting / no dongle / no rtl_sdr / no fob learned / restarting
    self.fails = 0
    self.retry_at = 0.0
    self.learn_until = 0.0
    self.learn_seen = {}            # raw_id -> times heard while learning
    self.bursts = {}                # radio burst number -> what we know about it
    self.window_burst = None        # (burst, since, False, record) while a hold waits for WINDOW_AFTER_S
    self.window_until = 0.0         # the window relay is held until then (0: not held)
    self.window_burst_b = None      # the burst that started it: a later one stops it
    self.sleep = sleep
    self.last_cmd = None            # (cmd, when) the comma's own last lock / unlock
    self.last_code = None           # (code, when) the newest press of a learned fob
    self.busy = False               # a lock / unlock is on its way (card answers within 3 s)
    self.recent = deque(maxlen=40)
    self.seen = deque(maxlen=500)     # ~ a year of presses
    self._load_seen()

  # ---- settings / status (starviewd "fob" action) ----

  def mode(self) -> str | None:
    """"car" (on, in Park: lock / unlock), "off" (recently turned off: windows), or None (driving / long off).
    Both need Park: card's last word before the car turned off is Park; openpilot stopping while driving leaves it
    saying Drive, so that never counts as "off"."""
    if not self.parked():
      return None
    if self.started():
      return "car"
    return "off" if self.after_off() else None

  def status(self) -> dict:
    with self.lock:
      learn = max(0.0, self.learn_until - self.clock())
      return {"ok": True, "on": self.cfg["on"], "ids": list(self.cfg["ids"]), "radio": self.state, "mode": self.mode(),
              "learning": round(learn), "others": self.others, "recent": list(self.recent)[-20:]}

  def set_on(self, on: bool) -> dict:
    with self.lock:
      self.cfg = save_config({**self.cfg, "on": bool(on)}, self.config_path)
    return self.status()

  def learn(self) -> dict:
    with self.lock:
      self.learn_until = self.clock() + LEARN_S
      self.learn_seen = {}
    return self.status()

  def forget(self, fob_id: str) -> dict:
    with self.lock:
      ids = [i for i in self.cfg["ids"] if i != str(fob_id).lower()]
      self.cfg = save_config({**self.cfg, "ids": ids}, self.config_path)
    return self.status()

  def history(self, n: int = 200) -> list:
    try:
      with open(self.events_path) as f:
        lines = f.readlines()[-n:]
    except OSError:
      return []
    out = []
    for line in lines:
      try:
        out.append(json.loads(line))
      except ValueError:
        pass
    return out[::-1]

  # ---- the radio's life ----

  @staticmethod
  def _mtime(path):
    try:
      return os.stat(path).st_mtime_ns
    except OSError:
      return None

  def tick(self) -> None:
    """Every TICK_S: start the radio when it can be useful, stop it when it can't."""
    with self.lock:
      m = self._mtime(self.config_path)
      if m != self._cfg_mtime:                  # edited by hand: one stat() a second
        self._cfg_mtime = m
        self.cfg = load_config(self.config_path)
      now = self.clock()
      learning = now < self.learn_until
      if self.window_until and self.mode() != "off":
        self._stop_windows("the car isn't off in Park any more")
      want, why = self._want(learning)
      ids = list(self.cfg["ids"])
      if self.radio is not None and (not want or ids != self.radio_ids):
        self._stop_radio()
      if not want:
        self.state = why
        return
      if self.radio is None and now >= self.retry_at:
        self._start_radio(ids)

  def _want(self, learning: bool) -> tuple[bool, str]:
    if self.started() and not self.parked():
      return False, "off"                       # driving: never, not even to learn
    if not self.cfg["on"] and not learning:
      return False, "off"
    if not self.cfg["ids"] and not learning:
      return False, "no fob learned"
    if not learning and self.mode() is None:
      return False, "off"
    if not os.path.exists(self.rtl_sdr):
      return False, "no rtl_sdr"
    if not self.dongle():
      return False, "no dongle"
    return True, ""

  def _start_radio(self, ids) -> None:
    try:
      radio = self.radio_cls(ids)
    except OSError as e:
      self.log(f"fob: radio didn't start: {e}")
      self._failed()
      return
    self.radio, self.radio_ids, self.state = radio, ids, "starting"
    self.bursts = {}
    threading.Thread(target=self._read, args=(radio,), name="starview-fob-radio", daemon=True).start()

  def _read(self, radio) -> None:
    try:
      for ev in radio.events():
        with self.lock:
          if self.radio is not radio:
            return
          try:
            self.handle(ev)
          except Exception as e:     # one bad event never ends the listening
            self.log(f"fob: {ev.get('e')}: {e}")
    except Exception as e:
      self.log(f"fob: reading the radio: {e}")
    finally:
      with self.lock:
        if self.radio is radio:     # it stopped on its own (dongle pulled, crash): try again later
          self.log("fob: radio stopped")
          self.radio = None
          self._release_window("radio stopped")
          self._failed()
      try:
        radio.stop()
      except Exception:
        pass

  def _failed(self) -> None:
    self.retry_at = self.clock() + RETRY_S[min(self.fails, len(RETRY_S) - 1)]
    self.fails += 1
    self.state = "restarting"

  def _stop_radio(self) -> None:
    radio, self.radio = self.radio, None
    self._release_window("radio off")
    if radio is not None:
      try:
        radio.stop()
      except Exception as e:
        self.log(f"fob: stopping radio: {e}")

  def close(self) -> None:
    with self.lock:
      self._stop_radio()

  # ---- events ----

  def handle(self, ev: dict) -> None:
    e, b = ev.get("e"), ev.get("b")
    if e == "ready":
      self.state, self.fails = "listening", 0
      return
    if b is None:
      return
    st = self.bursts.setdefault(b, {"dec": None, "hold": False, "ended": False, "ms": 0, "done": False})
    if e == "burst":
      if st["dec"] is not None:
        return                                  # decided already (the early try matched)
      st["dec"] = ev
    elif e == "hold":
      st["hold"] = True
    elif e == "on":
      self._window_on(b, int(ev.get("ms", 0)))
      return
    elif e == "end":
      st["ended"], st["ms"] = True, int(ev.get("ms", 0))
      if self.window_burst is not None and self.window_burst[0] == b:
        self.window_burst = None
        self._record(st.get("rec") or {"t": round(self.wall(), 1), "kind": "hold"}, "nothing",
                     f"let go before {WINDOW_AFTER_S:g} s (the slide doors and panic are held briefly too)")
    else:
      return
    self._decide(b, st)
    if st["done"] and st["ended"]:
      self.bursts.pop(b, None)
    for old in [k for k in self.bursts if k < b - 20]:
      self.bursts.pop(old, None)

  def _decide(self, b: int, st: dict) -> None:
    if st["done"]:
      return
    dec = st["dec"]
    if dec is None:
      return
    car = self.mode() == "car" and self.cfg["on"] and self.clock() >= self.learn_until
    if not car and not (st["ended"] or st["hold"]):
      return                                    # car off: wait to know whether it's held too
    st["done"] = True
    kind = "hold" if st["hold"] else "press"
    ch = (312.099, 314.349)[int(dec.get("ch", 0)) % 2]
    rec = {"t": round(self.wall(), 1), "kind": kind, "mhz": ch, "fob": dec.get("raw_id"), "ours": bool(dec.get("id"))}
    if dec.get("t0"):                           # how long it took: the press started -> now (decoded, deciding)
      rec["heard_ms"] = round((self.clock() - float(dec["t0"])) * 1000)
      rec["decode_ms"], rec["lag_ms"] = dec.get("dec_ms"), dec.get("lag_ms")
    if dec.get("db") is not None:
      rec["db"] = dec["db"]                     # how far above the noise beside it: range left (a press is ~18)
    if dec.get("id") and dec.get("frame"):
      rec["frame"] = dec["frame"]               # kept for looking into the fob's code (which button, if it shows)
    code = self._code(dec.get("frame"))
    seen = code is not None and self._seen_before(code)
    if code is not None and not seen and (dec.get("id") or self.clock() < self.learn_until):
      self._remember(code)                      # every code heard counts, also learning or switched off
      self.last_code = (code, self.clock())
    if self.clock() < self.learn_until:
      self._learning(dec, rec)
      return
    if not self.cfg["on"]:
      self._record(rec, "nothing", "switched off")
      return
    if not dec.get("id") or code is None:
      self.others += 1                          # not logged: other transmitters would fill the list
      return
    if seen:
      lc = self.last_code
      if lc and self.clock() - lc[1] < 10.0 and (int(code, 2) ^ int(lc[0], 2)).bit_count() < SAME_CODE_BITS:
        self.last_code = (code, self.clock())
        return                                  # the same press heard in pieces (a hold that faded a moment)
      self._record(rec, "nothing", "a code it already heard (replayed?)")
      return
    if self.window_until:
      if kind == "hold":                        # holding again: keep closing, 15 s from now
        self.window_until = self.clock() + WINDOW_RUN_S
        self.window_burst_b = b
        self._record(rec, "windows", f"still closing - {WINDOW_RUN_S:g} s from now")
        return
      self._stop_windows("a fob press")         # a short press of a learned fob stops the windows - nothing else does
      self._record(rec, "stopped", "the windows")
      return
    mode = self.mode()
    if kind == "hold" and mode != "car":
      if mode == "off" and not st["ended"]:
        st["rec"] = rec
        self.window_burst = (b, self.clock(), False, rec)     # starts once the hold reaches WINDOW_AFTER_S
      else:
        self._record(rec, "nothing", "let go before it could start" if st["ended"] else "not listening for this now")
      return
    if mode != "car":
      self._record(rec, "nothing", "the car handles the fob itself when it's off" if mode == "off" else "not in Park")
      return
    if self.busy:
      self._record(rec, "nothing", "still doing the last press")
      return
    if self.last_cmd is not None and self.clock() - self.last_cmd[1] < REPEAT_S:
      # pressing again because it seemed slow (or from far away) must not undo it: Lock and Unlock look the same
      done = "locked" if self.last_cmd[0] == "lock" else "unlocked"
      self.last_cmd = (self.last_cmd[0], self.clock())
      self._record(rec, "nothing", f"already {done} - a press within {REPEAT_S:g} s repeats, wait to switch")
      return
    cmd = self._toggle()
    self.busy = True
    self.last_cmd = (cmd, self.clock())
    self.run_async(lambda: self._door(cmd, rec))

  def _toggle(self) -> str:
    """Lock or unlock: the opposite of the comma's own last one if it was recent (the car's lock state is read every
    2 s and lags), else by the driver's door - unlocked or unknown -> lock."""
    if self.last_cmd is not None and self.clock() - self.last_cmd[1] < TOGGLE_MEMORY_S:
      return "unlock" if self.last_cmd[0] == "lock" else "lock"
    doors = (self.lock_state() or {}).get("doors") or {}
    drv = doors.get("driver")
    if drv not in ("locked", "unlocked"):
      vals = [v for v in doors.values() if v in ("locked", "unlocked")]
      drv = "locked" if vals and "unlocked" not in vals else "unlocked"
    return "unlock" if drv == "locked" else "lock"

  def _door(self, cmd: str, rec: dict) -> None:
    t = self.clock()
    r = {}
    for attempt in (0, 1):
      try:
        r = self.door(cmd) or {}
      except Exception as e:
        r = {"ok": False, "error": str(e)}
      if r.get("ok") or attempt or "refused" not in str(r.get("result") or r.get("error") or ""):
        break
      self.sleep(0.5)                           # refused: the car just started - once more
    with self.lock:
      self.busy = False
      if not r.get("ok") and self.last_cmd and self.last_cmd[0] == cmd:
        self.last_cmd = None                    # it didn't happen: don't flip from it
      self._record({**rec, "door_ms": round((self.clock() - t) * 1000)},
                   ("locked" if cmd == "lock" else "unlocked") if r.get("ok") else f"{cmd} failed",
                   str(r.get("result") or r.get("error") or ""))

  def _window_on(self, b: int, ms: int) -> None:
    """A pulse of a held burst: once it's been held WINDOW_AFTER_S (still car off in Park), the windows close for
    WINDOW_RUN_S - the relay is kept by a thread of its own, also after the fob stops sending."""
    wb = self.window_burst
    if wb is None or wb[0] != b or ms < WINDOW_AFTER_S * 1000:
      return
    self.window_burst = None
    if self.mode() != "off":
      self._record(wb[3], "nothing", "the car isn't off in Park any more")
      return
    try:
      r = self.window(True)
    except Exception as e:
      r = {"ok": False, "error": str(e)}
    if not r.get("ok"):
      self._record(wb[3], "nothing", str(r.get("error") or "relay box didn't take it"))
      return
    started = not self.window_until
    self.window_until = self.clock() + WINDOW_RUN_S
    self.window_burst_b = b
    self._record(wb[3], "windows", f"closing for {WINDOW_RUN_S:g} s - any fob press stops it")
    if started:
      self.run_async(self._window_loop)

  def _window_loop(self) -> None:
    while True:
      with self.lock:
        if not self.window_until:
          return
        if self.clock() >= self.window_until:
          self._stop_windows(None)
          return
        try:
          self.window(True)
        except Exception as e:
          self.log(f"fob: windows: {e}")
      self.sleep(WINDOW_PULSE_S)

  def _stop_windows(self, why) -> None:
    self.window_burst = None
    if not self.window_until:
      return
    self.window_until = 0.0
    self.window_burst_b = None
    try:
      self.window(False)
    except Exception as e:
      self.log(f"fob: letting go of the windows: {e}")
    if why:
      self.log(f"fob: windows stopped ({why})")

  def _release_window(self, why) -> None:
    self._stop_windows(why)

  def _learning(self, dec: dict, rec: dict) -> None:
    rid = dec.get("raw_id")
    if not rid or int(dec.get("rep", 0)) < 2:
      self._record(rec, "nothing", "learning: couldn't read it, press again")
      return
    n = self.learn_seen.get(rid, 0) + 1
    self.learn_seen[rid] = n
    if n < 2:
      self._record(rec, "nothing", "learning: press once more")
      return
    if rid not in self.cfg["ids"]:
      self.cfg = save_config({**self.cfg, "ids": self.cfg["ids"] + [rid]}, self.config_path)
    self.learn_until = 0.0
    self._record({**rec, "fob": rid, "ours": True}, "learned", f"fob {rid} added")

  # ---- codes heard ----

  @staticmethod
  def _code(frame) -> str | None:
    """The changing part of a frame (bits 10-199) - what makes each press different."""
    if not frame:
      return None
    try:
      return format(int(frame, 16), "0256b")[10:200]
    except ValueError:
      return None

  def _seen_before(self, code: str) -> bool:
    c = int(code, 2)
    return any((c ^ int(o, 2)).bit_count() < SAME_CODE_BITS for o in self.seen)

  def _remember(self, code: str) -> None:
    self.seen.append(code)
    try:
      os.makedirs(os.path.dirname(self.seen_path) or ".", exist_ok=True)
      with open(self.seen_path + ".tmp", "w") as f:
        json.dump([f"{int(c, 2):048x}" for c in self.seen], f)
      os.replace(self.seen_path + ".tmp", self.seen_path)
    except OSError:
      pass

  def _load_seen(self) -> None:
    try:
      with open(self.seen_path) as f:
        for h in json.load(f):
          self.seen.append(format(int(h, 16), "0190b"))
    except (OSError, ValueError, TypeError):
      pass

  # ---- log ----

  def _record(self, rec: dict, did: str, why: str) -> None:
    rec = {**rec, "did": did, **({"why": why} if why else {})}
    self.recent.append(rec)
    self.log(f"fob: {rec['kind']} {rec.get('fob')}: {did} {why}")
    try:
      os.makedirs(os.path.dirname(self.events_path), exist_ok=True)
      line = json.dumps(rec, separators=(",", ":")) + "\n"
      if os.path.exists(self.events_path) and os.path.getsize(self.events_path) > EVENTS_MAX:
        with open(self.events_path) as f:
          lines = f.readlines()
        keep, size = [], 0
        for ln in reversed(lines):             # the newest half
          size += len(ln)
          if size > EVENTS_MAX // 2:
            break
          keep.append(ln)
        keep.reverse()
        with open(self.events_path + ".tmp", "w") as f:
          f.writelines(keep)
        os.replace(self.events_path + ".tmp", self.events_path)
      with open(self.events_path, "a") as f:
        f.write(line)
    except OSError as e:
      self.log(f"fob: log: {e}")


def run(watch: FobWatch) -> None:
  while True:
    try:
      watch.tick()
    except Exception as e:     # never die quietly
      watch.log(f"fob: {e}")
    time.sleep(TICK_S)
