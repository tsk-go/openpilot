"""Drive replay: a recorded drive from the comma's own log files, played to the StarView tablet instead of the live data.

Parked only. The tablet can't tell it from a drive, so its lane-change card, pass and exit signals, turn signals and
Scene react as they would have on that drive; it's how they're tried out in the driveway. openpilot never sees any of
it: nothing is published on msgq, and starviewd doesn't pass the tablet's blinker requests to the relay box meanwhile.

  * Files: <log root>/<route>--<segment>/rlog.zst (qlog.zst when the full log is gone) and qcamera.ts (the small
    526x330 H.264 road video). 7.0 writes 60 s segments.
  * Each segment is read once into memory: only the services a tablet can ask for (compat.tablet_services()), and the
    qcamera frames with their times from qNarrowRoadEncodeIdx. The next segment is read ahead in the background.
  * Played on this device's clock: every event's logMonoTime (and each video frame's timestampEof) is rewritten to the
    time it is sent, so the tablet's clock pairing (Odometry.monoToLocal) and freshness checks work as when driving.
    Paused, the newest event of each service is sent again twice a second so the tablet doesn't think the comma died.
  * Stops by itself when the car isn't parked any more (ignition off is parked; on: gear P and standing still).
"""
from __future__ import annotations

import bz2
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from openpilot.cereal import log, messaging
from openpilot.common.swaglog import cloudlog
from openpilot.starpilot.system.starview import compat

SEGMENT_S = 60
QCAM_W, QCAM_H = 526, 330
VIDEO_IDX = "qNarrowRoadEncodeIdx"
# never kept: large, and nothing on the tablet's road screens reads them
DENY = {"can", "sendcan", "accelerometer", "gyroscope", "magnetometer", "temperatureSensor", "lightSensor",
        "logMessage", "errorLogMessage", "operatingSystemLog", "procLog", "qcomGnss", "ubloxRaw", "gnssMeasurements",
        "rawAudioData", "soundPressure", "thumbnail", "initData", "sentinel", "uiDebug", "userBookmark", "bookmarkButton"}
# the memory params the tablet gets (compat.MemParams) are built from these: kept as the newest of each
MEM_SOURCES = ("slcState", "starpilotNavigation")
PAUSE_RESEND_S = 0.5
TICK_S = 0.01


# ------------------------------------------------------------------------------------------ capnp framing
def _root_data_offset(buf, start: int) -> tuple[int, int] | None:
  """(byte offset of the root struct's data section, its size in bytes) for the message at `start`, None if odd."""
  nseg = struct.unpack_from("<I", buf, start)[0] + 1
  hdr = 4 * (1 + nseg)
  hdr += hdr % 8
  seg0 = start + hdr
  ptr = struct.unpack_from("<Q", buf, seg0)[0]
  if ptr & 3 != 0:
    return None
  off = (ptr >> 2) & 0x3FFFFFFF
  if off & 0x20000000:
    off -= 0x40000000
  data_words = (ptr >> 32) & 0xFFFF
  return seg0 + 8 * (1 + off), 8 * data_words


def split_messages(buf) -> list[tuple[int, int]]:
  """(start, end) of every capnp message in a log file's bytes (messages are just written one after another)."""
  return list(iter_messages(buf))


def iter_messages(buf):
  n, i = len(buf), 0
  while i + 8 <= n:
    nseg = struct.unpack_from("<I", buf, i)[0] + 1
    if nseg > 512:
      break
    hdr = 4 * (1 + nseg)
    hdr += hdr % 8
    if i + hdr > n:
      break
    words = sum(struct.unpack_from(f"<{nseg}I", buf, i + 4))
    end = i + hdr + 8 * words
    if end > n:
      break   # a segment still being written ends mid-message
    yield i, end
    i = end


def patch_mono(raw: bytearray, mono_ns: int) -> bool:
  """Rewrite Event.logMonoTime (@0, the first 8 bytes of the root struct's data section) in place."""
  try:
    loc = _root_data_offset(raw, 0)
  except struct.error:
    return False
  if loc is None or loc[1] < 8:
    return False
  struct.pack_into("<Q", raw, loc[0], mono_ns)
  return True


