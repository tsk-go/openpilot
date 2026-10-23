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
