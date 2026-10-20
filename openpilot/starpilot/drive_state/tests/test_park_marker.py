from types import SimpleNamespace as NS

from openpilot.starpilot.drive_state import park_marker
from openpilot.starpilot.drive_state.tests.test_evidence import Messages
from openpilot.starpilot.drive_state.evidence import PhysicalSource


def car(**kw):
  return NS(**{"canValid": True, "canTimeout": False, "standstill": True, "gearShifter": "park", **kw})


def test_card_leaves_its_last_parked_state(tmp_path):
  path = str(tmp_path / "park")
  now = [0]
  m = park_marker.ParkMarker(path, clock=lambda: now[0])
  m.update(car(), False)
  assert park_marker.parked_when_card_stopped(path=path)
  for change in ({"gearShifter": "drive"}, {"standstill": False}, {"canValid": False}):
    now[0] += 1
    m.update(car(**change), False)
    assert not park_marker.parked_when_card_stopped(path=path)
  m.update(car(), lambda: True)                     # engaged in Park: not parked for this purpose
  assert not park_marker.parked_when_card_stopped(path=path)
  m.update(car(), lambda: False)
  assert park_marker.parked_when_card_stopped(path=path)
  m.update(None, False)                             # no carState yet: nothing written
  m.update(car(), lambda: 1 / 0)                    # a bad read never escapes into card
  assert not park_marker.parked_when_card_stopped(path=str(tmp_path / "missing"))


def offroad_ignition_on(monkeypatch, tmp_path, parked):
  monkeypatch.setattr(park_marker, "PATH", str(tmp_path / "park"))
  park_marker.write(parked, now_ns=1)
  sm = Messages()
  sm.values["pandaStates"][0].ignitionLine = True
  for key in ("carState", "selfdriveState"):          # card and selfdrived stopped offroad: no fresh messages
    sm.alive[key] = False
  now = [1_000_000_000, 10_000_000_000]
  source = PhysicalSource(sm, mono=lambda: now[0], boot=lambda: sum(now))
  now[0] = 2_100_000_000
  return source, sm


def test_update_allowed_offroad_with_ignition_on_after_park(monkeypatch, tmp_path):
  source, sm = offroad_ignition_on(monkeypatch, tmp_path, True)
  assert source.status(parked_marker=True)["allowed"]
  assert not source.status()["allowed"]                # settings / drive state keep the stock rule
  sm.values["pandaStates"][0].safetyModel = "toyota"   # a panda still able to control the car: no
  assert not source.status(parked_marker=True)["allowed"]
  sm.values["pandaStates"][0].safetyModel = "noOutput"
  sm.values["pandaStates"][0].controlsAllowed = True
  assert not source.status(parked_marker=True)["allowed"]


def test_update_refused_when_card_last_saw_it_moving(monkeypatch, tmp_path):
  source, _ = offroad_ignition_on(monkeypatch, tmp_path, False)
  assert "turn off the vehicle ignition" in source.status(parked_marker=True)["reason"]