class _Union:
  """Event's union tag straight from the bytes (no parse): discriminant offset and value -> field name from the schema."""
  def __init__(self):
    node = log.Event.schema.node.struct
    self.offset = 2 * node.discriminantOffset
    self.names = {f.discriminantValue: f.name for f in node.fields if f.discriminantValue != 0xFFFF}

  def which(self, buf, start: int) -> tuple[str | None, int]:
    loc = _root_data_offset(buf, start)
    if loc is None:
      return None, 0
    data, size = loc
    mono = struct.unpack_from("<Q", buf, data)[0] if size >= 8 else 0
    tag = struct.unpack_from("<H", buf, data + self.offset)[0] if self.offset + 2 <= size else 0
    return self.names.get(tag), mono


_UNION = None


def _union() -> _Union:
  global _UNION
  if _UNION is None:
    _UNION = _Union()
  return _UNION


def read_log(path: Path) -> bytes:
  dat = path.read_bytes()
  if path.suffix == ".zst":
    import zstandard
    with zstandard.ZstdDecompressor().stream_reader(dat, read_across_frames=True) as r:   # as tools/lib/logreader.py
      return r.read()
  if path.suffix == ".bz2":
    return bz2.decompress(dat)
  return dat


# ------------------------------------------------------------------------------------------ qcamera.ts
def _nal_types(data: bytes) -> set[int]:
  out, i, n = set(), 0, len(data)
  while i + 3 < n:
    if data[i] == 0 and data[i + 1] == 0 and (data[i + 2] == 1 or (data[i + 2] == 0 and data[i + 3] == 1)):
      i += 3 if data[i + 2] == 1 else 4
      if i < n:
        out.add(data[i] & 0x1F)
    else:
      i += 1
  return out


def _nals(data: bytes, types: set[int]) -> bytes:
  """The NAL units of these types (start codes included)."""
  starts, i, n = [], 0, len(data)
  while i + 3 < n:
    if data[i] == 0 and data[i + 1] == 0 and (data[i + 2] == 1 or (data[i + 2] == 0 and data[i + 3] == 1)):
      starts.append(i)
      i += 3 if data[i + 2] == 1 else 4
    else:
      i += 1
  out = b""
  for k, s in enumerate(starts):
    e = starts[k + 1] if k + 1 < len(starts) else n
    sc = 3 if data[s + 2] == 1 else 4
    if s + sc < n and (data[s + sc] & 0x1F) in types:
      out += data[s:e]
  return out


def ts_frames(path: Path) -> list[tuple[int, bytes, bool]]:
  """H.264 access units of an MPEG-TS file: (pts 90 kHz or -1, Annex-B bytes, keyframe). Keyframes get the newest
  SPS/PPS put in front when they don't carry their own (the tablet's decoder starts on a keyframe)."""
  d = path.read_bytes()
  pmt_pid, vid_pid = None, None
  pes: dict[int, bytearray] = {}
  frames: list[tuple[int, bytes]] = []

  def flush(pid):
    b = pes.pop(pid, None)
    if not b or len(b) < 9 or b[0:3] != b"\x00\x00\x01":
      return
    hl = b[8]
    pts = -1
    if b[7] & 0x80 and len(b) >= 14:
      p = b[9:14]
      pts = ((p[0] >> 1) & 0x07) << 30 | p[1] << 22 | (p[2] >> 1) << 15 | p[3] << 7 | (p[4] >> 1)
    frames.append((pts, bytes(b[9 + hl:])))

  for off in range(0, len(d) - 187, 188):
    pkt = d[off:off + 188]
    if pkt[0] != 0x47:
      continue
    pusi = bool(pkt[1] & 0x40)
    pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
    afc = (pkt[3] >> 4) & 3
    i = 4
    if afc in (2, 3):
      i += 1 + pkt[4]
    if afc in (0, 2) or i >= 188:
      continue
    payload = pkt[i:]
    if pid == 0 and pusi:
      sec = payload[1 + payload[0]:]
      if len(sec) >= 16:
        pmt_pid = ((sec[10] & 0x1F) << 8) | sec[11]
    elif pid == pmt_pid and pusi and vid_pid is None:
      sec = payload[1 + payload[0]:]
      slen = ((sec[1] & 0x0F) << 8) | sec[2]
      pil = ((sec[10] & 0x0F) << 8) | sec[11]
      j, stop = 12 + pil, 3 + slen - 4
      while j + 5 <= stop:
        st, epid, eil = sec[j], ((sec[j + 1] & 0x1F) << 8) | sec[j + 2], ((sec[j + 3] & 0x0F) << 8) | sec[j + 4]
        if st == 0x1B:
          vid_pid = epid
          break
        j += 5 + eil
    elif pid == vid_pid:
      if pusi:
        flush(pid)
        pes[pid] = bytearray(payload)
      elif pid in pes:
        pes[pid] += payload
  if vid_pid is not None:
    flush(vid_pid)

  out, params = [], b""
  for pts, data in frames:
    types = _nal_types(data)
    if 7 in types and 8 in types:
      params = _nals(data, {7, 8})
    key = 5 in types
    if key and not (7 in types and 8 in types) and params:
      data = params + data
    out.append((pts, data, key))
  return out


