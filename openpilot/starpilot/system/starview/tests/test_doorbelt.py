import json
import os

import pytest
import zstandard as zstd

from openpilot.cereal import log
from openpilot.starpilot.system.starview import doorbelt

WALL0 = 1_790_000_000.0       # some time in 2026


@pytest.fixture
def files(tmp_path, monkeypatch):
  d = tmp_path / "doorbelt"
  monkeypatch.setattr(doorbelt, "DIR", str(d))
  monkeypatch.setattr(doorbelt, "MAP", str(d / "bits.json"))
  monkeypatch.setattr(doorbelt, "EVENTS", str(d / "events.jsonl"))
  monkeypatch.setattr(doorbelt, "SCAN_LOCK", str(d / "scan.lock"))
  monkeypatch.setattr(doorbelt, "SCANNED", str(d / "scanned.json"))
  monkeypatch.setattr(doorbelt, "PROGRESS", str(tmp_path / "progress.json"))
  monkeypatch.setattr(doorbelt, "ROOT", str(tmp_path / "realdata"))
  os.makedirs(tmp_path / "realdata")
  return tmp_path


def body(door=0, slide_r=0, belt_unlatched=1):
  """BODY_CONTROL_STATE (0x620) with the driver's door, the right sliding door and the driver's belt."""
  b = bytearray(8)
  b[5] = (door << 5) | (slide_r << 3)
  b[7] = belt_unlatched << 6
  return bytes(b)


# ------------------------------------------------------------------------------------------ the map
def test_standard_bits_until_learned(files):
  bits = doorbelt.bit_map()
  assert bits["slide_right"] | {} == {"bus": 0, "addr": 0x620, "byte": 5, "bit": 3, "active": 1, "source": "standard"}
  assert doorbelt.value(body(slide_r=1), bits["slide_right"]) == 1
  assert doorbelt.value(body(belt_unlatched=0), bits["belt_driver"]) == 0
  assert doorbelt.state_word("belt_driver", 0, bits) == "buckled"
  assert doorbelt.state_word("slide_right", 1, bits) == "open"
  assert "belt_2r" not in bits
  doorbelt._write_json(doorbelt.MAP, {"items": {"belt_2r": {"bus": 0, "addr": 0x3B1, "byte": 2, "bit": 0, "active": 1}}})
  assert doorbelt.bit_map()["belt_2r"]["source"] == "learned"


# ------------------------------------------------------------------------------------------ Learn
class Clock:
  def __init__(self):
    self.t = 100.0

  def __call__(self):
    return self.t


def learner(monkeypatch):
  clock = Clock()
  w = doorbelt.CanWatch(ok=lambda: None, clock=clock)
  monkeypatch.setattr(w, "_ensure", lambda: setattr(w, "asked", clock()))   # no socket thread in the test
  return w, clock


def feed_for(w, clock, seconds, frames):
  """frames(t) -> [(bus, addr, data)] fed at 100 Hz for `seconds`."""
  end = clock.t + seconds
  while clock.t < end:
    for bus, addr, dat in frames(clock.t):
      w.feed(clock.t, bus, addr, dat)
    clock.t += 0.01


