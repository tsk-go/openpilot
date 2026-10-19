"""Drive replay (replay.py): log reading, timing, pause / seek / speed, the parked guard, and starviewd's use of it."""
import os
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path

import pytest
import zstandard

from openpilot.cereal import messaging
from openpilot.starpilot.system.starview import compat, replay

T0 = 5_000_000_000_000      # the recording's own clock (ns): an old boot of the comma


def _evt(name, mono, **fill):
  m = messaging.new_message(name, 1) if name == "can" else messaging.new_message(name)
  m.logMonoTime = mono
  sub = getattr(m, name)
  for k, v in fill.items():
    setattr(sub, k, v)
  return m.to_bytes()


def write_segment(d: Path, number: int, seconds=3.0, t0=T0, video=True):
  """A 7.0-like segment: carState 100 Hz (vEgo = seconds into the segment), modelV2 20 Hz, starpilotNavigation 2 Hz,
  can 100 Hz (never replayed), qNarrowRoadEncodeIdx + qcamera.ts at 20 fps."""
  d.mkdir(parents=True, exist_ok=True)
  out = []
  n = int(seconds * 100)
  for k in range(n):
    mono = t0 + k * 10_000_000
    out.append(_evt("carState", mono, vEgo=k / 100.0))
    out.append(_evt("can", mono))
    if k % 5 == 0:
      out.append(_evt("modelV2", mono + 1, frameId=k // 5))
      if video:
        idx = messaging.new_message("qNarrowRoadEncodeIdx")
        idx.logMonoTime = mono + 2
        ei = idx.qNarrowRoadEncodeIdx
        ei.frameId, ei.segmentNum, ei.segmentId, ei.timestampEof = k // 5, number, k // 5, mono
        out.append(idx.to_bytes())
    if k % 50 == 0:
      nav = messaging.new_message("starpilotNavigation")
      nav.logMonoTime = mono + 3
      nv = nav.starpilotNavigation.navigation
      nv.version, nv.enabled, nv.status = 2, True, "guiding"
      nv.instruction.text, nv.instruction.maneuverType, nv.instruction.maneuverModifier = "Exit 19", "off ramp", "slightRight"
      nv.instruction.distanceMeters = 300.0 - k
      out.append(nav.to_bytes())
  (d / "rlog.zst").write_bytes(zstandard.ZstdCompressor().compress(b"".join(out)))
  if video:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={replay.QCAM_W}x{replay.QCAM_H}:rate=20",
                    "-t", str(seconds), "-c:v", "libx264", "-g", "15", "-pix_fmt", "yuv420p", "-f", "mpegts", str(d / "qcamera.ts")],
                   check=True)


need_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


# ------------------------------------------------------------------------------------------ files
def test_split_and_tag_match_a_real_parse(tmp_path):
  write_segment(tmp_path / "r--0", 0, seconds=0.2, video=False)
  buf = replay.read_log(tmp_path / "r--0" / "rlog.zst")
  spans = replay.split_messages(buf)
  assert len(spans) == 20 * 2 + 4 + 1
  u = replay._union()
  for s, e in spans:
    evt = messaging.log_from_bytes(bytes(buf[s:e]))
    assert u.which(buf, s) == (evt.which(), evt.logMonoTime)


def test_truncated_tail_is_left_out(tmp_path):
  write_segment(tmp_path / "r--0", 0, seconds=0.1, video=False)
  buf = replay.read_log(tmp_path / "r--0" / "rlog.zst")
  full = replay.split_messages(buf)
  assert replay.split_messages(buf[:full[-1][1] - 3]) == full[:-1]     # a segment still being written


def test_log_written_in_several_zstd_frames(tmp_path):
  a, b = _evt("carState", 1, vEgo=1.0), _evt("carState", 2, vEgo=2.0)
  c = zstandard.ZstdCompressor()
  (tmp_path / "rlog.zst").write_bytes(c.compress(a) + c.compress(b))
  assert replay.read_log(tmp_path / "rlog.zst") == a + b


