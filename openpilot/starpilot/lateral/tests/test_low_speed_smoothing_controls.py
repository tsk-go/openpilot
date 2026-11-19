"""tsk-go fork: Low Speed Smoothing through the real controlsd on a 4th-gen Sienna (synthetic inputs, one control step at
a time). The steering-permission handshake with pandad is switched off here: this checks the curvature path only."""
import time

import pytest

from opendbc.car.car_helpers import interfaces
from opendbc.car.toyota.values import CAR
from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.prefix import OpenpilotPrefix
from openpilot.starpilot.lateral import low_speed_smoothing as lss


@pytest.fixture
def controls(tmp_path, monkeypatch):
  monkeypatch.setattr(lss, "OFF_FILE", str(tmp_path / "low_speed_smoothing_off"))
  with OpenpilotPrefix():
    cp = interfaces[CAR.TOYOTA_SIENNA_4TH_GEN].get_non_essential_params(CAR.TOYOTA_SIENNA_4TH_GEN)
    cp.secOcKeyAvailable = True
    Params().put("CarParams", cp.to_bytes(), block=True)
    from openpilot.selfdrive.controls.controlsd import Controls
    c = Controls()
    c.aol_replay = False
    c.ordinary_axis_ack_required = False
    try:
      yield c
    finally:
      c.low_speed_smoothing.close()


def steer(c, curvature, speed, *, frames=120, blinker=False):
  for _ in range(frames):
    msgs = []
    m = messaging.new_message("carState")
    cs = m.carState
    cs.vEgo = cs.vEgoRaw = speed
    cs.canValid = True
    cs.cruiseState.enabled = True
    cs.gearShifter = "drive"
    cs.leftBlinker = blinker
    msgs.append(m)
    m = messaging.new_message("selfdriveState")
    m.selfdriveState.enabled = m.selfdriveState.active = True
    msgs.append(m)
    m = messaging.new_message("modelV2")
    m.modelV2.action.desiredCurvature = curvature
    msgs.append(m)
    m = messaging.new_message("vehicleParameters")
    m.vehicleParameters.steerRatio, m.vehicleParameters.stiffnessFactor, m.vehicleParameters.valid = 15.0, 1.0, True
    msgs.append(m)
    m = messaging.new_message("lateralDelay")
    m.lateralDelay.lateralDelay = 0.3
    msgs.append(m)
    msgs.append(messaging.new_message("longitudinalPlan"))
    c.sm.update_msgs(time.monotonic_ns(), msgs)
    CC = c.state_control()[0]
    assert CC.latActive
  return c.desired_curvature


def test_the_sienna_steers_by_half_a_small_correction_at_crawl_speed(controls):
  assert controls.low_speed_smoothing.supported and controls.low_speed_smoothing._thread is not None
  assert steer(controls, 0.003, 3.0) == pytest.approx(0.0015, rel=1e-3)          # 6.7 mph


def test_full_request_with_the_blinker_above_15_mph_and_in_turns(controls):
  assert steer(controls, 0.003, 3.0, blinker=True) == pytest.approx(0.003, rel=1e-3)
  assert steer(controls, 0.003, 8.0) == pytest.approx(0.003, rel=1e-3)            # 18 mph
  assert steer(controls, 0.08, 3.0) == pytest.approx(0.08, rel=1e-3)               # an intersection turn


def test_switched_off_in_galaxy_steers_as_before(controls, tmp_path):
  (tmp_path / "low_speed_smoothing_off").write_text("off\n")
  controls.low_speed_smoothing.on = lss.switched_on(controls.low_speed_smoothing.path)   # the 1 s look, done now
  assert steer(controls, 0.003, 3.0) == pytest.approx(0.003, rel=1e-3)
