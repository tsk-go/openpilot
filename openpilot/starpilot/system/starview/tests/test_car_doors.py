"""card's side of StarView's doors (starview/car_doors.py): requests in, results and lock state out, the module's replies
handed over only while asked for, the driver's door for auto-lock."""
import ast
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from opendbc.car import structs
from openpilot.starpilot.system.starview import car_doors

Gear = structs.CarState.GearShifter
OPENPILOT = Path(__file__).resolve().parents[4]


class FakeLocks:
  def __init__(self):
    self.sequence = self.manual = None
    self.manual_result = ""
    self.read_locks = True
    self.locks = {"driver": None}
    self.locks_version = 0
    self.listening = False
    self.replies = []

  def response(self, dat):
    self.replies.append(dat)


@pytest.fixture
def files(tmp_path, monkeypatch):
  for name in ("DOOR_REQUEST", "DOOR_RESULT", "DRIVER_DOOR", "LOCKS"):
    monkeypatch.setattr(car_doors, name, str(tmp_path / name.lower()))
  return tmp_path


def make_car(locks=None, driver_open=False):
  return NS(CI=NS(CC=NS(door_locks=locks) if locks is not None else NS(), CS=NS(driver_door_open=driver_open)))


def state(door_open=False, gear=Gear.park):
  return NS(doorOpen=door_open, gearShifter=gear)


def tick(car, n=1, cs=None, can=()):
  for _ in range(n):
    car_doors.update(car, cs or state(), list(can))


def test_replies_only_while_listening(files):
  locks = FakeLocks()
  car = make_car(locks)
  can = [(0, [(0x758, b"\x40\x03\x62", 0), (0x758, b"\x40\x03\x62", 1), (0x750, b"x", 0)])]
  tick(car, can=can)
  assert locks.replies == []
  locks.listening = True
  tick(car, can=can)
  assert locks.replies == [b"\x40\x03\x62"]            # the body module's replies on bus 0 only


def test_request_is_handed_over_once(files):
  locks = FakeLocks()
  car = make_car(locks)
  (files / "door_request").write_text("unlock horn 2x8x17")
  tick(car, 25)                                          # checked 4x a second while idle
  assert locks.manual == "unlock horn 2x8x17"
  assert not (files / "door_request").exists()


@pytest.mark.parametrize("text,age", [("open sesame", 0), ("lock", 6), ("lock " + "x" * 40, 0)])
def test_bad_or_old_requests_are_dropped(files, text, age):
  locks = FakeLocks()
  car = make_car(locks)
  (files / "door_request").write_text(text)
  then = time.time() - age  # noqa: TID251
  os.utime(files / "door_request", (then, then))
  tick(car, 25)
  assert locks.manual is None and not (files / "door_request").exists()


def test_result_and_lock_state_go_to_the_tablet(files):
  locks = FakeLocks()
  car = make_car(locks)
  tick(car, 25)
  assert json.loads((files / "locks").read_text())["doors"] == {"driver": None}   # written at start: nothing known yet
  locks.locks, locks.locks_version = {"driver": "locked"}, 1
  locks.manual_result = "lock: confirmed"
  tick(car, 5)                                           # 20x a second while there is something to say
  assert json.loads((files / "door_result").read_text())["result"] == "lock: confirmed"
  assert locks.manual_result == ""
  assert json.loads((files / "locks").read_text())["doors"] == {"driver": "locked"}


def test_no_door_locks_no_files(files):
  car = make_car(None)
  tick(car, 50)
  assert sorted(p.name for p in files.iterdir()) == ["driver_door"]   # the driver's door is the car state's own


def test_driver_door_written_on_changes_only(files):
  car = make_car(FakeLocks(), driver_open=True)
  tick(car, 3, cs=state(door_open=True))
  first = json.loads((files / "driver_door").read_text())
  assert first == {"n": 1, "driver": "open", "any_open": True, "park": True, "closes": 0}
  car.CI.CS.driver_door_open = False
  tick(car, 3)
  assert json.loads((files / "driver_door").read_text()) == {"n": 2, "driver": "shut", "any_open": False, "park": True,
                                                             "closes": 1}
  tick(car, 3, cs=state(gear=Gear.drive))
  assert json.loads((files / "driver_door").read_text())["n"] == 3


def test_card_calls_the_hook_right_after_the_car_update():
  tree = ast.parse((OPENPILOT / "selfdrive/car/card.py").read_text())
  fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "state_update")
  body = [ast.unparse(n) for n in fn.body]
  at = body.index("CS = self.CI.update(can_list)")
  assert body[at + 1] == "car_doors.update(self, CS, can_list)"