def test_learn_finds_each_switch_and_drops_counters_and_shared_bits(files, monkeypatch):
  w, clock = learner(monkeypatch)
  st = {"slide_r": 0, "door": 0, "dome": 0, "belt2r": 0, "n": 0}

  def frames(t):
    st["n"] += 1
    return [(0, 0x620, body(door=st["door"], slide_r=st["slide_r"])),
            (0, 0x100, bytes([st["n"] & 0xFF, 0, 0, 0])),                      # a counter: noisy
            (0, 0x500, bytes([st["dome"], 0])),                                  # dome light: on with any door
            (1, 0x3B1, bytes([0, 0, st["belt2r"], 0]))]

  def work(key, dome=False, times=4):
    for _ in range(times):
      st[key] ^= 1
      if dome:
        st["dome"] ^= 1
      feed_for(w, clock, 1.5, frames)

  assert w.begin()["ok"]
  feed_for(w, clock, 5, frames)
  # right sliding door
  w.start("slide_right")
  work("slide_r", dome=True)
  r = w.done("slide_right")
  assert r["found"]["addr"] in (0x620, 0x500)       # alone, the dome light looks as good
  feed_for(w, clock, 3, frames)
  st["slide_r"] ^= 1                                   # walked through it between steps: open...
  feed_for(w, clock, 3, frames)
  st["slide_r"] ^= 1                                   # ...and closed
  feed_for(w, clock, 3, frames)
  # driver's door (dome light moves again: it's not either door)
  w.start("door_driver")
  work("door", dome=True)
  assert w.done("door_driver")["found"]["addr"] == 0x620
  # 2nd row right belt, on bus 1
  w.start("belt_2r")
  work("belt2r")
  f = w.done("belt_2r")["found"]
  assert (f["bus"], f["addr"], f["byte"], f["bit"], f["active"]) == (1, 0x3B1, 2, 0, 1)
  # 3rd row middle: nothing moves
  w.start("belt_3c")
  feed_for(w, clock, 6, frames)
  assert w.done("belt_3c")["found"] is None
  r = w.save()
  assert r["ok"] and r["missing"] == ["belt_3c"]
  bits = doorbelt.bit_map()
  assert bits["slide_right"] | {} == {"bus": 0, "addr": 0x620, "byte": 5, "bit": 3, "active": 1, "source": "learned"}
  assert bits["door_driver"]["bit"] == 5 and bits["belt_2r"]["addr"] == 0x3B1
  assert (0, 0x100, 0, 0) not in w.changes                  # the counter was dropped as it ran
  st_items = {i["id"]: i["source"] for i in doorbelt.status()["items"]}
  assert st_items["belt_3c"] == "not on bus" and st_items["belt_2r"] == "learned" and st_items["hatch"] is None


def test_learn_needs_the_car_on_in_park(files, monkeypatch):
  w = doorbelt.CanWatch(ok=lambda: "Turn the car on and put it in Park.")
  assert w.begin() == {"ok": False, "error": "Turn the car on and put it in Park."}
  assert w.live()["ok"] is False
  assert w.start("belt_2r")["ok"] is False


def test_live_reads_only_the_mapped_messages(files, monkeypatch):
  w, clock = learner(monkeypatch)
  r = w.live()
  assert r["ok"] and r["values"]["slide_right"] is None
  w.feed(clock(), 0, 0x620, body(slide_r=1, belt_unlatched=0))
  w.feed(clock(), 0, 0x123, b"\x01")
  assert (0, 0x123) not in w.last
  r = w.live()
  assert r["words"]["slide_right"] == "open" and r["words"]["belt_driver"] == "buckled" and r["words"]["door_driver"] == "closed"


# ------------------------------------------------------------------------------------------ after the drive
def write_rlog(path, frames, mono0=10_000_000_000, wall=True, extra=None):
  """frames: [(seconds from start, data of 0x620, speed m/s)] -> rlog.zst with initData, carState and can."""
  msgs = []
  if wall:
    ev = log.Event.new_message(logMonoTime=mono0)
    ev.init("initData").wallTimeNanos = int(WALL0 * 1e9)
    msgs.append(ev.to_bytes())
  for s, dat, v in frames:
    mono = mono0 + int(s * 1e9)
    cs = log.Event.new_message(logMonoTime=mono)
    cs.init("carState").vEgo = v
    msgs.append(cs.to_bytes())
    ev = log.Event.new_message(logMonoTime=mono)
    can = ev.init("can", 3 if extra is None else 3 + extra)
    can[0].address, can[0].src, can[0].dat = 0x620, 0, dat
    can[1].address, can[1].src, can[1].dat = 0x620, 128, body()          # the comma's own: ignored by bus number
    can[2].address, can[2].src, can[2].dat = 0x2C1, 0, b"\x01\x02"
    for i in range(extra or 0):
      can[3 + i].address, can[3 + i].src, can[3 + i].dat = 0x400 + i % 50, 1, bytes(64)
    msgs.append(ev.to_bytes())
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "wb") as f:
    f.write(zstd.compress(b"".join(msgs)))


def seg(files, route, n):
  return str(files / "realdata" / f"{route}--{n}" / "rlog.zst")


