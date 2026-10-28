import json
import os

import pytest

from openpilot.starpilot.system.starview import autolock
from openpilot.starpilot.system.starview.autolock import AutoLock, PhoneSignal


class Rig:
  """An AutoLock with a fake clock, a fake phone signal and a recording door."""
  def __init__(self, tmp_path, **cfg):
    self.cfg_path, self.state_path = str(tmp_path / "autolock.json"), str(tmp_path / "door")
    self.t = 100.0
    self.dbm = -45
    self.calls = []
    self.answer = {"ok": True, "result": "lock: confirmed"}
    self.n = self.closes = 0
    self.driver = "shut"
    autolock.save_config({"lock": True, **cfg}, self.cfg_path)
    self.auto = AutoLock(self.door, lambda: self.dbm, self.cfg_path, self.state_path, clock=lambda: self.t)
    self.write(driver="shut")
    self.tick()

  def door(self, cmd, sound, beeps):
    self.calls.append((cmd, sound, beeps))
    return {**self.answer, "result": f"{cmd}: confirmed"}

  def write(self, driver=None, any_open=None, park=True):
    if driver == "shut" and self.driver == "open":
      self.closes += 1
    self.driver = driver or self.driver
    self.n += 1
    with open(self.state_path, "w") as f:
      json.dump({"n": self.n, "driver": self.driver, "any_open": self.driver == "open" if any_open is None else any_open,
                 "park": park, "closes": self.closes}, f)
    os.utime(self.state_path, ns=(self.n * 10**9, self.n * 10**9))

  def tick(self, dt=0.5, started=True):
    self.t += dt
    return self.auto.tick(started)

  def get_out(self):
    self.write(driver="open")
    self.tick()
    self.write(driver="shut")
    self.tick()


def test_locks_on_the_first_reading_outside(tmp_path):
  r = Rig(tmp_path, lock_beeps=[1, 30, 50])
  r.get_out()
  assert r.auto.phase == "armed" and r.calls == []
  r.dbm = -50                       # still above the line (-52): nothing
  r.tick()
  assert r.calls == []
  r.dbm = -58
  r.tick()
  assert r.calls == [("lock", "horn", [1, 30, 50])]
  assert r.auto.phase == "idle"


def test_phone_dropping_off_counts_as_walking_away(tmp_path):
  r = Rig(tmp_path)
  r.get_out()
  r.dbm = None
  r.tick()
  assert [c[0] for c in r.calls] == ["lock"]


def test_no_phone_at_the_door_never_arms(tmp_path):
  r = Rig(tmp_path)
  r.dbm = None                      # phone dead / left at home: never lock anyone out
  r.get_out()
  assert r.auto.phase == "idle"
  for _ in range(10):
    r.tick()
  assert r.calls == []


def test_a_door_opening_or_leaving_park_disarms(tmp_path):
  r = Rig(tmp_path)
  r.get_out()
  r.write(any_open=True)            # a sliding door / passenger
  r.tick()
  r.dbm = -80
  r.tick()
  assert r.calls == [] and r.auto.phase == "idle"
  r.write(any_open=False)
  r.dbm = -45
  r.get_out()
  r.write(park=False)
  r.tick()
  assert r.calls == []


def test_only_the_drivers_door_arms_and_only_when_switched_on(tmp_path):
  r = Rig(tmp_path)
  r.write(any_open=True)            # another door opens and closes, driver's stays shut
  r.tick()
  r.write(any_open=False)
  r.tick()
  assert r.auto.phase == "idle"
  autolock.save_config({"lock": False}, r.cfg_path)
  os.utime(r.cfg_path, ns=(1, 1))
  r.get_out()
  assert r.auto.phase == "idle"


def test_gives_up_after_a_minute(tmp_path):
  r = Rig(tmp_path)
  r.get_out()
  r.tick(dt=61)
  r.dbm = -90
  r.tick()
  assert r.calls == [] and r.auto.phase == "idle"


def test_auto_unlock_needs_walking_away_then_coming_back(tmp_path):
  r = Rig(tmp_path, unlock=True, unlock_beeps=[2, 80, 170])
  r.get_out()
  r.dbm = -60
  r.tick()
  assert r.auto.phase == "away"
  r.dbm = -55                       # still standing by the car: no unlock
  r.tick()
  assert [c[0] for c in r.calls] == ["lock"]
  r.dbm = None                      # walked off (out of range)
  r.tick()
  assert r.auto.phase == "returning"
  r.dbm = -70                       # on the way back
  r.tick()
  assert len(r.calls) == 1
  r.dbm = -58
  r.tick()
  assert r.calls[-1] == ("unlock", "horn", [2, 80, 170]) and r.auto.phase == "idle"


def test_auto_unlock_time_limit(tmp_path):
  r = Rig(tmp_path, unlock=True, unlock_min=1)
  r.get_out()
  r.dbm = -90
  r.tick()
  r.tick()
  assert r.auto.phase == "returning"
  r.tick(dt=61)
  r.dbm = -40
  r.tick()
  assert [c[0] for c in r.calls] == ["lock"]


def test_openpilot_off_does_nothing(tmp_path):
  r = Rig(tmp_path)
  r.get_out()
  assert r.tick(started=False) == autolock.OFF_S and r.auto.phase == "idle"


@pytest.mark.parametrize("bad", [{"lock_dbm": -10}, {"unlock_min": 0}, {"lock": "yes"}, {"away_dbm": -60, "unlock_dbm": -70},
                                 {"lock_beeps": [1, 2]}, {"what": 1}, {"sound": "siren"}])
def test_settings_are_checked(tmp_path, bad):
  with pytest.raises(ValueError):
    autolock.save_config(bad, str(tmp_path / "a.json"))


def test_bad_settings_file_falls_back_to_off(tmp_path):
  p = tmp_path / "a.json"
  p.write_text("{nope")
  assert autolock.load_config(str(p)) == autolock.DEFAULTS


def test_phone_signal_reads_btmgmt():
  calls = []
  out = {"con": "Connections:\n\t5A:11:22:33:44:55 type LE Random\n",
         "conn-info": "Connection Information for 5A:11:22:33:44:55 (LE Random)\n\tRSSI -57\tTX power 9\tmax TX power 9\n"}

  class R:
    def __init__(self, stdout):
      self.stdout = stdout

  def run(args, **kw):
    calls.append(args[3:])
    return R(out.get(args[3], ""))
  sig = PhoneSignal(run)
  assert sig.read() == -57
  assert calls == [["con"], ["conn-info", "-t", "2", "5A:11:22:33:44:55"]]
  assert sig.read() == -57 and len(calls) == 3            # the phone's address is remembered
  out["con"] = "Connections:\n"
  out["conn-info"] = "Unable to get conn info: Not Connected\n"
  assert sig.read() is None
