"""Fork fix 4: a wake after a parked shutdown, with no drive since, shuts down again after 2 minutes instead of staying
on an hour (fixes/parked_restart.py, through upstream's PowerMonitoring.should_shutdown). Moved here from the end of
upstream's test_power_monitoring.py (Nov 24)."""
import itertools

import pytest

from openpilot.starpilot.system.starview.fixes import parked_restart
from openpilot.system.hardware.power_monitoring import CAR_BATTERY_CAPACITY_uWh, DELAY_SHUTDOWN_TIME_S, PowerMonitoring
from openpilot.system.hardware.tests import test_power_monitoring as upstream


@pytest.fixture
def setup(tmp_path, monkeypatch):
  monkeypatch.setattr("time.monotonic", upstream.mock_time_monotonic)
  monkeypatch.setattr(parked_restart, "MARKER", str(tmp_path / "parked_off"))
  monkeypatch.setattr("openpilot.system.hardware.power_monitoring.HARDWARE.get_current_power_draw", lambda: 0)
  return tmp_path / "parked_off", FakeParams()


class FakeParams(dict):
  """The two switches should_shutdown reads, as set here (the rest: unset)."""
  def get_bool(self, key):
    return bool(self.get(key, False))

  def put_bool(self, key, value):
    self[key] = value


def test_parked_restart_shuts_down_quickly(setup):
  marker, _ = setup
  pm = PowerMonitoring()
  assert not pm.parked.restart
  pm.parked.mark()
  assert marker.exists()

  # woken by the car's CAN with the car still off: off again after 2 minutes, not after an hour
  pm = PowerMonitoring()
  pm.car_battery_capacity_uWh = CAR_BATTERY_CAPACITY_uWh
  assert pm.parked.restart
  upstream.set_mock_time(100)
  assert not pm.should_shutdown(False, True, 0, False)
  upstream.set_mock_time(130)
  assert pm.should_shutdown(False, True, 0, False)
  assert not pm.should_shutdown(True, True, 0, False)       # ignition: never
  assert not pm.should_shutdown(False, False, 0, False)     # not in a car: never

  # a drive clears it: back to the normal rules (stays on, good battery, an hour minimum)
  pm.parked.clear()
  assert not marker.exists()
  upstream.set_mock_time(400)
  assert not pm.should_shutdown(False, True, 0, True)
  assert not PowerMonitoring().parked.restart


def _original(pm, params, ignition, in_car, offroad_time, started_seen, now, base, restart):
  """should_shutdown as the fix was first written inside it (patch 50), for the same inputs."""
  quick = restart and not started_seen and offroad_time > parked_restart.RESTART_SHUTDOWN_S
  s = base or quick
  s = s and not ignition and not params.get_bool("DisablePowerDown") and in_car
  s = s and (quick or offroad_time > DELAY_SHUTDOWN_TIME_S)
  s = s or params.get_bool("ForcePowerDown")
  return s and (started_seen or now > 3600 or quick)


@pytest.mark.parametrize("restart", [False, True])
def test_same_answers_as_the_fix_inside_should_shutdown(setup, restart):
  # every combination of the inputs: the hook gives what the fix gave when it was written into should_shutdown
  marker, params = setup
  if restart:
    marker.write_text("parked shutdown\n")
  pm = PowerMonitoring()
  pm.params = params
  for ignition, in_car, started_seen, dpd, fpd, empty, offroad, now in itertools.product(
      (False, True), (False, True), (False, True), (False, True), (False, True), (False, True), (60, 200, 400), (500, 4000)):
    params.put_bool("DisablePowerDown", dpd)
    params.put_bool("ForcePowerDown", fpd)
    pm.car_battery_capacity_uWh = 0 if empty else CAR_BATTERY_CAPACITY_uWh
    upstream.set_mock_time(now - 1)        # should_shutdown's time.monotonic() adds one
    expected = _original(pm, params, ignition, in_car, offroad, started_seen, now, empty, restart)
    assert pm.should_shutdown(ignition, in_car, now - offroad, started_seen) == expected, \
      (ignition, in_car, started_seen, dpd, fpd, empty, offroad, now)
