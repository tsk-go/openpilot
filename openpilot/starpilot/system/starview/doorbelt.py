"""Doors & belts: every door and seat-belt switch of the van, checked after every drive - from the drive's own logs, so
nothing extra runs while driving.

Where the switches are on the bus:
  - standard: the driver's, passenger and both sliding doors and the driver's belt are in Toyota's BODY_CONTROL_STATE
    (0x620, bus 0), the same bits card reads for carState.doorOpen / seatbeltUnlatched
  - learned: the tablet's Learn (car on, in Park) walks through every door and belt; each switch is the bit that moves
    while you work it and hardly anywhere else (CanWatch). Saved in MAP; a learned bit wins over the standard one.

After a drive (car off: starviewd runs `doorbelt.py scan` at nice 19 / idle I/O, like the log copy) every new segment's
rlog is read once, streamed (a few MB of memory, never the whole file), and each change of a switch is written to
EVENTS with the time, speed and whether it came fast after the last one (a flicker). SCANNED keeps a line per drive
even when nothing changed, and is saved after every segment with the size EVENTS had then: a scan that is killed
(starviewd restarting, the comma powering off) never writes the same change twice.
Driving: no reader, no socket, no file - the logs already hold every CAN frame.

Live (the tablet's Doors & belts screen, car on and in Park only): CanWatch reads the "can" socket while the screen
asks, and stops IDLE_S after the last ask, or at once when the car leaves Park.
"""
import json
import os
import sys
import threading
import time
from collections import defaultdict

DIR = "/data/starview/doorbelt"
MAP = os.path.join(DIR, "bits.json")
EVENTS = os.path.join(DIR, "events.jsonl")
SCAN_LOCK = os.path.join(DIR, "scan.lock")
SCANNED = os.path.join(DIR, "scanned.json")
PROGRESS = "/dev/shm/starview_doorbelt_scan.json"
ROOT = "/data/media/0/realdata"

ITEMS = [  # (id, name, kind) - the tablet shows them in this order
  ("door_driver", "Driver's door", "door"), ("door_passenger", "Passenger door", "door"),
  ("slide_left", "Left sliding door", "door"), ("slide_right", "Right sliding door", "door"), ("hatch", "Back hatch", "door"),
  ("belt_driver", "Driver's belt", "belt"), ("belt_passenger", "Passenger belt", "belt"),
  ("belt_2l", "2nd row left belt", "belt"), ("belt_2c", "2nd row middle belt", "belt"), ("belt_2r", "2nd row right belt", "belt"),
  ("belt_3l", "3rd row left belt", "belt"), ("belt_3c", "3rd row middle belt", "belt"), ("belt_3r", "3rd row right belt", "belt"),
]
ITEM_IDS = [i[0] for i in ITEMS]
KIND = {i[0]: i[2] for i in ITEMS}
# BODY_CONTROL_STATE (0x620): DOOR_OPEN_FL 45, FR 44, RL 42, RR 43, SEATBELT_DRIVER_UNLATCHED 62 (Motorola start bit =
# byte * 8 + bit). "active" = the value that means open / buckled.
STANDARD = {
  "door_driver": {"bus": 0, "addr": 0x620, "byte": 5, "bit": 5, "active": 1},
  "door_passenger": {"bus": 0, "addr": 0x620, "byte": 5, "bit": 4, "active": 1},
  "slide_left": {"bus": 0, "addr": 0x620, "byte": 5, "bit": 2, "active": 1},
  "slide_right": {"bus": 0, "addr": 0x620, "byte": 5, "bit": 3, "active": 1},
  "belt_driver": {"bus": 0, "addr": 0x620, "byte": 7, "bit": 6, "active": 0},
}

FAST_S = 3.0           # a change this soon after the last one of the same switch is a flicker
MOVING_MS = 1.34       # 3 mph
KEEP_EVENTS = 5000     # events.jsonl is cut back to KEEP_EVENTS * 0.8 when it grows past this
KEEP_DRIVES = 200
BACKLOG_S = 7 * 86400  # the first scan (or after a new Learn) reads at most the last week of drives
LOCK_STALE_S = 300     # rlog.lock left by a crash: the segment counts as finished after this
RUN_EVERY_S = 120.0


# ------------------------------------------------------------------------------------------ files
def _read_json(path, default):
  try:
    with open(path) as f:
      return json.load(f)
  except (OSError, ValueError):
    return default