# ------------------------------------------------------------------------------------------ segments
@dataclass
class Segment:
  number: int
  events: list[tuple[int, str, bytes]] = field(default_factory=list)   # (logMonoTime, 7.0 service, raw)
  frames: list[tuple[int, int, bytes, bool]] = field(default_factory=list)   # (timestampEof, frameId, data, key)
  t0: int = 0
  t1: int = 0
  full: bool = True


def keep_services() -> set[str]:
  keep = set()
  for name in compat.tablet_services():
    keep.update(compat.sources(name))
  return (keep | set(MEM_SOURCES)) - DENY


def load_segment(seg_dir: Path, number: int, keep: set[str] | None = None) -> Segment:
  """keep: the 7.0 services to keep (default: all a tablet can ask for). Only those are copied out of the log."""
  keep = keep_services() if keep is None else (set(keep) | set(MEM_SOURCES)) - DENY
  seg = Segment(number)
  logf = next((seg_dir / n for n in ("rlog.zst", "rlog.bz2", "rlog") if (seg_dir / n).is_file()), None)
  if logf is None:
    logf = next((seg_dir / n for n in ("qlog.zst", "qlog.bz2", "qlog") if (seg_dir / n).is_file()), None)
    seg.full = False
  if logf is None:
    raise FileNotFoundError(f"no log in {seg_dir}")
  buf = read_log(logf)
  u = _union()
  idx = []
  for s, e in iter_messages(buf):
    name, mono = u.which(buf, s)
    if name is None or mono == 0:
      continue
    if name == VIDEO_IDX:
      try:
        ei = messaging.log_from_bytes(bytes(buf[s:e])).qNarrowRoadEncodeIdx
        idx.append((int(ei.segmentId), int(ei.timestampEof) or mono, int(ei.frameId)))
      except Exception:
        pass
      continue
    if name in keep:
      seg.events.append((mono, name, bytes(buf[s:e])))
  del buf       # ~100 MB decompressed: only the copies of what's kept stay
  seg.events.sort(key=lambda x: x[0])
  if seg.events:
    seg.t0, seg.t1 = seg.events[0][0], seg.events[-1][0]
  qcam = seg_dir / "qcamera.ts"
  if qcam.is_file():
    try:
      raw_frames = ts_frames(qcam)
    except Exception as e:
      cloudlog.warning(f"starview replay: {qcam}: {e}")
      raw_frames = []
    by_id = {sid: (t, fid) for sid, t, fid in idx}
    pts0 = next((p for p, _, _ in raw_frames if p >= 0), -1)
    for k, (pts, data, key) in enumerate(raw_frames):
      if k in by_id:
        t, fid = by_id[k]
      elif pts >= 0 and pts0 >= 0 and seg.t0:
        t, fid = seg.t0 + (pts - pts0) * 100000 // 9, k     # 90 kHz -> ns
      else:
        continue
      seg.frames.append((t, fid, data, key))
    seg.frames.sort(key=lambda x: x[0])
  return seg


LOG_NAMES = ("rlog.zst", "rlog.bz2", "rlog", "qlog.zst", "qlog.bz2", "qlog")


def recording(p: Path) -> bool:
  """loggerd is writing this segment now (its lock is fresh; a crash leaves a stale one behind)."""
  try:
    return time.time() - (p / "rlog.lock").stat().st_mtime < 120  # noqa: TID251  file mtimes are wall clock
  except OSError:
    return False


def segment_dirs(root: Path, route: str) -> dict[int, Path]:
  """The finished segments of a drive that have a log: number -> folder."""
  out = {}
  try:
    for p in root.iterdir():
      if p.is_dir() and p.name.startswith(route + "--"):
        num = p.name[len(route) + 2:]
        if num.isdigit() and not recording(p) and any((p / f).is_file() for f in LOG_NAMES):
          out[int(num)] = p
  except OSError:
    pass
  return out