def test_messages_are_streamed_whole_even_when_big(files):
  p = seg(files, "0000001a--abcdef0123", 0)
  write_rlog(p, [(i * 0.01, body(), 0.0) for i in range(300)], extra=3000)   # big can lists: multi-segment messages
  msgs = list(doorbelt._messages(p))
  assert len(msgs) == 1 + 2 * 300
  assert max(int.from_bytes(m[:4], "little") for m in msgs) >= 1      # some came in more than one capnp segment
  with open(p, "rb") as f:                            # cut short: stops cleanly at the last whole message
    data = zstd.decompress(f.read())
  with open(p, "wb") as f:
    f.write(zstd.compress(data[:len(data) - 100]))
  assert sum(1 for _ in doorbelt._messages(p)) == 600


def test_scan_finds_flickers_across_segments_and_each_drive_once(files):
  route = "0000001a--abcdef0123"
  # segment 0: parked, right sliding door opens and closes slowly; then driving at 40 mph
  f0 = [(0.0, body(), 0.0), (5.0, body(slide_r=1), 0.0), (20.0, body(), 0.0), (30.0, body(), 18.0), (59.9, body(), 18.0)]
  # segment 1: driving, the driver's belt buckled at the start, then the sliding door flickers twice, 1 s apart
  f1 = [(60.0, body(belt_unlatched=0), 18.0), (70.0, body(slide_r=1, belt_unlatched=0), 18.0),
        (71.0, body(belt_unlatched=0), 18.0), (90.0, body(belt_unlatched=0), 18.0)]
  write_rlog(seg(files, route, 0), f0)
  write_rlog(seg(files, route, 1), f1, wall=False)    # no clock in this one: carried from the file time
  now = os.path.getmtime(seg(files, route, 1)) + 600
  assert doorbelt.pending(now) == 2
  r = doorbelt.scan(now=now, progress=False)
  assert r == {"segments": 2, "events": 5, "stopped": False, "left": 0}
  evs = [json.loads(ln) for ln in open(doorbelt.EVENTS)]
  assert [(e["item"], e["on"], e["fast"], e["moving"]) for e in evs] == [
    ("slide_right", True, False, False), ("slide_right", False, False, False),
    ("belt_driver", True, False, True),                               # the belt change at the segment boundary is seen
    ("slide_right", True, False, True), ("slide_right", False, True, True)]
  assert evs[0]["t"] == WALL0 + 5.0 and evs[0]["route"] == route and evs[3]["mph"] == 40
  d = doorbelt.history()["drives"][0]
  assert d["segs"] == 2 and d["changes"] == {"slide_right": 4, "belt_driver": 1} and d["fast"] == {"slide_right": 1}
  assert doorbelt.pending(now) == 0
  assert doorbelt.scan(now=now, progress=False)["segments"] == 0          # each segment read once


def test_scan_skips_the_segment_being_written_and_old_drives(files):
  route = "0000001b--abcdef0123"
  write_rlog(seg(files, route, 0), [(0.0, body(), 0.0)])
  open(os.path.join(os.path.dirname(seg(files, route, 0)), "rlog.lock"), "w").close()
  now = os.path.getmtime(seg(files, route, 0)) + 10
  assert doorbelt.pending(now) == 0
  assert doorbelt.pending(now + doorbelt.LOCK_STALE_S) == 1           # a lock left by a crash
  assert doorbelt.pending(now + doorbelt.BACKLOG_S + 1) == 0          # older than a week: left alone


def test_scan_stops_when_the_car_turns_on(files):
  for n in range(3):
    write_rlog(seg(files, "0000001c--abcdef0123", n), [(n * 60.0, body(), 0.0)])
  now = os.path.getmtime(seg(files, "0000001c--abcdef0123", 2)) + 60
  calls = {"n": 0}

  def stop():
    calls["n"] += 1
    return calls["n"] > 2
  r = doorbelt.scan(should_stop=stop, now=now, progress=False)
  assert r["stopped"] and r["segments"] == 2 and r["left"] == 1
  assert doorbelt.scan(now=now, progress=False)["segments"] == 1       # the rest the next time it's parked


def test_a_new_learn_starts_the_history_over(files):
  write_rlog(seg(files, "0000001d--abcdef0123", 0), [(0.0, body(), 0.0), (5.0, body(slide_r=1), 0.0)])
  now = os.path.getmtime(seg(files, "0000001d--abcdef0123", 0)) + 60
  doorbelt.scan(now=now, progress=False)
  assert len(doorbelt.history()["events"]) == 1
  doorbelt._write_json(doorbelt.MAP, {"items": {"slide_right": {"bus": 0, "addr": 0x620, "byte": 5, "bit": 2, "active": 1}}})
  assert doorbelt.pending(now) == 1
  doorbelt.scan(now=now, progress=False)
  assert doorbelt.history()["events"] == []                           # bit 2 never moved in that drive


