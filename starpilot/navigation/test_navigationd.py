import json
import pytest

from openpilot.starpilot.navigation import navigationd as navigationd_module
from openpilot.starpilot.navigation.navigationd import Navigationd, location_age_ok


class CountingParams:
  def __init__(self):
    self.use_vienna_reads = 0

  def get(self, key: str, *, encoding: str):
    assert key == "NavDestination"
    return None

  def get_bool(self, key: str) -> bool:
    assert key == "UseVienna"
    self.use_vienna_reads += 1
    return True


class CountingRoute:
  def __init__(self):
    self.payload_builds = 0

  def build_instruction_payload(self, progress, *, use_vienna_sign: bool):
    assert progress == "progress"
    assert use_vienna_sign
    self.payload_builds += 1
    return {"payload": self.payload_builds}


class StopLoop(Exception):
  pass


class Recorder:
  def __init__(self, return_value=None):
    self.calls = []
    self.return_value = return_value

  def __call__(self, *args):
    self.calls.append(args)
    return self.return_value


class Ratekeeper:
  def keep_time(self):
    raise StopLoop


def test_run_builds_one_payload_for_both_navigation_publishers():
  navigationd = Navigationd.__new__(Navigationd)
  route = CountingRoute()
  params = CountingParams()
  navigationd.params = params
  navigationd.rk = Ratekeeper()
  navigationd._update_location = Recorder((True, 0.0))
  navigationd._maybe_update_route = Recorder((route, None, 0))
  navigationd._build_progress = Recorder(("progress", None))
  navigationd._maybe_recompute = Recorder()
  navigationd._snapshot_route = Recorder((route, None, 0))
  navigationd._publish_nav_instruction = Recorder()
  navigationd._publish_nav_state = Recorder()
  navigationd._publish_nav_route_if_needed = Recorder()

  with pytest.raises(StopLoop):
    navigationd.run()

  assert route.payload_builds == 1
  assert params.use_vienna_reads == 1
  instruction_payload = navigationd._publish_nav_instruction.calls[0][3]
  state_payload = navigationd._publish_nav_state.calls[0][3]
  assert instruction_payload is state_payload


def test_navigation_state_timestamp_refreshes_even_when_instruction_is_unchanged():
  navigationd = Navigationd.__new__(Navigationd)
  navigationd._last_nav_state = None
  navigationd.params_memory = type("Memory", (), {})()
  navigationd.params_memory.put_nonblocking = Recorder()
  navigationd.params_memory.remove = Recorder()
  payload = {"maneuverType": "turn", "maneuverModifier": "right", "maneuverDistance": 55.0}

  navigationd._publish_nav_state(object(), object(), True, payload)
  navigationd._publish_nav_state(object(), object(), True, payload)

  states = [args[1] for args in navigationd.params_memory.put_nonblocking.calls]
  assert len(states) == 2
  assert all(state["valid"] and state["updatedAtMonotonic"] > 0 for state in states)
  assert states[0]["updatedAtMonotonic"] < states[1]["updatedAtMonotonic"]


def test_location_age_ok_while_stopped():
  # moving or speed unknown: at most 2.5 s
  assert location_age_ok(2.0, 12.0, None)
  assert not location_age_ok(3.0, 12.0, 12.0)
  assert not location_age_ok(3.0, 0.0, None)
  # stopped at the fix and still stopped: the position stays good for 30 s
  assert location_age_ok(20.0, 0.1, 0.0)
  assert not location_age_ok(31.0, 0.1, 0.0)
  # stopped at the fix but rolling now, or moving at the fix: no
  assert not location_age_ok(5.0, 0.1, 2.0)
  assert not location_age_ok(5.0, 3.0, 0.0)


class _MemParams:
  def __init__(self, value):
    self.value = value

  def get(self, key, encoding=None):
    assert key == "LastGPSPosition"
    return self.value


def test_update_location_keeps_an_old_position_while_stopped(monkeypatch):
  monkeypatch.setattr(navigationd_module, "monotonic", lambda: 100.0)
  nd = Navigationd.__new__(Navigationd)
  nd._last_position = None
  nd._last_bearing = None
  nd._fix_age = 0.0
  gps = {"latitude": 40.63, "longitude": -73.99, "bearing": 90.0, "speed": 0.0, "hasFix": True, "updatedAtMonotonic": 90.0}
  nd.params_memory = _MemParams(json.dumps(gps))
  nd._wheel_speed = lambda: 0.0
  assert nd._update_location() == (True, 0.0)          # 10 s old, stopped: still good
  nd._wheel_speed = lambda: None
  assert nd._update_location() == (False, 0.0)         # wheel speed unknown: the strict 2.5 s
  nd._wheel_speed = lambda: 0.0
  nd.params_memory = _MemParams(json.dumps(dict(gps, speed=8.0)))
  assert nd._update_location() == (False, 0.0)         # it was moving at that fix