def _write_json(path, obj):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(obj, f, separators=(",", ":"))
  os.replace(tmp, path)


def learned() -> dict:
  """MAP: {"items": {id: bit dict}, "missing": [ids Learn found nothing for], "time"}."""
  m = _read_json(MAP, {})
  return m if isinstance(m, dict) else {}


def bit_map() -> dict:
  """id -> {bus, addr, byte, bit, active, source: "learned" / "standard"} for every switch that can be read."""
  out = {k: dict(v, source="standard") for k, v in STANDARD.items()}
  for k, v in (learned().get("items") or {}).items():
    if k in KIND and isinstance(v, dict) and all(isinstance(v.get(f), int) for f in ("bus", "addr", "byte", "bit", "active")):
      out[k] = {f: v[f] for f in ("bus", "addr", "byte", "bit", "active")} | {"source": "learned"}
  return out


def map_key(bits: dict) -> str:
  return json.dumps({k: [v["bus"], v["addr"], v["byte"], v["bit"], v["active"]] for k, v in sorted(bits.items())}, separators=(",", ":"))


def value(dat: bytes, b: dict):
  return (dat[b["byte"]] >> b["bit"]) & 1 if b["byte"] < len(dat) else None


def state_word(item: str, v, bits: dict) -> str | None:
  if v is None or item not in bits:
    return None
  on = v == bits[item]["active"]
  return ("open" if on else "closed") if KIND[item] == "door" else ("buckled" if on else "unbuckled")