def test_patch_mono_rewrites_only_the_time():
  raw = bytearray(_evt("carState", 123, vEgo=4.5))
  assert replay.patch_mono(raw, 987654321)
  evt = messaging.log_from_bytes(bytes(raw))
  assert evt.logMonoTime == 987654321 and evt.carState.vEgo == 4.5


@need_ffmpeg
def test_segment_keeps_tablet_services_and_times_video(tmp_path):
  write_segment(tmp_path / "r--0", 0, seconds=2.0)
  seg = replay.load_segment(tmp_path / "r--0", 0)
  names = {n for _, n, _ in seg.events}
  assert {"carState", "modelV2", "starpilotNavigation"} <= names and "can" not in names
  assert seg.t0 == T0 and seg.full
  assert len(seg.frames) == 40
  assert [f[0] for f in seg.frames[:3]] == [T0, T0 + 50_000_000, T0 + 100_000_000]     # qNarrowRoadEncodeIdx times
  keys = [f for f in seg.frames if f[3]]
  assert keys and all(7 in replay._nal_types(f[2]) and 8 in replay._nal_types(f[2]) for f in keys)


def test_list_drives_newest_first_and_skips_the_one_recording(tmp_path):
  write_segment(tmp_path / "aaa--0", 0, seconds=0.1, video=False)
  write_segment(tmp_path / "aaa--1", 1, seconds=0.1, video=False)
  write_segment(tmp_path / "bbb--0", 0, seconds=0.1, video=False)
  os.utime(tmp_path / "aaa--0" / "rlog.zst", (1_700_000_000, 1_700_000_000))
  os.utime(tmp_path / "bbb--0" / "rlog.zst", (1_700_000_500, 1_700_000_500))
  write_segment(tmp_path / "ccc--0", 0, seconds=0.1, video=False)
  (tmp_path / "ccc--0" / "rlog.lock").write_text("")
  (tmp_path / "boot").mkdir()
  write_segment(tmp_path / "ddd--0", 0, seconds=0.1, video=False)       # a lock left behind by a crash: finished
  (tmp_path / "ddd--0" / "rlog.lock").write_text("")
  os.utime(tmp_path / "ddd--0" / "rlog.lock", (1_600_000_000, 1_600_000_000))
  os.utime(tmp_path / "ddd--0" / "rlog.zst", (1_600_000_000, 1_600_000_000))
  drives = replay.list_drives(tmp_path)
  assert [d["route"] for d in drives] == ["bbb", "aaa", "ddd"]
  assert drives[1]["segments"] == 2 and drives[1]["full"] and not drives[1]["video"]
  assert replay.segment_dirs(tmp_path, "ccc") == {}                      # never replays the segment being written
  write_segment(tmp_path / "aaa--2", 2, seconds=0.1, video=False)
  (tmp_path / "aaa--2" / "rlog.lock").write_text("")
  assert sorted(replay.segment_dirs(tmp_path, "aaa")) == [0, 1]


def test_only_the_services_asked_for_are_kept(tmp_path):
  write_segment(tmp_path / "r--0", 0, seconds=0.5, video=False)
  seg = replay.load_segment(tmp_path / "r--0", 0, keep={"carState", "can"})
  assert {n for _, n, _ in seg.events} == {"carState", "starpilotNavigation"}   # + the memory params' sources, never can


def _with_version(d: Path, version: str):
  init = messaging.new_message("initData")
  init.logMonoTime = T0 - 1
  init.initData.version = version
  buf = init.to_bytes() + replay.read_log(d / "rlog.zst")
  (d / "rlog.zst").write_bytes(zstandard.ZstdCompressor().compress(buf))


def test_drives_from_another_version_line_are_refused(tmp_path):
  write_segment(tmp_path / "old--0", 0, seconds=0.2, video=False)
  _with_version(tmp_path / "old--0", "0.10.1")
  write_segment(tmp_path / "new--0", 0, seconds=0.2, video=False)
  _with_version(tmp_path / "new--0", "0.11.0")
  assert replay.recorded_version(tmp_path / "old--0") == "0.10.1"
  r = replay.DriveReplay(lambda *a: None, lambda *a: None, lambda: True, root=tmp_path, version=lambda: "0.11.2")
  ack = r.start("old")
  assert not ack["ok"] and "before StarPilot 7" in ack["error"]
  assert r.start("new")["ok"]
  r.stop()


