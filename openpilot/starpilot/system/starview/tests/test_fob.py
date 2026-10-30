import json
import threading

import numpy as np
import pytest

from openpilot.starpilot.system.starview import fob, fob_radio as r

FOB = "c8a4ab584"
OTHER = "9d3c4127a"     # (an ID with nine zeros in a row would look like the preamble to a fob it doesn't know)


def _bits(h, n):
  return format(int(h, 16), f"0{n}b")


def frame(rng, fob_id=FOB, inverted=False):
  fid = _bits(fob_id, 36)
  if inverted:
    fid = "".join("1" if c == "0" else "0" for c in fid)
  rolling = "".join(rng.choice(["0", "1"], 190))
  tail = "".join(rng.choice(["0", "1"], 20))
  return "1000000000" + rolling + fid + tail


class Air:
  """rtl_sdr's output as 10 ms blocks: noise, plus the fob's FSK bursts where asked."""
  def __init__(self, seed=1, noise=6.0):
    self.rng = np.random.default_rng(seed)
    self.noise = noise
    self.t = 0

  def _out(self, x):
    raw = np.empty(2 * len(x), np.uint8)
    raw[0::2] = np.clip(x.real + 127.5, 0, 255)
    raw[1::2] = np.clip(x.imag + 127.5, 0, 255)
    b = raw.tobytes()
    return [b[i:i + 2 * r.BLK] for i in range(0, len(b), 2 * r.BLK)]

  def quiet(self, blocks):
    n = blocks * r.BLK
    x = (self.rng.normal(size=n) + 1j * self.rng.normal(size=n)) * self.noise
    self.t += n
    return self._out(x)

  def burst(self, ch, frames, amp=12.0, after=8, spc=r.FS / 2860):
    chips = "".join("10" if c == "1" else "01" for fr in frames for c in fr)
    idx = (np.arange(int(len(chips) * spc)) / spc).astype(int)
    sym = np.where(np.frombuffer(chips.encode(), np.uint8)[idx] == ord("1"), 1.0, -1.0)
    f = r.CHANS[ch] - r.FC + 14.3e3 * sym
    sig = amp * np.exp(1j * (2 * np.pi * np.cumsum(f) / r.FS + 2 * np.pi * (r.CHANS[ch] - r.FC) * self.t / r.FS))
    n = (len(sig) // r.BLK + 1 + after) * r.BLK
    x = (self.rng.normal(size=n) + 1j * self.rng.normal(size=n)) * self.noise
    x[:len(sig)] += sig
    self.t += n
    return self._out(x)


START = r.SETTLE_BLOCKS + 10                         # the tuner settles first


def listen(blocks, ids=(FOB,)):
  out = []
  lis = r.Listener(list(ids), out.append)
  th = threading.Thread(target=lis.work, daemon=True)
  th.start()
  for b in blocks:
    lis.feed(b)
  lis.jobs.put(None)
  th.join(timeout=60)
  return out


def test_radio_hears_presses_on_both_channels_a_hold_and_reads_the_id():
  air = Air()
  rng = np.random.default_rng(7)
  blocks = air.quiet(START)
  press1 = [frame(rng)] * 4
  blocks += air.burst(0, press1)
  blocks += air.quiet(30)
  blocks += air.burst(1, [frame(rng, inverted=True)] * 4, amp=5.0)    # the weaker channel, ID sent inverted
  blocks += air.quiet(30)
  blocks += air.burst(0, [frame(rng)] * 20)                            # held: ~3.6 s
  blocks += air.quiet(20)
  ev = listen(blocks)
  assert ev[0] == {"e": "ready"}
  ends = [e for e in ev if e["e"] == "end"]
  assert [e["b"] for e in ends] == [1, 2, 3]
  assert 650 <= ends[0]["ms"] <= 800 and ends[2]["ms"] > 3000
  assert [e["b"] for e in ev if e["e"] == "hold"] == [3]
  assert sum(e["e"] == "on" and e["b"] == 3 for e in ev) >= 8
  bursts = {e["b"]: e for e in ev if e["e"] == "burst"}
  assert [bursts[b]["ch"] for b in (1, 2, 3)] == [0, 1, 0]
  assert all(bursts[b]["id"] == FOB and bursts[b]["raw_id"] == FOB for b in (1, 2, 3))
  assert format(int(bursts[1]["frame"], 16), "0256b") == press1[0]
  assert bursts[1]["rep"] >= 1 and bursts[1]["early"]          # matched on the first try, 0.25 s in


def test_radio_isnt_fooled_when_the_noise_floor_jumps():
  air = Air(seed=8)
  rng = np.random.default_rng(13)
  fr = frame(rng)
  blocks = air.quiet(START)
  air.noise = 6.0 * 10 ** (8 / 20)                     # +8 dB: interference starts
  blocks += air.quiet(r.MAX_BURST_BLOCKS + 20) + air.burst(0, [fr] * 4, amp=30.0) + air.quiet(20)
  ev = listen(blocks)
  b = [e for e in ev if e["e"] == "burst" and e["id"] == FOB]
  assert len(b) == 1 and format(int(b[0]["frame"], 16), "0256b") == fr


def test_radio_another_fob_isnt_ours_and_noise_is_no_burst():
  air = Air(seed=3)
  rng = np.random.default_rng(9)
  blocks = air.quiet(START) + air.burst(0, [frame(rng, OTHER)] * 4) + air.quiet(20)
  ev = listen(blocks)
  b = [e for e in ev if e["e"] == "burst"]
  assert len(b) == 1 and b[0]["id"] is None and b[0]["raw_id"] == OTHER
  assert [e for e in listen(Air(seed=4).quiet(150)) if e["e"] != "ready"] == []


def test_radio_ignores_blips_and_a_long_one_on_one_channel_never_hides_the_other():
  air = Air(seed=6)
  rng = np.random.default_rng(17)
  fr = frame(rng)
  blocks = air.quiet(START)
  for _ in range(8):                                   # short blips: 10-300 ms of something on 312.1
    blocks += air.burst(0, [frame(rng, OTHER)[:30]], amp=20.0, after=10)
  # a 2 s carrier on 312.1 while the fob presses on 314.35
  junk = air.burst(0, [frame(rng, OTHER)] * 11, amp=20.0, after=0)
  press = air.burst(1, [fr] * 4, amp=12.0, after=0)
  mix = []
  for a, b in zip(junk[:len(press)], press, strict=False):
    x = np.frombuffer(a, np.uint8).astype(np.int16) + np.frombuffer(b, np.uint8).astype(np.int16) - 127
    mix.append(np.clip(x, 0, 255).astype(np.uint8).tobytes())
  blocks += mix + junk[len(press):] + air.quiet(20)
  ev = listen(blocks)
  ours = [e for e in ev if e["e"] == "burst" and e["id"] == FOB]
  assert len(ours) == 1 and format(int(ours[0]["frame"], 16), "0256b") == fr
  assert len([e for e in ev if e["e"] == "end"]) == 2            # the blips never became bursts


def test_radio_ignores_the_tuners_first_second():
  air = Air(seed=12)
  rng = np.random.default_rng(19)
  blocks = air.burst(0, [frame(rng)] * 4, amp=30.0, after=0)[:r.SETTLE_BLOCKS] + air.quiet(200)
  assert [e for e in listen(blocks) if e["e"] != "ready"] == []


def test_radio_skips_decodes_that_waited_too_long(monkeypatch):
  out = []
  lis = r.Listener([FOB], out.append, decode_fn=lambda b, ch, ids: {"rep": 4, "raw_id": FOB, "id": FOB, "m": 1.0, "frame": "0" * 64})
  t = r.time.monotonic()
  lis.jobs.put((1, 0, [], t - r.STALE_S - 1, t - 4, 0.0, False, 9.0))
  lis.jobs.put((2, 1, [], t, t - 0.6, 0.02, False, 17.94))
  lis.jobs.put(None)
  lis.work()
  assert [(e["b"], e.get("stale", False), e["id"]) for e in out] == [(1, True, None), (2, False, FOB)]
  assert out[1]["lag_ms"] == 20 and out[1]["t0"] == t - 0.6 and out[1]["dec_ms"] >= 0


def test_radio_reads_a_weak_press():
  air = Air(seed=5)
  rng = np.random.default_rng(11)
  fr = frame(rng)
  ev = listen(air.quiet(START) + air.burst(1, [fr] * 4, amp=3.5) + air.quiet(10))
  b = [e for e in ev if e["e"] == "burst"]
  assert len(b) == 1 and b[0]["id"] == FOB and format(int(b[0]["frame"], 16), "0256b") == fr


# ---- FobWatch: what a press does ----

class Car:
  def __init__(self, started=True, park=True, after_off=False, doors=None):
    self.started, self.park, self.after = started, park, after_off
    self.doors = doors if doors is not None else {"driver": "unlocked", "passenger": "unlocked"}
    self.door_calls, self.window_calls = [], []
    self.window_ok = True

  def door(self, cmd):
    self.door_calls.append(cmd)
    return {"ok": True, "result": f"{cmd}: confirmed"}

  def window(self, hold):
    self.window_calls.append(hold)
    return {"ok": self.window_ok, "held": hold} if self.window_ok else {"ok": False, "error": "relay box lost"}


class Clock:
  def __init__(self):
    self.t = 1000.0

  def __call__(self):
    return self.t


def make_watch(tmp_path, car, ids=(FOB,), clock=None, **kw):
  fob.save_config({"on": True, "ids": list(ids)}, str(tmp_path / "fob.json"))
  clock = clock or Clock()

  def sleep(s):
    clock.t += s
  w = fob.FobWatch(started=lambda: car.started, after_off=lambda: car.after, door=car.door,
                   lock_state=lambda: {"doors": car.doors}, window=car.window, parked=lambda: car.park,
                   dongle=lambda: True, rtl_sdr=str(tmp_path / "rtl_sdr"), config_path=str(tmp_path / "fob.json"),
                   events_path=str(tmp_path / "fob" / "events.jsonl"), seen_path=str(tmp_path / "seen.json"),
                   clock=clock, wall=lambda: 1.7e9, **{"run_async": lambda fn: fn(), "sleep": sleep, **kw})
  return w


_n = [0]


def code_frame(fob_id=FOB, seed=None):
  _n[0] += 1
  rng = np.random.default_rng(seed if seed is not None else 100 + _n[0])
  return f"{int(frame(rng, fob_id), 2):064x}"


def press(w, b, fob_id=FOB, frame_hex=None, ms=720, held=False, decode_last=False):
  dec = {"e": "burst", "b": b, "ch": b % 2, "rep": 4, "raw_id": fob_id, "id": fob_id if fob_id == FOB else None,
         "m": 1.0, "frame": frame_hex or code_frame(fob_id)}
  evs = []
  if held:
    evs.append({"e": "hold", "b": b})
  if not decode_last:
    evs.insert(0, dec)
  evs.append({"e": "end", "b": b, "ms": ms})
  if decode_last:
    evs.append(dec)
  for e in evs:
    w.handle(e)
  return dec


@pytest.mark.parametrize("doors,cmd", [
  ({"driver": "unlocked", "passenger": "unlocked"}, "lock"),
  ({"driver": "locked", "passenger": "unlocked"}, "unlock"),             # the driver's door decides
  ({"driver": None, "passenger": "locked", "back": None}, "unlock"),
  ({"driver": None, "passenger": "unlocked", "back": "locked"}, "lock"),
  ({}, "lock"),
])
def test_a_press_in_park_flips_the_locks(tmp_path, doors, cmd):
  car = Car(doors=doors)
  w = make_watch(tmp_path, car)
  press(w, 1)
  assert car.door_calls == [cmd]
  last = w.status()["recent"][-1]
  assert last["did"] == ("locked" if cmd == "lock" else "unlocked") and last["ours"] and last["kind"] == "press"
  assert w.history()[0]["did"] == last["did"]


def test_decode_after_the_end_still_acts(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car)
  press(w, 1, decode_last=True)
  assert car.door_calls == ["lock"]


def test_the_same_code_twice_is_ignored_even_after_a_restart(tmp_path):
  car = Car()
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  fr = code_frame()
  press(w, 1, frame_hex=fr)
  press(w, 2, frame_hex=fr)                        # right after: the same press in pieces - quietly
  assert car.door_calls == ["lock"] and len(w.history()) == 1
  clock.t += 11
  press(w, 3, frame_hex=fr)                        # later: played back
  assert car.door_calls == ["lock"]
  assert "replayed" in w.status()["recent"][-1]["why"]
  w2 = make_watch(tmp_path, car)
  press(w2, 1, frame_hex=fr)
  assert car.door_calls == ["lock"]
  press(w2, 2)
  assert car.door_calls == ["lock", "lock"]


def test_a_second_press_while_the_first_is_still_going_is_skipped(tmp_path):
  car = Car()
  pending = []
  clock = Clock()
  w = make_watch(tmp_path, car, run_async=pending.append, clock=clock)
  press(w, 1)
  press(w, 2)
  assert w.history()[0]["why"] == "still doing the last press"
  pending[0]()
  assert car.door_calls == ["lock"]
  clock.t += fob.REPEAT_S + 0.1
  press(w, 3)
  pending[1]()
  assert car.door_calls == ["lock", "unlock"]      # then it alternates


def test_codes_heard_while_switched_off_or_learning_never_work_later(tmp_path):
  car = Car()
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  fr1, fr2 = code_frame(), code_frame()
  w.set_on(False)
  press(w, 1, frame_hex=fr1)
  w.set_on(True)
  w.learn()
  press(w, 2, frame_hex=fr2)
  w.learn_until = 0.0
  clock.t += 11
  press(w, 3, frame_hex=fr1)
  press(w, 4, frame_hex=fr2)
  assert car.door_calls == []
  assert [e["why"] for e in w.history()[:2]] == ["a code it already heard (replayed?)"] * 2


def test_a_bad_event_never_stops_the_listening(tmp_path):
  (tmp_path / "rtl_sdr").write_text("")
  car = Car(started=False, after_off=True)
  got = threading.Event()

  class Scripted(FakeRadio):
    def events(self):
      yield {"e": "ready"}
      yield {"e": "hold", "b": 1}
      yield {"e": "burst", "b": 1, "ch": 0, "rep": 4, "raw_id": FOB, "id": FOB, "m": 1.0, "frame": code_frame()}
      yield {"e": "on", "b": 1, "ms": 2500}          # the relay box raises
      yield {"e": "end", "b": 1, "ms": 3000}
      yield {"e": "ready"}
      got.set()
      self.done.wait(timeout=5)

  def boom(hold):
    raise RuntimeError("relay box exploded")
  w = make_watch(tmp_path, car, radio=Scripted)
  w.window = boom
  w.tick()
  assert got.wait(5)
  with w.lock:
    assert w.radio is not None and w.state == "listening"
  w.close()


def test_someone_elses_fob_does_nothing(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car)
  press(w, 1, fob_id=OTHER)
  assert car.door_calls == [] and w.status()["recent"] == [] and w.status()["others"] == 1


def test_press_while_driving_or_car_off_does_nothing(tmp_path):
  car = Car(park=False)
  w = make_watch(tmp_path, car)
  press(w, 1)
  car.started, car.after, car.park = False, True, True
  press(w, 2)
  assert car.door_calls == [] and car.window_calls == []
  assert [e["why"] for e in w.history()] == ["the car handles the fob itself when it's off", "not in Park"]


def held(w, b, upto_ms, frame_hex=None):
  w.handle({"e": "hold", "b": b})
  w.handle({"e": "burst", "b": b, "ch": 0, "rep": 4, "raw_id": FOB, "id": FOB, "m": 1.0, "frame": frame_hex or code_frame()})
  for ms in range(1250, upto_ms + 1, 250):
    w.handle({"e": "on", "b": b, "ms": ms})


def test_hold_after_off_closes_windows_for_15_s_also_after_letting_go(tmp_path):
  car = Car(started=False, after_off=True)
  clock = Clock()
  loops = []
  w = make_watch(tmp_path, car, clock=clock, run_async=loops.append)
  held(w, 1, 2250)
  assert car.window_calls == []                    # slide doors / panic are held this long too
  w.handle({"e": "on", "b": 1, "ms": 2500})
  assert car.window_calls == [True] and len(loops) == 1
  assert w.history()[0]["did"] == "windows"
  w.handle({"e": "end", "b": 1, "ms": 4700})       # the fob stops sending: the windows keep closing
  assert car.window_calls == [True]
  loops[0]()                                       # the keep-alive thread: every 0.25 s until 15 s are up
  n = len(car.window_calls)
  assert car.window_calls[-1] is False and car.window_calls[1:-1] == [True] * (n - 2)
  assert abs((n - 2) * fob.WINDOW_PULSE_S - fob.WINDOW_RUN_S) <= fob.WINDOW_PULSE_S
  assert w.window_until == 0.0


def test_any_fob_press_stops_the_windows(tmp_path):
  car = Car(started=False, after_off=True)
  loops = []
  w = make_watch(tmp_path, car, run_async=loops.append)
  fr = code_frame()
  held(w, 1, 2500, frame_hex=fr)
  w.handle({"e": "end", "b": 1, "ms": 2900})
  press(w, 2, frame_hex=fr)                        # the hold faded and came back: same code, keeps closing
  w.handle({"e": "end", "b": 3, "ms": 600})        # something else entirely (not decoded as a fob): keeps closing
  w.handle({"e": "burst", "b": 3, "ch": 0, "rep": 2, "raw_id": OTHER, "id": None, "m": 0.5, "frame": code_frame(OTHER)})
  assert car.window_calls == [True] and w.window_until > 0
  press(w, 4)                                      # a new press of your fob stops it
  assert car.window_calls == [True, False] and w.window_until == 0.0
  assert w.history()[0]["did"] == "stopped"
  loops[0]()                                       # the thread sees it stopped and ends
  assert car.window_calls == [True, False]


def test_holding_again_keeps_the_windows_closing(tmp_path):
  car = Car(started=False, after_off=True)
  clock = Clock()
  loops = []
  w = make_watch(tmp_path, car, clock=clock, run_async=loops.append)
  held(w, 1, 2500)
  w.handle({"e": "end", "b": 1, "ms": 4700})
  clock.t += 10
  press(w, 2, held=True, ms=3000)                  # a second hold: 15 s from now, not a stop
  assert car.window_calls == [True] and abs(w.window_until - (clock.t + fob.WINDOW_RUN_S)) < 1e-6
  assert w.history()[0]["why"].startswith("still closing")


def test_a_short_hold_after_off_does_nothing(tmp_path):
  car = Car(started=False, after_off=True)
  w = make_watch(tmp_path, car)
  held(w, 1, 1750)
  w.handle({"e": "end", "b": 1, "ms": 1900})
  assert car.window_calls == [] and "let go before 2.5 s" in w.history()[0]["why"]


def test_windows_stop_when_the_car_starts_or_leaves_park(tmp_path):
  car = Car(started=False, after_off=True)
  loops = []
  w = make_watch(tmp_path, car, run_async=loops.append)
  held(w, 1, 2500)
  assert car.window_calls == [True]
  car.started = True
  w.tick()
  assert car.window_calls == [True, False] and w.window_until == 0.0


def test_openpilot_stopping_while_driving_is_never_car_off(tmp_path):
  car = Car(started=False, after_off=True, park=False)   # card's last word: Drive
  w = make_watch(tmp_path, car)
  assert w.mode() is None
  held(w, 1, 4000)
  assert car.window_calls == []


def test_a_hold_with_the_car_on_is_a_press_and_one_decoded_too_late_after_off_does_nothing(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car)
  press(w, 1, held=True, ms=4000)
  assert car.door_calls == ["lock"]
  car.started, car.after = False, True
  press(w, 2, held=True, ms=1500, decode_last=True)
  assert car.window_calls == []
  assert w.history()[0]["why"] == "let go before it could start"


def test_window_relay_refused_is_logged_and_never_held(tmp_path):
  car = Car(started=False, after_off=True)
  car.window_ok = False
  w = make_watch(tmp_path, car)
  held(w, 1, 2500)
  assert w.window_until == 0.0 and w.history()[0]["why"] == "relay box lost"


def test_in_park_the_press_acts_on_the_decode_and_logs_how_long_it_took(tmp_path):
  car = Car()
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  w.handle({"e": "burst", "b": 1, "ch": 0, "rep": 3, "raw_id": FOB, "id": FOB, "m": 1.0, "frame": code_frame(),
            "t0": clock.t - 1.1, "dec_ms": 480, "lag_ms": 15})
  assert car.door_calls == ["lock"]                # no waiting for the end of the burst
  rec = w.history()[0]
  assert rec["heard_ms"] == 1100 and rec["decode_ms"] == 480 and rec["lag_ms"] == 15 and "door_ms" in rec
  w.handle({"e": "end", "b": 1, "ms": 720})
  assert car.door_calls == ["lock"]


@pytest.mark.parametrize("doors,last,cmd", [
  ({"driver": "locked", "passenger": "unlocked"}, None, "unlock"),        # the driver's door decides
  ({"driver": "unlocked", "passenger": "locked"}, None, "lock"),
  ({"driver": "unlocked"}, ("lock", 5.0), "unlock"),                     # lagging state: the comma's own last wins
  ({"driver": "unlocked"}, ("lock", 11.0), "lock"),                      # ...for 10 s
])
def test_toggle(tmp_path, doors, last, cmd):
  car = Car(doors=doors)
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  if last:
    w.last_cmd = (last[0], clock.t - last[1])
  press(w, 1)
  assert car.door_calls == [cmd]


def test_presses_within_5_s_repeat_and_later_ones_alternate_though_the_lock_state_lags(tmp_path):
  car = Car()
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  press(w, 1)
  clock.t += 2
  press(w, 2)                                      # pressed again because it seemed slow: must not undo it
  clock.t += 4
  press(w, 3)                                      # still within 5 s of the last press
  assert car.door_calls == ["lock"]
  assert w.history()[0]["why"].startswith("already locked")
  clock.t += 6
  press(w, 4)                                      # 6 s later: the other way, though the car still says unlocked
  assert car.door_calls == ["lock", "unlock"]


def test_a_failed_press_can_be_tried_again_at_once(tmp_path):
  car = Car()
  answers = [{"ok": False, "result": "lock: not sent (busy)"}, {"ok": True, "result": "lock: confirmed"}]
  car.door = lambda cmd: car.door_calls.append(cmd) or answers.pop(0)
  clock = Clock()
  w = make_watch(tmp_path, car, clock=clock)
  press(w, 1)
  clock.t += 1
  press(w, 2)
  assert car.door_calls == ["lock", "lock"] and w.history()[0]["did"] == "locked"


def test_the_log_has_the_signal_strength_and_the_frame(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car)
  fr = code_frame()
  w.handle({"e": "burst", "b": 1, "ch": 0, "rep": 2, "raw_id": FOB, "id": FOB, "m": 1.0, "frame": fr, "db": 17.9})
  rec = w.history()[0]
  assert rec["db"] == 17.9 and rec["frame"] == fr


def test_a_refusal_is_tried_once_more(tmp_path):
  car = Car()
  answers = [{"ok": False, "result": "lock: refused by the car (code 7F)"}, {"ok": True, "result": "lock: confirmed"}]
  car.door = lambda cmd: car.door_calls.append(cmd) or answers.pop(0)
  w = make_watch(tmp_path, car)
  press(w, 1)
  assert car.door_calls == ["lock", "lock"] and w.history()[0]["did"] == "locked"


def test_learning_adds_a_fob_pressed_twice(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car, ids=())
  assert w.status()["ids"] == []
  w.learn()
  press(w, 1, fob_id=OTHER)
  assert "press once more" in w.history()[0]["why"]
  press(w, 2, fob_id=OTHER)
  assert w.status()["ids"] == [OTHER] and w.status()["learning"] == 0
  assert fob.load_config(str(tmp_path / "fob.json"))["ids"] == [OTHER]
  assert car.door_calls == []                      # learning never locks anything


def test_forget_and_switch(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car)
  assert w.set_on(False)["on"] is False
  press(w, 1)
  assert car.door_calls == [] and w.history()[0]["why"] == "switched off"
  w.tick()
  assert w.status()["radio"] == "off"              # the switch stops the radio too
  assert w.forget(FOB)["ids"] == []


class FakeRadio:
  made = []

  def __init__(self, ids):
    self.ids = ids
    self.stopped = False
    self.lines = []
    self.done = threading.Event()
    FakeRadio.made.append(self)

  def events(self):
    yield {"e": "ready"}
    self.done.wait(timeout=5)

  def stop(self):
    self.stopped = True
    self.done.set()


def test_radio_runs_only_when_useful(tmp_path):
  FakeRadio.made = []
  (tmp_path / "rtl_sdr").write_text("")
  car = Car(started=True, park=False)
  have = {"dongle": True}
  w = make_watch(tmp_path, car, radio=FakeRadio)
  w.dongle = lambda: have["dongle"]
  w.tick()
  assert FakeRadio.made == [] and w.status()["radio"] == "off"     # driving: off
  car.park = True
  w.tick()
  assert len(FakeRadio.made) == 1 and FakeRadio.made[0].ids == [FOB]
  car.park = False
  w.tick()
  assert FakeRadio.made[0].stopped and w.radio is None
  car.park = True
  car.started, car.after = False, True                             # just turned off (in Park): windows
  w.tick()
  assert len(FakeRadio.made) == 2
  car.after = False                                                # long off
  w.tick()
  assert FakeRadio.made[1].stopped
  car.after = True
  have["dongle"] = False
  w.tick()
  assert w.status()["radio"] == "no dongle" and len(FakeRadio.made) == 2
  w.close()


def test_no_rtl_sdr_or_no_fob_says_why(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car, radio=FakeRadio)
  w.tick()
  assert w.status()["radio"] == "no rtl_sdr"
  w2 = make_watch(tmp_path, car, ids=(), radio=FakeRadio)
  w2.tick()
  assert w2.status()["radio"] == "no fob learned"


def test_radio_restarts_with_the_new_fob_list_and_backs_off_when_it_dies(tmp_path):
  FakeRadio.made = []
  (tmp_path / "rtl_sdr").write_text("")
  car = Car()
  clock = Clock()
  w = make_watch(tmp_path, car, radio=FakeRadio, clock=clock)
  w.tick()
  w.cfg = fob.save_config({"on": True, "ids": [FOB, OTHER]}, w.config_path)
  w.tick()
  assert FakeRadio.made[0].stopped
  w.tick()
  assert FakeRadio.made[-1].ids == [FOB, OTHER]
  # the radio dies on its own
  dead = FakeRadio.made[-1]
  with w.lock:
    w.radio = dead
  dead.done.set()
  for _ in range(100):
    if w.radio is None:
      break
    threading.Event().wait(0.01)
  assert w.radio is None and w.status()["radio"] == "restarting"
  n = len(FakeRadio.made)
  w.tick()
  assert len(FakeRadio.made) == n                  # waits RETRY_S first
  clock.t += fob.RETRY_S[0] + 0.1
  w.tick()
  assert len(FakeRadio.made) == n + 1
  w.close()


def test_events_log_stays_small(tmp_path, monkeypatch):
  monkeypatch.setattr(fob, "EVENTS_MAX", 2000)
  car = Car()
  w = make_watch(tmp_path, car)
  w.set_on(False)
  for b in range(1, 60):
    press(w, b)
  size = (tmp_path / "fob" / "events.jsonl").stat().st_size
  assert size < 2000 + 600
  assert all(json.loads(x) for x in (tmp_path / "fob" / "events.jsonl").read_text().splitlines())


def test_park_reads_card_file_only_when_it_changes(tmp_path):
  p = tmp_path / "dd.json"
  park = fob.Park(str(p))
  assert park() is False
  p.write_text(json.dumps({"park": True}))
  assert park() is True
  p.unlink()
  assert park() is False


def test_dongle_detection(tmp_path):
  d = tmp_path / "1-1"
  d.mkdir()
  (d / "idVendor").write_text("0bda\n")
  (d / "idProduct").write_text("2838\n")
  assert fob.dongle_present(str(tmp_path))
  (d / "idProduct").write_text("8153\n")
  assert not fob.dongle_present(str(tmp_path))


def test_settings_edited_by_hand_are_picked_up(tmp_path):
  car = Car()
  w = make_watch(tmp_path, car, radio=FakeRadio)
  (tmp_path / "fob.json").write_text(json.dumps({"on": False, "ids": [FOB]}))
  import os
  os.utime(tmp_path / "fob.json", ns=(1, 1))
  w.tick()
  assert w.status()["on"] is False


def test_config_cleans_bad_ids(tmp_path):
  p = tmp_path / "f.json"
  p.write_text(json.dumps({"on": False, "ids": [FOB, "zz", FOB.upper(), 5]}))
  assert fob.load_config(str(p)) == {"on": False, "ids": [FOB]}
