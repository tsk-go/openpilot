import pytest

from openpilot.starpilot.system.starview import nudge


def test_strength_is_kept_and_read_back(tmp_path):
  path = str(tmp_path / "starview" / "nudge_pct")
  assert nudge.write(60, path) == 60
  assert nudge.read(path) == 60
  assert nudge.write(100, path) is None          # 100 % = the car's own rule: no file
  assert nudge.read(path) is None
  assert nudge.write(None, path) is None
  for bad in (10, 151, "x"):
    with pytest.raises(ValueError):
      nudge.write(bad, path)


def test_modeld_reads_it_once_a_second(tmp_path):
  path = str(tmp_path / "nudge_pct")
  now = [0.0]
  setting = nudge.NudgeSetting("toyota", path, clock=lambda: now[0])
  assert setting.torque() is None
  nudge.write(60, path)
  assert setting.torque() is None                # not re-read yet
  now[0] = 1.0
  assert setting.torque() == pytest.approx(60.0)  # 60 % of Toyota's 100
  nudge.write(140, path)
  now[0] = 2.0
  assert setting.torque() == pytest.approx(140.0)


def test_other_cars_keep_the_stock_rule(tmp_path):
  path = str(tmp_path / "nudge_pct")
  nudge.write(60, path)
  assert nudge.NudgeSetting("hyundai", path).torque() is None
