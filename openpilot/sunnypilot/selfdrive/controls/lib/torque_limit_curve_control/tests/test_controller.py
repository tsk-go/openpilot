"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import math
import unittest

from openpilot.cereal import custom
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control import (
  USABLE_FRACTION, A_ENGAGE, A_RELEASE, A_MAX, MIN_V, RESPONSE_LAG_T,
)
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.controller import TorqueLimitCurveControl
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.tests.helpers import (
  FakeParams, make_cp, make_sm, make_model, SIENNA_LAT_ACCEL_FACTOR, SIENNA_FRICTION,
)

State = custom.LongitudinalPlanSP.TorqueLimitCurveControl.TorqueLimitCurveControlState

SIENNA_PRIOR = SIENNA_LAT_ACCEL_FACTOR * (1 - SIENNA_FRICTION)
SIENNA_USABLE = SIENNA_PRIOR * USABLE_FRACTION

SETTLE = 40  # frames for the a_req filter to settle


def make_controller(enabled: bool = True) -> TorqueLimitCurveControl:
  return TorqueLimitCurveControl(make_cp(), FakeParams({"TorqueLimitCurveControl": enabled}))


def run(ctrl: TorqueLimitCurveControl, sm, v_ego: float, n: int = SETTLE, long_enabled: bool = True, long_override: bool = False):
  for _ in range(n):
    ctrl.update(sm, long_enabled, long_override, v_ego, 0.)


def curve_for(v: float, a_lat: float) -> float:
  """curvature that needs `a_lat` at speed `v`"""
  return a_lat / v ** 2