# ------------------------------------------------------------------------------------------ live + Learn
class CanWatch:
  """Reads the "can" socket only while the tablet asks (Doors & belts screen open, or a Learn running), car on in Park.

  Learn: begin() starts recording; for each switch the tablet calls start(item), you work it (open / close or buckle /
  unbuckle twice), done(item) picks the bit that moved most inside that step and less outside it. Bits that change
  more than NOISY times (counters, checksums, speeds) are dropped as they show up. save() writes MAP."""

  IDLE_S = 10.0
  LEARN_IDLE_S = 180.0
  NOISY = 40
  SLACK_S = 2.0       # a power door still moving when Done is tapped
  STILL_S = 5.0       # after Begin the tablet asks to hold everything still this long
  WANT = 4            # open-close-open-close / buckle-unbuckle-buckle-unbuckle

  def __init__(self, ok, clock=time.monotonic, sock=None):
    self.ok = ok                    # () -> None when the car is on in Park, else the reason shown on the tablet
    self.clock = clock
    self._sock = sock               # tests hand in a fake; None = messaging.sub_sock("can") in the thread
    self.lock = threading.Lock()
    self.thread = None
    self.stop_reason = None
    self.asked = -1e9
    self._bits = {}
    self._live_keys = set()
    self._reset()

  def _reset(self):
    self.learning = False
    self.last = {}                  # (bus, addr) -> int of the data, every address while learning, mapped ones in live
    self.lens = {}
    self.noisy = defaultdict(int)   # (bus, addr) -> mask of noisy bits
    self.changes = defaultdict(list)  # (bus, addr, byte, bit) -> [(t, new value)]
    self.windows = {}               # item -> [t start, t done or None]
    self.found = {}                 # item -> candidate dict or None
    self.t0 = None

  # ---- frames
  def feed(self, t, bus, addr, dat: bytes):
    key = (bus, addr)
    if not self.learning:
      if key in self._live_keys:
        self.last[key] = dat
      return
    n = int.from_bytes(dat, "big")
    prev = self.last.get(key)
    self.last[key] = n
    if prev is None or self.lens.get(key) != len(dat):
      self.lens[key] = len(dat)
      return
    x = (prev ^ n) & ~self.noisy[key]
    while x:
      low = x & -x
      pos = low.bit_length() - 1
      x ^= low
      k = (bus, addr, len(dat) - 1 - pos // 8, pos % 8)
      ch = self.changes[k]
      ch.append((t, (n >> pos) & 1))
      if len(ch) > self.NOISY:
        self.noisy[key] |= low
        del self.changes[k]

  def _set_bits(self):
    self._bits = bit_map()
    self._live_keys = {(b["bus"], b["addr"]) for b in self._bits.values()}

  # ---- thread
  def _run(self):
    me = threading.current_thread()
    try:
      sock = self._sock
      if sock is None:
        import openpilot.cereal.messaging as messaging
        sock = messaging.sub_sock("can", conflate=False, timeout=100)
        drain = messaging.drain_sock
      else:
        drain = sock.drain
      while True:
        with self.lock:
          idle = self.LEARN_IDLE_S if self.learning else self.IDLE_S
          if self.clock() - self.asked > idle:
            self._stop(me, "idle")   # decided and recorded under one lock: a begin() right after starts a new reader
            return
        why = self.ok()
        if why:
          with self.lock:
            self._stop(me, why)
          return
        for m in drain(sock, wait_for_one=True):
          t = self.clock()
          with self.lock:
            for c in m.can:
              if c.src < 128:        # what the comma sent itself is left out
                self.feed(t, c.src, c.address, bytes(c.dat))
    except Exception as e:
      with self.lock:
        self._stop(me, f"The bus reader stopped ({e})"[:160])

  def _stop(self, me, why):
    """With the lock held: this reader is done."""
    if self.thread is me:
      self.thread = None
      self.stop_reason = why
      if self.learning:
        self.learning = False
        self.windows.clear()

  def _ensure(self):
    self.asked = self.clock()
    if self.thread is None or not self.thread.is_alive():
      self.stop_reason = None
      self.thread = threading.Thread(target=self._run, name="starview-doorbelt", daemon=True)
      self.thread.start()

  # ---- the tablet's calls
  def live(self) -> dict:
    """{item: 0/1/None} - starts / keeps the reader going for IDLE_S."""
    why = self.ok()
    if why:
      return {"ok": False, "error": why}
    with self.lock:
      self._set_bits()
      self._ensure()
      vals = {}
      for item, b in self._bits.items():
        d = self.last.get((b["bus"], b["addr"]))
        if isinstance(d, int):     # learning keeps ints
          d = d.to_bytes(self.lens.get((b["bus"], b["addr"]), 8), "big")
        vals[item] = None if d is None else value(d, b)
      return {"ok": True, "values": vals, "words": {k: state_word(k, v, self._bits) for k, v in vals.items()}, "learning": self.learning}

  def begin(self) -> dict:
    why = self.ok()
    if why:
      return {"ok": False, "error": why}
    with self.lock:
      self._reset()
      self._set_bits()
      self.learning = True
      self.t0 = self.clock()
      self._ensure()
    return {"ok": True}

  def start(self, item) -> dict:
    if item not in KIND:
      return {"ok": False, "error": "unknown switch"}
    with self.lock:
      if not self.learning:
        return {"ok": False, "error": self._stopped()}
      self.asked = self.clock()
      old = self.windows.get(item)
      if old:                        # "Again": what the earlier try moved doesn't count anywhere
        lo, hi = old[0], (old[1] if old[1] is not None else self.clock()) + self.SLACK_S
        for k in list(self.changes):
          self.changes[k] = [c for c in self.changes[k] if not lo <= c[0] <= hi]
      self.windows[item] = [self.clock(), None]
      self.found.pop(item, None)
    return {"ok": True}

  def done(self, item) -> dict:
    with self.lock:
      if not self.learning:
        return {"ok": False, "error": self._stopped()}
      w = self.windows.get(item)
      if not w:
        return {"ok": False, "error": "tap Start first"}
      self.asked = w[1] = self.clock()
      c = self._pick(item)
      self.found[item] = c
    return {"ok": True, "item": item, "found": c}

  def skip(self, item) -> dict:
    with self.lock:
      self.windows.pop(item, None)
      self.found.pop(item, None)
      self.asked = self.clock()
    return {"ok": True}

  def save(self) -> dict:
    """Picks every switch again with all the steps known (a bit that moved in several steps - the dome light, "a door
    is open" - drops out), writes MAP, stops the reader."""
    with self.lock:
      if not self.learning:
        return {"ok": False, "error": self._stopped()}
      items = {it: self._pick(it) for it, w in self.windows.items() if w[1] is not None}
      self.learning = False
      self.asked = -1e9
    old = learned()
    keep = {k: v for k, v in (old.get("items") or {}).items() if k not in items}
    got = {k: {f: c[f] for f in ("bus", "addr", "byte", "bit", "active")} for k, c in items.items() if c}
    missing = sorted((set(old.get("missing") or []) - set(items)) | {k for k, c in items.items() if not c})
    _write_json(MAP, {"items": keep | got, "missing": missing, "time": int(time.time())})  # noqa: TID251  shown as a date
    return {"ok": True, "found": items, "missing": missing}

  def cancel(self) -> dict:
    with self.lock:
      self.learning = False
      self.windows.clear()
      self.asked = -1e9
    return {"ok": True}

  def _stopped(self) -> str:
    return self.stop_reason if self.stop_reason and self.stop_reason != "idle" else "Learn stopped - start it again"

  def _pick(self, item):
    """The bit that changed at least twice in this step and more there than in all the other steps plus the first
    STILL_S (when everything is held still). Between steps doesn't count: walking through a door to the 3rd row is fine."""
    now = self.clock()
    ts, td = self.windows[item]
    hi = (td if td is not None else now) + self.SLACK_S
    other = [(a, (b if b is not None else now) + self.SLACK_S) for it, (a, b) in self.windows.items() if it != item]
    if self.t0 is not None:
      other.append((self.t0, self.t0 + self.STILL_S))
    best = []
    for (bus, addr, byte, bit), ch in self.changes.items():
      if self.noisy[(bus, addr)] >> ((self.lens.get((bus, addr), 8) - 1 - byte) * 8 + bit) & 1:
        continue
      inside = [(t, v) for t, v in ch if ts <= t <= hi]
      outside = sum(1 for t, _ in ch if any(a <= t <= b for a, b in other) and not ts <= t <= hi)
      if len(inside) < 2 or len(inside) <= outside:
        continue
      best.append(((outside, abs(len(inside) - self.WANT), bus != 0, addr, byte, bit),
                   {"bus": bus, "addr": addr, "byte": byte, "bit": bit, "active": inside[0][1], "changes": len(inside), "elsewhere": outside}))
    best.sort(key=lambda x: x[0])
    return best[0][1] if best else None


# ------------------------------------------------------------------------------------------ after the drive
def _messages(path):
  """Each capnp message of an rlog (.zst or plain), streamed: [segment count - 1][sizes][padding][segments]."""
  import zstandard as zstd
  with open(path, "rb") as raw:
    f = zstd.ZstdDecompressor().stream_reader(raw, read_size=1 << 20) if path.endswith(".zst") else raw
    buf = bytearray()
    pos = 0
    eof = False
    while True:
      if len(buf) - pos < 8:
        if eof:
          return
        chunk = f.read(1 << 20)
        if not chunk:
          eof = True
        buf = buf[pos:] + chunk
        pos = 0
        continue
      nseg = int.from_bytes(buf[pos:pos + 4], "little") + 1
      head = 4 * (nseg + 1)
      head += head % 8
      if len(buf) - pos < head:
        if eof:
          return
        chunk = f.read(1 << 20)
        eof = not chunk
        buf = buf[pos:] + chunk
        pos = 0
        continue
      size = head + 8 * sum(int.from_bytes(buf[pos + 4 + 4 * i:pos + 8 + 4 * i], "little") for i in range(nseg))
      while len(buf) - pos < size and not eof:
        chunk = f.read(max(1 << 20, size))
        eof = not chunk
        buf = buf[pos:] + chunk
        pos = 0
      if len(buf) - pos < size:
        return                      # cut short (power lost while writing)
      yield bytes(buf[pos:pos + size])
      pos += size


def scan_segment(path, bits: dict, route_state: dict, should_stop=lambda: False):
  """One rlog -> [event dicts], updating route_state {"v": {item: value}, "tc": {item: wall time of the last change}}.
  None when stopped (the car turned on)."""
  from openpilot.cereal import log
  by_key = defaultdict(list)
  for item, b in bits.items():
    by_key[(b["bus"], b["addr"])].append((item, b))
  vals = dict(route_state.get("v") or {})   # committed to route_state only when the whole segment is read
  raw_events = []                    # (mono ns, item, value, speed)
  offset = None                      # wall ns - mono ns
  speed = 0.0
  last_mono = 0
  for n, dat in enumerate(_messages(path)):
    if n % 20000 == 0 and n and should_stop():
      return None
    with log.Event.from_bytes(dat, traversal_limit_in_words=2 ** 63 - 1) as ev:
      w = ev.which()
      if w == "can":
        mono = ev.logMonoTime
        last_mono = mono
        for c in ev.can:
          lst = by_key.get((c.src, c.address))
          if lst:
            d = c.dat
            for item, b in lst:
              v = value(d, b)
              if v is None:
                continue
              old = vals.get(item)
              vals[item] = v
              if old is not None and old != v:
                raw_events.append((mono, item, v, speed))
      elif w == "carState":
        speed = ev.carState.vEgo
      elif w == "initData" and offset is None:
        if ev.initData.wallTimeNanos > 1.6e18:
          offset = ev.initData.wallTimeNanos - ev.logMonoTime
      elif w == "clocks" and offset is None:
        if ev.clocks.wallTimeNanos > 1.6e18:
          offset = ev.clocks.wallTimeNanos - ev.logMonoTime
  if offset is None:                 # no clock in the log: the rlog's own time stamp is its last write
    offset = int(os.path.getmtime(path) * 1e9) - last_mono
  tc = dict(route_state.get("tc") or {})
  out = []
  for mono, item, v, spd in raw_events:
    t = (mono + offset) / 1e9
    fast = item in tc and t - tc[item] <= FAST_S
    tc[item] = t
    out.append({"t": round(t, 2), "item": item, "v": v, "on": v == bits[item]["active"], "mph": round(spd * 2.237),
                "moving": spd > MOVING_MS, "fast": fast})
  route_state["v"] = vals
  route_state["tc"] = tc
  return out


def _segments(now):
  """Finished segments with an rlog, oldest first: [(route, number, dir name, rlog path, rlog mtime)]."""
  out = []
  try:
    names = os.listdir(ROOT)
  except OSError:
    return out
  for name in names:
    route, _, num = name.rpartition("--")
    if not route or not num.isdigit():
      continue
    d = os.path.join(ROOT, name)
    rlog = next((p for p in (os.path.join(d, "rlog.zst"), os.path.join(d, "rlog")) if os.path.exists(p)), None)
    if rlog is None:
      continue
    try:
      mt = os.path.getmtime(rlog)
    except OSError:
      continue
    if now - mt > BACKLOG_S:
      continue
    if os.path.exists(os.path.join(d, "rlog.lock")) and now - mt < LOCK_STALE_S:
      continue                      # still being written
    out.append((route, int(num), name, rlog, mt))
  out.sort(key=lambda s: (s[0], s[1]))
  return out


def _scanned(bits) -> dict:
  st = _read_json(SCANNED, {})
  key = map_key(bits)
  if not isinstance(st, dict) or st.get("map") != key:
    # a new Learn: the old history used other bits - start over and read the last week again
    try:
      os.unlink(EVENTS)
    except OSError:
      pass
    st = {"map": key, "segs": [], "routes": {}, "drives": [], "events_size": 0}
  for k, default in (("segs", []), ("routes", {}), ("drives", [])):
    if not isinstance(st.get(k), type(default)):
      st[k] = default
  # a scan killed after writing events but before saving SCANNED: cut those events, the segment is read again
  try:
    if "events_size" in st and os.path.getsize(EVENTS) > st["events_size"]:
      os.truncate(EVENTS, st["events_size"])
  except OSError:
    pass
  return st


def pending(now=None) -> int:
  """How many finished segments still wait to be read (a directory listing; cheap)."""
  now = time.time() if now is None else now  # noqa: TID251  compared with file times
  bits = bit_map()
  st = _read_json(SCANNED, {})
  done = set(st.get("segs") or []) if isinstance(st, dict) and st.get("map") == map_key(bits) else set()
  return sum(1 for s in _segments(now) if s[2] not in done)


def _append_events(evs):
  if not evs:
    return
  os.makedirs(DIR, exist_ok=True)
  with open(EVENTS, "a") as f:
    for e in evs:
      f.write(json.dumps(e, separators=(",", ":")) + "\n")
  try:
    if os.path.getsize(EVENTS) > KEEP_EVENTS * 160:
      with open(EVENTS) as f:
        lines = f.read().splitlines()
      if len(lines) > KEEP_EVENTS:
        with open(EVENTS + ".tmp", "w") as f:
          f.write("\n".join(lines[-int(KEEP_EVENTS * 0.8):]) + "\n")
        os.replace(EVENTS + ".tmp", EVENTS)
  except OSError:
    pass


def scan(should_stop=lambda: False, now=None, progress=True) -> dict:
  """Reads every finished, not yet read segment. Stops between (and inside) segments when should_stop() - the car
  turning on. {"segments": read, "events": found, "stopped": bool, "left": n}; {"busy": True} while another scan
  runs."""
  import fcntl
  os.makedirs(DIR, exist_ok=True)
  with open(SCAN_LOCK, "w") as lock:
    try:
      fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
      return {"busy": True}
    return _scan(should_stop, now, progress)


def _scan(should_stop, now, progress) -> dict:
  now = time.time() if now is None else now  # noqa: TID251  compared with file times
  bits = bit_map()
  st = _scanned(bits)
  done = set(st["segs"])
  todo = [s for s in _segments(now) if s[2] not in done]
  drives = st["drives"]
  by_route = {d.get("route"): d for d in drives}
  n_ev = 0
  read = 0
  stopped = False
  for i, (route, num, name, rlog, mt) in enumerate(todo):
    if should_stop():
      stopped = True
      break
    if progress:
      try:
        _write_json(PROGRESS, {"pid": os.getpid(), "done": i, "total": len(todo), "segment": name})
      except OSError:
        pass
    rs = st["routes"].setdefault(route, {})
    if rs.get("seg", -1) >= num:
      rs = st["routes"][route] = {}  # read again from an earlier segment: no carry-over
    try:
      evs = scan_segment(rlog, bits, rs, should_stop)
    except Exception as e:           # a damaged rlog: skip it, note why
      print(f"{name}: {e}", file=sys.stderr)
      evs = []
    if evs is None:
      stopped = True
      break
    rs["seg"] = num
    _append_events([dict(e, route=route) for e in evs])
    n_ev += len(evs)
    d = by_route.get(route)
    if d is None:
      d = by_route[route] = {"route": route, "start": round(mt - 60), "segs": 0, "changes": {}, "fast": {}, "moving": {}}
      drives.append(d)
    d["end"] = round(mt)
    d["segs"] += 1
    for e in evs:
      d["changes"][e["item"]] = d["changes"].get(e["item"], 0) + 1
      if e["fast"]:
        d["fast"][e["item"]] = d["fast"].get(e["item"], 0) + 1
      if e["moving"]:
        d["moving"][e["item"]] = d["moving"].get(e["item"], 0) + 1
    st["segs"].append(name)
    read += 1
    _save_state(st)                  # every segment: two small writes, and a kill never repeats one
  _save_state(st)
  try:
    os.unlink(PROGRESS)
  except OSError:
    pass
  return {"segments": read, "events": n_ev, "stopped": stopped, "left": len(todo) - read}


def _save_state(st):
  on_disk = set(os.listdir(ROOT)) if os.path.isdir(ROOT) else set()
  st["segs"] = [s for s in st["segs"] if s in on_disk]
  routes = {s.rpartition("--")[0] for s in st["segs"]}
  st["routes"] = {r: v for r, v in st["routes"].items() if r in routes}
  st["drives"].sort(key=lambda d: d.get("start", 0))
  del st["drives"][:-KEEP_DRIVES]
  try:
    st["events_size"] = os.path.getsize(EVENTS)
  except OSError:
    st["events_size"] = 0
  _write_json(SCANNED, st)


def scan_progress():
  p = _read_json(PROGRESS, None)
  try:
    os.kill(int(p["pid"]), 0)
    return p
  except Exception:
    return None


def history(n_events=400, n_drives=40) -> dict:
  """For the tablet: the last drives (newest first) and events (newest first)."""
  st = _read_json(SCANNED, {})
  drives = st.get("drives") if isinstance(st, dict) and isinstance(st.get("drives"), list) else []
  evs = []
  try:
    with open(EVENTS) as f:
      lines = f.read().splitlines()[-n_events:]
    for ln in reversed(lines):
      try:
        evs.append(json.loads(ln))
      except ValueError:
        pass
  except OSError:
    pass
  return {"drives": list(reversed(drives))[:n_drives], "events": evs}


def status() -> dict:
  bits = bit_map()
  lm = learned()
  missing = set(lm.get("missing") or [])
  items = [{"id": i, "name": nm, "kind": k, "source": bits[i]["source"] if i in bits else ("not on bus" if i in missing else None)}
           for i, nm, k in ITEMS]
  return {"items": items, "learnedAt": lm.get("time"), "pending": pending(), "scanning": scan_progress()}


def main(argv):
  cmd = argv[1] if len(argv) > 1 else ""
  if cmd == "scan":
    from openpilot.common.params import Params
    from openpilot.starpilot.system.starview import compat
    params = Params()
    r = scan(should_stop=lambda: compat.is_onroad(params))
    print(json.dumps(r))
  elif cmd == "status":
    print(json.dumps(status() | history(30, 10), indent=1))
  else:
    print("usage: doorbelt.py scan | status")
    return 2
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv))
