import os

from openpilot.starpilot.system.starview import advice


def test_only_gentler_and_inside_the_limits(tmp_path):
  path = str(tmp_path / "advice")
  clock = [100.0]
  reader = advice.Advice(path, clock=lambda: clock[0])
  assert reader.speed_cap() is None and reader.extra_follow() == 0.0 and reader.offset() == 0.0
  out = advice.write({"cap": 1.0, "follow": 5.0, "offset": -2.0, "why": "speed bump"}, path, clock=lambda: clock[0])
  assert out == {"cap": advice.MIN_CAP_MPS, "follow": advice.MAX_EXTRA_FOLLOW, "offset": -advice.MAX_OFFSET, "why": "speed_bump"}
  clock[0] += advice.CHECK_S
  assert abs(reader.speed_cap() - advice.MIN_CAP_MPS) < 1e-3       # never below 10 mph
  assert reader.extra_follow() == advice.MAX_EXTRA_FOLLOW
  assert reader.offset() == -advice.MAX_OFFSET
  assert reader.why == "speed_bump"


def test_stale_cleared_and_bad_values(tmp_path):
  path = str(tmp_path / "advice")
  clock = [100.0]
  reader = advice.Advice(path, clock=lambda: clock[0])
  advice.write({"cap": 7.0}, path, clock=lambda: clock[0])
  clock[0] += 0.3
  assert reader.speed_cap() == 7.0 and reader.extra_follow() == 0.0
  clock[0] += 2.0                                                    # the tablet stopped sending
  assert reader.speed_cap() is None
  advice.write({"cap": float("nan"), "follow": "x", "offset": True}, path, clock=lambda: clock[0])
  clock[0] += 0.3
  assert reader.speed_cap() is None and reader.extra_follow() == 0.0 and reader.offset() == 0.0
  advice.write({}, path)
  assert not os.path.exists(path)
  clock[0] += 0.3
  assert reader.speed_cap() is None


def test_file_looked_at_at_most_four_times_a_second(tmp_path, monkeypatch):
  path = str(tmp_path / "advice")
  clock = [100.0]
  reader = advice.Advice(path, clock=lambda: clock[0])
  calls = []
  real = os.stat
  monkeypatch.setattr(advice.os, "stat", lambda p: calls.append(p) or real(p))
  for _ in range(100):                  # planner at 20 Hz for 1 s (5 s of controls at 100 Hz looks the same)
    reader.speed_cap()
    clock[0] += 0.01
  assert len(calls) <= 5


# ---- the hooks in upstream's planner and Lane Centering (one line each there)

def _reader(tmp_path, req):
  path = str(tmp_path / "advice")
  clock = [100.0]
  advice.write(req, path, clock=lambda: clock[0])
  clock[0] += 0.3
  return advice.Advice(path, clock=lambda: clock[0])


def test_mpc_follow(tmp_path):
  from types import SimpleNamespace as NS
  from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import get_T_FOLLOW
  profile = NS(follow_seconds=1.8)
  none = _reader(tmp_path, {})
  for follow, last in ((None, None), (1.2, profile), (None, profile)):
    assert none.mpc_follow(follow, last, 1, True) is follow                 # no advice: the planner's own, as it is
  more = _reader(tmp_path, {"follow": 0.5})
  assert more.mpc_follow(1.2, profile, 1, True) == 1.7
  assert more.mpc_follow(None, profile, 1, True) == 1.8 + 0.5             # the MPC call's own fallback first
  assert more.mpc_follow(None, None, 1, True) == get_T_FOLLOW(1) + 0.5
  assert more.mpc_follow(1.2, profile, 1, False) == 1.2                   # not eligible: nothing added


def test_cruise_and_lane_settings(tmp_path):
  from openpilot.starpilot.lateral.lane_runtime import LaneCenteringSettings
  slow = _reader(tmp_path, {"cap": 9.0, "offset": 0.2})
  assert slow.cruise(25.0, True) == 9.0 and slow.cruise(8.0, True) == 8.0 and slow.cruise(25.0, False) == 25.0
  settings = LaneCenteringSettings()
  shifted = slow.lane_settings(settings)
  assert shifted.offset_m == min(advice.MAX_OFFSET, settings.offset_m + 0.2)
  assert _reader(tmp_path, {}).lane_settings(settings) is settings


def test_the_hooks_are_in_place():
  import ast
  from pathlib import Path
  root = Path(advice.__file__).resolve().parents[3]
  planner = (root / "selfdrive/controls/lib/longitudinal_planner.py").read_text()
  assert "follow = self.starview_advice.mpc_follow(follow, self.last_profile, sm['selfdriveState'].personality," in planner
  assert planner.index("self.starview_advice.mpc_follow(") < planner.index("self.mpc.update(")
  assert "v_cruise = self.starview_advice.cruise(v_cruise, profile_eligible)" in planner
  lanes = ast.parse((root / "starpilot/lateral/lane_runtime.py").read_text())
  assert any("self.advice.lane_settings(self.settings)" in ast.unparse(n) for n in ast.walk(lanes) if isinstance(n, ast.Return))