class TestTorqueLimitCurveControl(unittest.TestCase):
  def test_disabled_by_toggle(self):
    ctrl = make_controller(enabled=False)
    md = make_model(30., curve_kappa=curve_for(30., 3.0), curve_start_m=40.)
    run(ctrl, make_sm(30., md=md), 30.)
    self.assertEqual(ctrl.state, State.disabled)
    self.assertEqual(ctrl.output_v_target, V_CRUISE_UNSET)

  def test_straight_road_does_nothing(self):
    ctrl = make_controller()
    run(ctrl, make_sm(30.), 30.)
    self.assertEqual(ctrl.state, State.enabled)
    self.assertFalse(ctrl.is_active)
    self.assertEqual(ctrl.output_v_target, V_CRUISE_UNSET)
    self.assertEqual(ctrl.a_required, 0.)

  def test_curve_within_limit_does_nothing(self):
    # a curve that only needs 80% of the usable limit at the current speed
    ctrl = make_controller()
    md = make_model(25., curve_kappa=curve_for(25., 0.8 * SIENNA_USABLE), curve_start_m=30.)
    run(ctrl, make_sm(25., md=md), 25.)
    self.assertEqual(ctrl.state, State.enabled)
    self.assertFalse(ctrl.is_active)
    self.assertAlmostEqual(ctrl.lat_accel_required, 0.8 * SIENNA_USABLE, places=3)

  def test_far_curve_over_limit_not_yet_engaged(self):
    # needs 1.5x the limit but 150 m away: required decel is well below A_ENGAGE
    v = 25.
    ctrl = make_controller()
    md = make_model(v, curve_kappa=curve_for(v, 1.5 * SIENNA_USABLE), curve_start_m=150.)
    run(ctrl, make_sm(v, md=md), v)
    v_curve = math.sqrt(SIENNA_USABLE / curve_for(v, 1.5 * SIENNA_USABLE))
    # the limiting point is the first plan sample inside the curve (plan is discretized)
    d = min(xi for xi in md.position.x if xi >= 150.)
    a_needed = (v ** 2 - v_curve ** 2) / (2 * (d - v * RESPONSE_LAG_T))
    self.assertLess(a_needed, A_ENGAGE)
    self.assertAlmostEqual(ctrl.a_required, a_needed, places=3)
    self.assertAlmostEqual(ctrl.v_curve, v_curve, places=3)
    self.assertAlmostEqual(ctrl.dist_to_curve, d, places=3)
    self.assertEqual(ctrl.state, State.enabled)
    self.assertFalse(ctrl.is_active)

  def test_engages_exactly_when_decel_is_needed(self):
    v = 25.
    kappa = curve_for(v, 1.5 * SIENNA_USABLE)
    v_curve = math.sqrt(SIENNA_USABLE / kappa)
    # distance at which constant A_ENGAGE decel is exactly required (after lag compensation)
    d_engage = (v ** 2 - v_curve ** 2) / (2 * A_ENGAGE) + v * RESPONSE_LAG_T

    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d_engage * 1.1)), v)
    self.assertEqual(ctrl.state, State.enabled)

    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d_engage * 0.9)), v)
    self.assertEqual(ctrl.state, State.braking)
    self.assertTrue(ctrl.is_active)
    # asks for roughly the needed decel, requested through v_target = v_ego + a_target
    self.assertLess(ctrl.output_a_target, -A_ENGAGE * 0.9)
    self.assertGreaterEqual(ctrl.output_a_target, -A_MAX)
    self.assertAlmostEqual(ctrl.output_v_target, v + ctrl.output_a_target, places=5)
    self.assertGreaterEqual(ctrl.output_v_target, ctrl.v_curve)

  def test_never_targets_below_curve_speed(self):
    v = 20.
    kappa = curve_for(v, 1.05 * SIENNA_USABLE)  # barely too fast, and the curve is right here
    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=0.)), v)
    self.assertTrue(ctrl.is_active)
    self.assertAlmostEqual(ctrl.output_v_target, ctrl.v_curve, places=5)

  def test_releases_once_slow_enough(self):
    v = 25.
    kappa = curve_for(v, 1.5 * SIENNA_USABLE)
    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=20.)), v)
    self.assertTrue(ctrl.is_active)
    v_curve = ctrl.v_curve
    run(ctrl, make_sm(v_curve - 0.1, md=make_model(v_curve - 0.1, curve_kappa=kappa, curve_start_m=20.)), v_curve - 0.1)
    self.assertEqual(ctrl.state, State.enabled)
    self.assertEqual(ctrl.output_v_target, V_CRUISE_UNSET)

  def test_limited_when_braking_cannot_make_it(self):
    v = 30.
    kappa = curve_for(v, 3.0 * SIENNA_USABLE)
    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=10.)), v)
    self.assertEqual(ctrl.state, State.limited)
    self.assertAlmostEqual(ctrl.output_a_target, -A_MAX, places=5)

  def test_override_and_long_disabled(self):
    v = 25.
    kappa = curve_for(v, 2.0 * SIENNA_USABLE)
    ctrl = make_controller()
    sm = make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=20.))
    run(ctrl, sm, v)
    self.assertTrue(ctrl.is_active)
    run(ctrl, sm, v, long_override=True)
    self.assertEqual(ctrl.state, State.overriding)
    self.assertEqual(ctrl.output_v_target, V_CRUISE_UNSET)
    run(ctrl, sm, v, long_enabled=False)
    self.assertEqual(ctrl.state, State.disabled)

  def test_below_min_speed_does_nothing(self):
    v = MIN_V - 0.5
    kappa = curve_for(v, 3.0 * SIENNA_USABLE)
    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=5.)), v)
    self.assertFalse(ctrl.is_active)

  def test_learned_lower_limit_brakes_earlier(self):
    v = 25.
    kappa = curve_for(v, 1.2 * SIENNA_USABLE)
    d = 60.
    ctrl = make_controller()
    run(ctrl, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d)), v)
    a_with_prior = ctrl.a_required

    # the same car turns out to saturate at 1.0 m/s^2: same curve now needs harder braking
    ctrl2 = make_controller()
    for _ in range(1000):
      ctrl2.update(make_sm(v, saturated=True, actual_lat_accel=1.0), True, False, v, 0.)
    run(ctrl2, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d)), v)
    self.assertLess(ctrl2.lat_accel_limit, ctrl.lat_accel_limit)
    self.assertGreater(ctrl2.a_required, a_with_prior)

  def test_adverse_roll_tightens_limit_but_favourable_roll_does_not_relax(self):
    v = 25.
    kappa = curve_for(v, 1.2 * SIENNA_USABLE)  # left turn (positive yaw rate)
    d = 30.
    base = make_controller()
    run(base, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d)), v)

    adverse = make_controller()
    run(adverse, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d), roll=-0.05), v)
    self.assertGreater(adverse.a_required, base.a_required)

    favourable = make_controller()
    run(favourable, make_sm(v, md=make_model(v, curve_kappa=kappa, curve_start_m=d), roll=0.05), v)
    self.assertAlmostEqual(favourable.a_required, base.a_required, places=6)

  def test_release_hysteresis(self):
    self.assertLess(A_RELEASE, A_ENGAGE)
    self.assertLessEqual(A_ENGAGE, A_MAX)


if __name__ == "__main__":
  unittest.main()
