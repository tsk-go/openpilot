"""tsk-go fork: Low Speed Smoothing (the Sienna's stop-and-go wobble, Nov 16)."""
import time
from types import SimpleNamespace

import pytest

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_CTRL
from openpilot.starpilot.lateral import low_speed_smoothing as lss

SIENNA = SimpleNamespace(carFingerprint="TOYOTA_SIENNA_4TH_GEN", steerControlType="torque", notCar=False, passive=False,
                         dashcamOnly=False)
OTHER = SimpleNamespace(**{**vars(SIENNA), "carFingerprint": "TOYOTA_RAV4_TSS2"})
MPH = CV.MPH_TO_MS


@pytest.fixture
def off_file(tmp_path, monkeypatch):
  path = tmp_path / "starview" / "low_speed_smoothing_off"
  monkeypatch.setattr(lss, "OFF_FILE", str(path))
  return path


def settle(smoother, curvature, speed, frames=100, **kw):
  out = None
  for _ in range(frames):
    out = smoother.update(curvature, speed, active=kw.get("active", True), blinker=kw.get("blinker", False),
                          lane_change=kw.get("lane_change", False))
  return out


def test_small_corrections_are_halved_at_crawl_speed_and_untouched_from_15_mph():
  for mph in (3, 5, 7, 10):
    assert lss.factor(0.003, mph * MPH) == pytest.approx(0.5)
    assert lss.factor(-0.003, mph * MPH) == pytest.approx(0.5)
  assert lss.factor(0.003, 12.5 * MPH) == pytest.approx(0.75)
  for mph in (15, 20, 45):
    assert lss.factor(0.003, mph * MPH) == 1.0


def test_turns_pass_untouched():
  for curvature in (0.012, 0.05, 0.15, -0.1):        # a 270 ft radius bend and sharper: every intersection turn
    assert lss.factor(curvature, 5 * MPH) == 1.0
  assert lss.factor(0.008, 5 * MPH) == pytest.approx(0.75)


def test_a_bigger_request_never_comes_out_smaller():
  for mph in (2, 5, 8, 10, 12, 14):
    prev = 0.0
    for i in range(1, 400):
      k = i * 5e-5
      out = k * lss.factor(k, mph * MPH)
      assert out > prev
      prev = out


def test_bad_numbers_pass_through():
  assert lss.factor(float("nan"), 3.0) == 1.0
  assert lss.factor(0.003, float("inf")) == 1.0


def test_only_the_4th_gen_sienna(off_file):
  assert lss.supported(SIENNA)
  assert not lss.supported(OTHER)
  assert not lss.supported(SimpleNamespace(**{**vars(SIENNA), "steerControlType": "angle"}))
  assert not lss.supported(SimpleNamespace(**{**vars(SIENNA), "dashcamOnly": True}))
  other = lss.LowSpeedSmoothing(OTHER, live=False)
  assert settle(other, 0.003, 5 * MPH) == 0.003


def test_steering_follows_the_halved_request_and_eases_in(off_file):
  s = lss.LowSpeedSmoothing(SIENNA, live=False)
  assert s.on and s.amount == 1.0
  assert settle(s, 0.003, 5 * MPH, frames=1) == pytest.approx(0.0015)
  # not steering: the measured curvature goes through untouched, and on engaging it fades in over half a second
  assert settle(s, 0.003, 5 * MPH, frames=100, active=False) == 0.003
  assert s.amount == 0.0
  first = s.update(0.003, 5 * MPH, active=True, blinker=False, lane_change=False)
  assert 0.0029 < first < 0.003
  assert settle(s, 0.003, 5 * MPH, frames=int(lss.RAMP_S / DT_CTRL)) == pytest.approx(0.0015)


@pytest.mark.parametrize("kw", [{"blinker": True}, {"lane_change": True}])
def test_blinker_and_lane_change_steer_by_the_full_request(off_file, kw):
  s = lss.LowSpeedSmoothing(SIENNA, live=False)
  assert settle(s, 0.003, 5 * MPH, **kw) == pytest.approx(0.003)
  assert settle(s, 0.003, 5 * MPH) == pytest.approx(0.0015)


def test_switched_off_steers_as_before(off_file):
  off_file.parent.mkdir(parents=True)
  off_file.write_text("off\n")
  s = lss.LowSpeedSmoothing(SIENNA, live=False)
  assert not s.on
  assert settle(s, 0.003, 5 * MPH) == 0.003


def test_the_switch_is_picked_up_while_driving(off_file, monkeypatch):
  monkeypatch.setattr(lss, "INTERVAL_S", 0.01)
  s = lss.LowSpeedSmoothing(SIENNA, live=True)
  try:
    assert s.on
    off_file.parent.mkdir(parents=True)
    off_file.write_text("off\n")
    deadline = time.monotonic() + 2.0
    while s.on and time.monotonic() < deadline:
      time.sleep(0.01)
    assert not s.on
    assert settle(s, 0.003, 5 * MPH) == pytest.approx(0.003)
    off_file.unlink()
    deadline = time.monotonic() + 2.0
    while not s.on and time.monotonic() < deadline:
      time.sleep(0.01)
    assert s.on
  finally:
    s.close()


def test_no_thread_for_other_cars():
  s = lss.LowSpeedSmoothing(OTHER, live=True)
  assert s._thread is None


def test_replay_of_the_nov_16_wobble_requests():
  """The model's requests in the 2:58 PM wobble (6 - 10 mph): +-4e-3 at 0.45 Hz - halved; the turn that follows a
  stop-and-go stretch (0.08) untouched."""
  s = lss.LowSpeedSmoothing(SIENNA, live=False)
  import math
  outs = [s.update(0.004 * math.sin(2 * math.pi * 0.45 * i * DT_CTRL), 3.5, active=True, blinker=False, lane_change=False)
          for i in range(1000)]
  assert max(abs(o) for o in outs) == pytest.approx(0.002, abs=1e-4)
  assert settle(s, 0.08, 3.5) == 0.08