def recorded_version(seg_dir: Path) -> str | None:
  """openpilot version the drive was recorded with (initData, the log's first message); None if unreadable."""
  for n in ("qlog.zst", "qlog.bz2", "qlog", "rlog.zst", "rlog.bz2", "rlog"):
    if (seg_dir / n).is_file():
      try:
        buf = read_log(seg_dir / n)
        for s, e in iter_messages(buf):
          evt = messaging.log_from_bytes(bytes(buf[s:e]))
          return str(evt.initData.version) if evt.which() == "initData" else None
      except Exception:
        return None
  return None


def same_schema(recorded: str | None, current: str | None) -> bool:
  """Logs from before StarPilot 7 number some messages differently (compat.py): replay only this version line."""
  if not recorded or not current:
    return True
  return recorded.split(".")[:2] == current.split(".")[:2]


def list_drives(root: Path, limit: int = 40) -> list[dict]:
  """Recorded drives, newest first: {route, segments, minutes, first, last, start (unix s), video, full}."""
  routes: dict[str, dict[int, Path]] = {}
  try:
    for p in root.iterdir():
      if not p.is_dir() or "--" not in p.name:
        continue
      route, _, num = p.name.rpartition("--")
      if not route or not num.isdigit():
        continue
      routes.setdefault(route, {})[int(num)] = p
  except OSError:
    return []
  out = []
  for route, segs in routes.items():
    usable = {n: p for n, p in segs.items() if not recording(p) and any((p / f).is_file() for f in LOG_NAMES)}
    if not usable:
      continue
    first = min(usable)
    try:
      start = (usable[first] / "rlog.zst").stat().st_mtime - SEGMENT_S if (usable[first] / "rlog.zst").exists() else usable[first].stat().st_mtime
    except OSError:
      start = 0.0
    out.append({"route": route, "segments": len(usable), "minutes": len(usable), "first": first, "last": max(usable),
                "start": start, "video": all((p / "qcamera.ts").is_file() for p in usable.values()),
                "full": all(any((p / f).is_file() for f in ("rlog.zst", "rlog.bz2", "rlog")) for p in usable.values())})
  out.sort(key=lambda d: d["start"], reverse=True)
  for d in out:
    d["start"] = round(d["start"])
  return out[:limit]