# ------------------------------------------------------------------------------------------ playing
class Clock:
  """A fake monotonic clock the replay thread's sleep moves forward."""
  def __init__(self):
    self.t = 10_000_000_000
    self.lock = threading.Lock()

  def ns(self):
    with self.lock:
      return self.t

  def sleep(self, s):
    with self.lock:
      self.t += int(s * 1e9)
    time.sleep(0.0005)


class Sink:
  def __init__(self):
    self.events, self.video = [], []
    self.lock = threading.Lock()

  def on_event(self, name, raw, now):
    evt = messaging.log_from_bytes(raw)
    with self.lock:
      self.events.append((name, evt.logMonoTime, evt.carState.vEgo if name == "carState" else None))

  def on_video(self, payload, key):
    with self.lock:
      self.video.append((struct.unpack_from("<IQQIHH", payload), key))

  def cars(self):
    with self.lock:
      return [e for e in self.events if e[0] == "carState"]


def player(tmp_path, parked=lambda: True):
  clock, sink = Clock(), Sink()
  r = replay.DriveReplay(sink.on_event, sink.on_video, parked, root=tmp_path, clock_ns=clock.ns, sleep=clock.sleep)
  return r, clock, sink


def wait(cond, timeout=20.0):
  end = time.monotonic() + timeout
  while time.monotonic() < end:
    if cond():
      return True
    time.sleep(0.005)
  return False


@need_ffmpeg
def test_plays_a_drive_in_order_on_this_devices_clock(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=2.0)
  write_segment(tmp_path / "drv--1", 1, seconds=2.0, t0=T0 + 60_000_000_000)
  r, clock, sink = player(tmp_path)
  start_dev = clock.ns()
  assert r.start("drv")["ok"]
  assert wait(lambda: not r.active)
  assert r.status()["result"] == "end of the drive"
  cars = sink.cars()
  assert len(cars) == 400
  monos = [m for _, m, _ in cars]
  assert monos == sorted(monos) and monos[0] >= start_dev        # the device's clock, not the recording's
  assert all(abs(b - a - 10_000_000) < 20_000_000 for a, b in zip(monos[:199], monos[1:200], strict=True))
  assert [v for *_, v in cars[:3]] == pytest.approx([0.0, 0.01, 0.02])
  assert len(sink.video) == 80 and sink.video[0][1]                # starts on a keyframe
  hdr = sink.video[0][0]
  assert (hdr[4], hdr[5]) == (replay.QCAM_W, replay.QCAM_H) and hdr[1] >= start_dev


def test_seek_pause_speed(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=4.0, video=False)
  r, clock, sink = player(tmp_path)
  assert r.start("drv", at_s=2.0)["ok"]
  assert wait(lambda: len(sink.cars()) > 5)
  assert sink.cars()[0][2] == pytest.approx(1.99)                  # the state just before 2 s first
  assert sink.cars()[1][2] == pytest.approx(2.0)
  r.control("pause")
  assert wait(lambda: r.status().get("paused"))
  n = len(sink.cars())
  assert wait(lambda: len(sink.cars()) >= n + 2)                   # paused: the newest is sent again
  assert {v for *_, v in sink.cars()[n:]} == {sink.cars()[n - 1][2]}
  r.control("resume")
  r.control("speed", 2.0)
  assert wait(lambda: not r.active)
  cars = sink.cars()
  fast = [m for _, m, v in cars if v is not None and v > 3.0]
  assert fast[-1] - fast[0] == pytest.approx(0.99e9 / 2, rel=0.05)   # 1 s of drive in 0.5 s
  r2, _, sink2 = player(tmp_path)
  r2.start("drv")
  assert wait(lambda: len(sink2.cars()) > 3)
  r2.control("seek", 3.5)
  assert wait(lambda: any(v is not None and v >= 3.5 for *_, v in sink2.cars()))
  r2.stop()
  assert not r2.active and r2.status()["result"] == "stopped"