def test_a_scan_stopped_inside_a_segment_reads_it_again_from_the_last_whole_one(files):
  route = "0000001e--abcdef0123"
  write_rlog(seg(files, route, 0), [(0.0, body(), 0.0), (59.0, body(), 0.0)])
  # 10100 frames (20000+ messages): the stop check inside the segment fires after the door opened
  write_rlog(seg(files, route, 1), [(60 + k * 0.001, body(slide_r=int(k >= 5000)), 0.0) for k in range(10100)])
  now = os.path.getmtime(seg(files, route, 1)) + 60
  calls = {"n": 0}

  def stop():
    calls["n"] += 1
    return calls["n"] > 2          # 1 check before each segment, the 3rd inside segment 1
  r = doorbelt.scan(should_stop=stop, now=now, progress=False)
  assert r["stopped"] and r["segments"] == 1
  assert doorbelt.scan(now=now, progress=False)["segments"] == 1
  evs = doorbelt.history()["events"]
  assert [(e["item"], e["on"]) for e in evs] == [("slide_right", True)]      # no made-up "closed" first


def test_a_scan_killed_after_writing_events_never_writes_them_twice(files, monkeypatch):
  route = "0000001f--abcdef0123"
  for n in range(3):
    write_rlog(seg(files, route, n), [(n * 60.0, body(), 0.0), (n * 60.0 + 10, body(slide_r=1), 0.0), (n * 60.0 + 20, body(), 0.0)])
  now = os.path.getmtime(seg(files, route, 2)) + 60
  real = doorbelt._save_state
  calls = {"n": 0}

  def killed(st):
    calls["n"] += 1
    if calls["n"] == 2:            # segment 1's events are written, its state never saved
      raise KeyboardInterrupt
    real(st)
  monkeypatch.setattr(doorbelt, "_save_state", killed)
  with pytest.raises(KeyboardInterrupt):
    doorbelt.scan(now=now, progress=False)
  monkeypatch.setattr(doorbelt, "_save_state", real)
  assert doorbelt.scan(now=now, progress=False)["segments"] == 2
  assert len(doorbelt.history()["events"]) == 6           # 2 per segment, once each
  assert doorbelt.history()["drives"][0]["segs"] == 3


def test_only_one_scan_at_a_time(files):
  import fcntl
  os.makedirs(doorbelt.DIR, exist_ok=True)
  with open(doorbelt.SCAN_LOCK, "w") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    assert doorbelt.scan(progress=False) == {"busy": True}


def test_learn_again_and_walking_through_doors_between_steps(files, monkeypatch):
  w, clock = learner(monkeypatch)
  st = {"hatch": 0, "belt": 0}

  def frames(t):
    return [(0, 0x620, bytes(8)), (0, 0x6A0, bytes([st["hatch"], 0])), (0, 0x3B2, bytes([0, st["belt"]]))]

  def flip(key, n):
    for _ in range(n):
      st[key] ^= 1
      feed_for(w, clock, 1.5, frames)

  w.begin()
  feed_for(w, clock, 6, frames)
  w.start("hatch")
  flip("hatch", 4)
  assert w.done("hatch")["found"]["addr"] == 0x6A0
  flip("hatch", 4)                  # out and back in through the hatch twice to reach the 3rd row
  w.start("belt_3r")
  flip("belt", 3)                   # a miscount...
  w.done("belt_3r")
  w.start("belt_3r")                # ..."Again"
  flip("belt", 4)
  assert w.done("belt_3r")["found"]["addr"] == 0x3B2
  r = w.save()
  assert r["missing"] == [] and r["found"]["hatch"]["addr"] == 0x6A0 and r["found"]["belt_3r"]["addr"] == 0x3B2


def test_a_dead_reader_is_started_again(files, monkeypatch):
  class Dead:
    def is_alive(self):
      return False
  started = []
  monkeypatch.setattr(doorbelt.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: started.append(1), "is_alive": lambda self: True})())
  w = doorbelt.CanWatch(ok=lambda: None)
  w.thread = Dead()
  assert w.begin()["ok"] and started == [1]