# ------------------------------------------------------------------------------------------ player
class DriveReplay:
  """One drive at a time. on_event(service, raw_bytes, now) and on_video(payload, key) are called on the replay thread;
  parked() is asked every tick (False stops the replay). keep() -> the 7.0 services to read (what the tablet asks for).

  Every start and stop makes a new generation: a replay thread only changes state, or sends anything, while its own
  generation is the current one, so a slow old thread (a segment load takes seconds) can never touch the next replay."""

  def __init__(self, on_event, on_video, parked, root: str | Path | None = None, clock_ns=time.monotonic_ns, sleep=time.sleep,
               keep=None, version=None):
    if root is None:
      from openpilot.common.hardware.hw import Paths
      root = Paths.log_root()
    self.root = Path(root)
    self.on_event, self.on_video, self.parked = on_event, on_video, parked
    self.keep = keep
    self.version = version          # callable -> current openpilot version (None: don't check)
    self.clock_ns, self.sleep = clock_ns, sleep
    self.lock = threading.Lock()    # status, commands, latest
    self._ctl = threading.RLock()   # start / stop / control: one at a time
    self._gen = 0
    self._thread: threading.Thread | None = None
    self._stop = threading.Event()
    self._cmds: list[tuple[str, float]] = []
    self._status = {"active": False}
    self._latest: dict[str, bytes] = {}
    self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="starview-replay-load")
    self.last_result = ""

  @property
  def active(self) -> bool:
    return bool(self._status.get("active"))

  def status(self) -> dict:
    with self.lock:
      return dict(self._status, result=self.last_result)

  def drives(self) -> list[dict]:
    return list_drives(self.root)

  def latest(self, service: str):
    """For compat.MemParams while replaying: (now, event) of the newest replayed message of that service."""
    raw = self._latest.get(service)
    if raw is None:
      return None
    try:
      return time.monotonic(), messaging.log_from_bytes(raw)
    except Exception:
      return None

  def start(self, route: str, at_s: float = 0.0, speed: float = 1.0) -> dict:
    if not route or "/" in route or ".." in route:
      return {"ok": False, "error": "bad drive name"}
    speed = _clamp_speed(speed)
    at_s = at_s if isinstance(at_s, (int, float)) and at_s == at_s and at_s >= 0 else 0.0
    with self._ctl:
      segs = segment_dirs(self.root, route)
      if not segs:
        return {"ok": False, "error": "that drive isn't on the comma any more"}
      if not self.parked():
        return {"ok": False, "error": "replay only works parked"}
      cur = None
      try:
        cur = self.version() if self.version else None
      except Exception:
        pass
      if cur and not same_schema(recorded_version(segs[min(segs)]), cur):
        return {"ok": False, "error": "that drive was recorded before StarPilot 7 - it can't be replayed"}
      self.stop("another drive started")
      with self.lock:
        self._gen += 1
        gen = self._gen
        self._stop = stop_ev = threading.Event()
        self._cmds = []
        self._latest = {}
        self.last_result = ""
        self._status = {"active": True, "route": route, "t": float(at_s), "dur": float((max(segs) + 1) * SEGMENT_S),
                        "first": min(segs), "paused": False, "speed": speed, "loading": True, "video": False, "full": True}
      self._thread = threading.Thread(target=self._run, args=(gen, segs, float(at_s), speed, stop_ev),
                                      name="starview-replay", daemon=True)
      self._thread.start()
    cloudlog.info(f"starview replay: {route} from {at_s:.0f} s")
    return {"ok": True, "replay": self.status()}

  def control(self, op: str, value: float = 0.0) -> dict:
    if op == "stop":
      self.stop("stopped")
      return {"ok": True, "replay": self.status()}
    with self._ctl:
      if not self.active:
        return {"ok": False, "error": "no replay running"}
      if op not in ("pause", "resume", "toggle", "seek", "skip", "speed"):
        return {"ok": False, "error": f"unknown replay control {op}"}
      try:
        v = float(value or 0.0)
      except (TypeError, ValueError):
        return {"ok": False, "error": "bad value"}
      if v != v or abs(v) > 1e7:
        return {"ok": False, "error": "bad value"}
      with self.lock:
        self._cmds.append((op, v))
    return {"ok": True}

  def request_stop(self, why: str) -> None:
    """Stop now without waiting for the thread (the hub's reader calls this): inactive at once, nothing more is sent."""
    with self.lock:
      self._gen += 1
      self._stop.set()
      if self._status.get("active"):
        self.last_result = why
        cloudlog.info(f"starview replay: {why}")
      self._status = {"active": False}
      self._latest = {}

  def stop(self, why: str = "stopped"):
    with self._ctl:
      self.request_stop(why)
      t = self._thread
      if t is not None and t.is_alive() and threading.current_thread() is not t:
        t.join(timeout=3.0)

  # ---- the replay thread (everything below checks its generation) ----
  def _mine(self, gen) -> bool:
    return gen == self._gen

  def _set(self, gen, **kw) -> bool:
    with self.lock:
      if gen != self._gen:
        return False
      self._status.update(kw)
      return True

  def _end(self, gen, why):
    with self.lock:
      if gen != self._gen:
        return
      self._gen += 1
      self._stop.set()
      self.last_result = why
      self._status = {"active": False}
      self._latest = {}
    cloudlog.info(f"starview replay: {why}")

  def _run(self, gen, segs, at_s, speed, stop_ev):
    try:
      self._play(gen, segs, at_s, speed, stop_ev)
    except Exception as e:
      cloudlog.exception("starview replay")
      self._end(gen, f"replay failed: {e}")

  def _wanted(self):
    try:
      return self.keep() if self.keep else None
    except Exception:
      return None

  def _play(self, gen, segs, at_s, speed, stop_ev):
    numbers = sorted(segs)
    paused, pos_s = False, at_s
    ahead = {}       # segment number -> future of its load (read ahead while the one before plays)
    current = None   # the loaded segment (a seek inside it doesn't read it again)
    while not stop_ev.is_set() and self._mine(gen):
      number = next((n for n in numbers if n * SEGMENT_S + SEGMENT_S > pos_s), None)
      if number is None:
        self._end(gen, "end of the drive")
        return
      offset_ns = int(max(0.0, pos_s - number * SEGMENT_S) * 1e9)
      if current is None or current.number != number:
        self._set(gen, loading=True)
        fut = ahead.pop(number, None)
        current = None
        current = fut.result() if fut is not None else load_segment(segs[number], number, self._wanted())
      ahead.clear()
      nxt = next((n for n in numbers if n > number), None)
      if nxt is not None:
        ahead[nxt] = self._pool.submit(load_segment, segs[nxt], nxt, self._wanted())
      if not self._set(gen, loading=False, video=bool(current.frames), full=current.full):
        return
      result = self._play_segment(gen, current, offset_ns, speed, paused, stop_ev)
      if result is None:
        return
      kind, value, speed, paused = result
      pos_s = value if kind == "seek" else (nxt * SEGMENT_S if nxt is not None else (number + 1) * SEGMENT_S)

  def _play_segment(self, gen, seg: Segment, offset_ns: int, speed: float, paused: bool, stop_ev):
    """Plays one segment. Returns None (stopped), ("seek", seconds, speed, paused) or ("next", 0, speed, paused)."""
    if not seg.events:
      return "next", 0.0, speed, paused
    rec_anchor = seg.t0 + offset_ns
    dev_anchor = self.clock_ns()
    i = next((k for k, ev in enumerate(seg.events) if ev[0] >= rec_anchor), len(seg.events))
    j = next((k for k, fr in enumerate(seg.frames) if fr[0] >= rec_anchor), len(seg.frames))
    # start every stream from the newest message before the start point (state, not a jump from nothing)
    newest: dict[str, tuple[int, bytes]] = {}
    for mono, name, raw in seg.events[:i]:
      newest[name] = (mono, raw)
    pending_start = list(newest.items())
    rec_now = rec_anchor
    last_resend = 0
    key_seen = False
    while not stop_ev.is_set() and self._mine(gen):
      if not self.parked():
        self._end(gen, "the car isn't parked - replay stopped")
        return None
      with self.lock:
        cmds, self._cmds = self._cmds, []
      for op, val in cmds:
        if op in ("pause", "resume", "toggle"):
          want = {"pause": True, "resume": False}.get(op, not paused)
          if want != paused:
            paused = want
            dev_anchor = self.clock_ns() - int((rec_now - rec_anchor) / speed)
        elif op == "speed":
          speed = _clamp_speed(val)
          rec_anchor, dev_anchor = rec_now, self.clock_ns()
        elif op == "seek":
          return "seek", max(0.0, val), speed, paused
        elif op == "skip":
          return "seek", max(0.0, seg.number * SEGMENT_S + (rec_now - seg.t0) / 1e9 + val), speed, paused
      now_dev = self.clock_ns()
      if not paused:
        rec_now = rec_anchor + int((now_dev - dev_anchor) * speed)
      now = time.monotonic()
      for name, (_mono, raw) in pending_start:
        self._send(gen, name, raw, now_dev, now)
      pending_start = []
      if paused:
        if now_dev - last_resend >= PAUSE_RESEND_S * 1e9:
          last_resend = now_dev
          for name, (_mono, raw) in newest.items():
            self._send(gen, name, raw, now_dev, now)
      else:
        while i < len(seg.events) and seg.events[i][0] <= rec_now:
          mono, name, raw = seg.events[i]
          newest[name] = (mono, raw)
          if not self._send(gen, name, raw, dev_anchor + int((mono - rec_anchor) / speed), now):
            return None
          i += 1
        while j < len(seg.frames) and seg.frames[j][0] <= rec_now:
          t, fid, data, key = seg.frames[j]
          j += 1
          if not key_seen and not key:
            continue
          key_seen = True
          if not self._mine(gen):
            return None
          hdr = struct.pack("<IQQIHH", fid & 0xFFFFFFFF, dev_anchor + int((t - rec_anchor) / speed), time.time_ns(),
                            1 if key else 0, QCAM_W, QCAM_H)
          self.on_video(hdr + data, key)
      if not self._set(gen, t=round(seg.number * SEGMENT_S + (rec_now - seg.t0) / 1e9, 1), paused=paused, speed=speed):
        return None
      if i >= len(seg.events) and j >= len(seg.frames) and not paused:
        return "next", 0.0, speed, paused
      self.sleep(TICK_S)
    return None

  def _send(self, gen, name, raw, mono_ns, now) -> bool:
    if not self._mine(gen):
      return False
    b = bytearray(raw)
    patch_mono(b, mono_ns)
    b = bytes(b)
    if name in MEM_SOURCES:
      self._latest[name] = b
    self.on_event(name, b, now)
    return True


def _clamp_speed(v) -> float:
  try:
    v = float(v)
  except (TypeError, ValueError):
    return 1.0
  return 1.0 if v != v else min(max(v, 0.25), 8.0)