def test_stops_when_the_car_isnt_parked_and_only_starts_parked(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=3.0, video=False)
  parked = {"v": False}
  r, _, sink = player(tmp_path, parked=lambda: parked["v"])
  ack = r.start("drv")
  assert not ack["ok"] and "parked" in ack["error"]
  parked["v"] = True
  assert r.start("drv")["ok"]
  assert wait(lambda: len(sink.cars()) > 10)
  parked["v"] = False
  assert wait(lambda: not r.active)
  assert "isn't parked" in r.status()["result"]
  assert not r.start("../etc")["ok"] and not r.start("nope")["ok"]


def test_start_speed_is_clamped(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=1.0, video=False)
  r, _, _ = player(tmp_path)
  for asked, got in ((float("nan"), 1.0), (100.0, 8.0), (0.0, 0.25), ("x", 1.0)):
    assert r.start("drv", speed=asked)["ok"]
    assert r.status()["speed"] == got
    r.stop()
  assert r.start("drv", at_s=float("nan"))["ok"] and r.status()["t"] == 0.0
  assert not r.control("seek", float("nan"))["ok"] and not r.control("speed", "fast")["ok"]
  r.stop()


def test_a_stop_is_immediate_and_a_slow_old_thread_never_touches_the_next_replay(tmp_path, monkeypatch):
  write_segment(tmp_path / "drv--0", 0, seconds=1.0, video=False)
  real, gate, loading = replay.load_segment, threading.Event(), threading.Event()

  def slow(*a, **k):
    loading.set()
    gate.wait(10)
    return real(*a, **k)
  monkeypatch.setattr(replay, "load_segment", slow)
  r, _, sink = player(tmp_path)
  assert r.start("drv")["ok"]
  assert loading.wait(5)
  r.request_stop("the car isn't parked - replay stopped")         # what the hub's reader does: no waiting
  assert not r.active and r.status()["result"] == "the car isn't parked - replay stopped"
  monkeypatch.setattr(replay, "load_segment", real)
  first = r._thread
  gate.set()
  first.join(5)
  assert sink.events == [] and not r.active                      # the old thread finished its load and sent nothing
  assert r.status()["result"] == "the car isn't parked - replay stopped"


def test_seeking_inside_the_playing_segment_doesnt_read_it_again(tmp_path, monkeypatch):
  write_segment(tmp_path / "drv--0", 0, seconds=4.0, video=False)
  loads = []
  real = replay.load_segment
  monkeypatch.setattr(replay, "load_segment", lambda *a, **k: loads.append(a[1]) or real(*a, **k))
  r, _, sink = player(tmp_path)
  r.start("drv")
  assert wait(lambda: len(sink.cars()) > 3)
  r.control("seek", 3.0)
  assert wait(lambda: any(v is not None and v >= 3.0 for *_, v in sink.cars()))
  r.stop()
  assert loads == [0]


def test_memparams_read_the_replay_not_msgq(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=2.0, video=False)
  r, _, sink = player(tmp_path)
  mp = compat.MemParams()
  mp.source = lambda service: r.latest(service) if r.active else compat.NO_SOURCE
  r.start("drv")
  assert wait(lambda: r.latest("starpilotNavigation") is not None)
  nav = mp.get("NavInstructionState")
  assert nav["maneuverType"] == "off ramp" and nav["maneuverPrimaryText"] == "Exit 19"
  assert mp.get("CEStatus") is None                     # no slcState in this drive: nothing, not the live one
  r.stop()


# ------------------------------------------------------------------------------------------ starviewd
class FakeBlinker:
  def __init__(self):
    self.calls = []

  def set(self, side, why=""):
    self.calls.append((side, why))
    return {"ok": True, "signal": True}


class ImmediateLoop:
  def call_soon_threadsafe(self, fn, *a):
    fn(*a)


class FakeDataClient:
  def __init__(self, rates):
    self.rates = rates
    self.last_sent = {}
    self.sent = 0
    self.frames = []

  def push(self, frame):
    self.frames.append(frame)


def replay_hub(tmp_path, onroad=False, started=False, ignition=None):
  from openpilot.starpilot.system.starview import starviewd
  from openpilot.starpilot.system.starview.tests.test_starviewd_control import FakeSock, make_hub
  hub = make_hub(onroad=onroad, started=started)
  hub.IGN_FRESH_S = 1e9          # no pandad here: the ignition set below stays fresh
  hub._ps_sock = FakeSock()
  hub._ign = (time.monotonic(), onroad if ignition is None else ignition)
  hub._park_check_t = 0.0
  hub._was_replaying = False
  hub._blink_held_t = None
  hub.blinker = FakeBlinker()
  hub.lock = threading.Lock()
  hub.last_raw = {}
  hub.loop = ImmediateLoop()
  hub.data_clients = set()
  hub.video_clients = {c: set() for c in starviewd.VIDEO_CAMS}
  hub.wanted_services = {"carState", "starpilotPlan"}
  hub.replay_translator = compat.Translator(hub.params, toggles=dict)
  hub._replay_routed = None
  hub.engaged = False
  hub.replay = replay.DriveReplay(hub._replay_event, hub._replay_video, hub._parked_for_replay, root=tmp_path,
                                  keep=hub._replay_keep)
  return hub


class FakeVideo:
  def __init__(self):
    self.got = []
    self.need_key = False

  def push(self, payload, key):
    self.got.append((payload, key))


def test_blinker_requests_never_reach_the_relay_box_while_replaying(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=3.0, video=False)
  hub = replay_hub(tmp_path)
  ack = hub.control({"action": "replay_list"})
  assert ack["ok"] and [d["route"] for d in ack["drives"]] == ["drv"]
  assert hub.control({"action": "replay_start", "route": "drv"})["ok"]
  assert hub.blinker.calls == [("off", "")]                  # a live hold is let go first
  ack = hub.control({"action": "blink", "side": "left", "why": "lane"})
  assert ack["ok"] and ack["replay"] and hub.blinker.calls == [("off", "")]
  assert hub.control({"action": "replay_control", "op": "pause"})["ok"]
  assert hub.control({"action": "replay_control", "op": "stop"})["ok"]
  hub.replay_tick(time.monotonic())                             # the reader notices the replay ended
  # the tablet still holds the blinker it asked for on the replayed drive: not passed on until it lets go
  ack = hub.control({"action": "blink", "side": "left", "why": "lane"})
  assert ack["replay"] and not ack["signal"] and hub.blinker.calls == [("off", "")]
  assert hub.control({"action": "blink", "side": "off"}) == {"ok": True, "signal": True}
  assert hub.control({"action": "blink", "side": "left", "why": "lane"}) == {"ok": True, "signal": True}
  assert hub.blinker.calls[-2:] == [("off", ""), ("left", "lane")]


def test_a_live_blinker_is_kept_when_the_replay_cant_start(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=1.0, video=False)
  hub = replay_hub(tmp_path, onroad=True, started=True)        # on, and no live carState: not parked
  ack = hub.control({"action": "replay_start", "route": "drv"})
  assert not ack["ok"] and hub.blinker.calls == []


def test_the_reader_stops_a_replay_once_the_car_isnt_parked(tmp_path, monkeypatch):
  write_segment(tmp_path / "drv--0", 0, seconds=3.0, video=False)
  hub = replay_hub(tmp_path)
  v = FakeVideo()
  hub.video_clients["road"] = {v}
  keys = []
  monkeypatch.setattr(hub, "request_keyframe", lambda: keys.append(1), raising=False)
  assert hub.control({"action": "replay_start", "route": "drv"})["ok"]
  assert v.need_key and keys == [1]                              # the tablet waits for a keyframe of the replay
  v.need_key = False
  hub._ign = (time.monotonic(), True)                            # ignition on, no carState in P
  hub.replay_tick(time.monotonic())
  assert not hub.replay.active and "isn't parked" in hub.replay.status()["result"]
  assert v.need_key and keys == [1, 1]                           # and back to the live video


def test_replayed_data_goes_to_the_tablet_under_its_names(tmp_path):
  hub = replay_hub(tmp_path)
  c = FakeDataClient({"carState": 0})
  hub.data_clients = {c}
  raw = _evt("carState", 42, vEgo=12.5)
  hub._replay_event("carState", raw, time.monotonic())
  assert c.frames == [bytes([8]) + b"carState" + raw]
  hub.wanted_services = {"carState", "selfdriveState"}
  hub._replay_event("selfdriveState", _evt("selfdriveState", 1, enabled=True), time.monotonic())
  assert hub.engaged is False                                 # replayed state never feeds the action guards
  hub._guard("selfdriveState", _evt("selfdriveState", 1, enabled=True), time.monotonic())
  assert hub.engaged is True                                  # the live one does (the reader, replay or not)


def test_parked_means_off_or_in_park_and_standing(tmp_path):
  hub = replay_hub(tmp_path)
  assert hub._parked_for_replay()                             # ignition off
  hub.IGN_FRESH_S = 1.5
  hub._ign = (time.monotonic() - 5, False)
  assert not hub._parked_for_replay()                         # no pandaStates (openpilot stopped): can't tell
  hub._ign = None
  assert not hub._parked_for_replay()
  offroad_on = replay_hub(tmp_path, onroad=False, ignition=True)
  assert not offroad_on._parked_for_replay()                  # offroad isn't parked: the ignition is on
  on = replay_hub(tmp_path, onroad=True, started=True)
  assert not on._parked_for_replay()                          # on, no live carState: can't tell
  def cs(gear, v, age=0.0):
    m = messaging.new_message("carState")
    m.carState.gearShifter, m.carState.vEgo = gear, v
    return time.monotonic() - age, m.to_bytes()
  on.last_raw["carState"] = cs("park", 0.0)
  assert on._parked_for_replay()
  on.last_raw["carState"] = cs("drive", 0.0)
  assert not on._parked_for_replay()
  on.last_raw["carState"] = cs("park", 2.0)
  assert not on._parked_for_replay()
  on.last_raw["carState"] = cs("park", 0.0, age=5)
  assert not on._parked_for_replay()                          # stale


def test_params_push_carries_the_replay_state(tmp_path):
  write_segment(tmp_path / "drv--0", 0, seconds=3.0, video=False)
  hub = replay_hub(tmp_path)
  snap = hub._build_params_snapshot()
  assert snap["r"]["active"] is False and snap["p"]["IsOnroad"] is False
  hub.control({"action": "replay_start", "route": "drv", "at": 1})
  snap = hub._build_params_snapshot()
  assert snap["r"]["active"] and snap["r"]["route"] == "drv" and snap["p"]["IsOnroad"] is True
  hub.replay.stop()


@need_ffmpeg
def test_whole_path_tablet_names_and_video(tmp_path):
  """A drive with a renamed service played through the hub to a tablet that asks for the old names."""
  write_segment(tmp_path / "drv--0", 0, seconds=1.0)
  hub = replay_hub(tmp_path)
  hub.wanted_services = {"carState", "liveCalibration"}
  c = FakeDataClient({"carState": 0, "liveCalibration": 0})
  hub.data_clients = {c}

  v = FakeVideo()
  hub.video_clients["road"] = {v}
  cal = messaging.new_message("extrinsicsCalibration")
  cal.logMonoTime = T0 + 5
  buf = replay.read_log(tmp_path / "drv--0" / "rlog.zst") + cal.to_bytes()
  (tmp_path / "drv--0" / "rlog.zst").write_bytes(zstandard.ZstdCompressor().compress(buf))
  assert hub.control({"action": "replay_start", "route": "drv"})["ok"]
  assert wait(lambda: not hub.replay.active)
  names = [f[1:1 + f[0]].decode() for f in c.frames]
  assert names.count("carState") == 100 and names.count("liveCalibration") == 1
  assert len(v.got) == 20 and v.got[0][1]
