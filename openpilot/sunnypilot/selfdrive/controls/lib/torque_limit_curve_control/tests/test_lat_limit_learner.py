"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import unittest
from typing import cast
from unittest import mock

from opendbc.car.lateral import ISO_LATERAL_ACCEL
from openpilot.common.params import Params
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.lat_limit_learner import (
  LateralLimitLearner, CACHE_KEY, SAT_SAMPLES_FULL_TRUST, CACHE_WRITE_PERIOD,
)
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.tests.helpers import (
  FakeParams, make_cp, make_sm, SIENNA_LAT_ACCEL_FACTOR, SIENNA_FRICTION,
)

SIENNA_PRIOR = SIENNA_LAT_ACCEL_FACTOR * (1 - SIENNA_FRICTION)


class TestLateralLimitLearner(unittest.TestCase):
  def test_prior_from_torque_params(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    self.assertAlmostEqual(learner.prior, SIENNA_PRIOR, places=4)
    self.assertAlmostEqual(learner.limit, SIENNA_PRIOR, places=4)

  def test_prior_for_angle_cars(self):
    learner = LateralLimitLearner(make_cp(torque=False), cast(Params, FakeParams()))
    self.assertAlmostEqual(learner.limit, ISO_LATERAL_ACCEL)

  def test_prior_tracks_live_torque_params(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    learner.update(make_sm(25., ltp_use_params=True, ltp_factor=2.0, ltp_friction=0.1))
    self.assertAlmostEqual(learner.prior, 2.0 * 0.9, places=4)

  def test_saturation_samples_move_the_limit(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    # the car saturates at 1.30 m/s^2, below the 1.45 prior
    for _ in range(SAT_SAMPLES_FULL_TRUST * 3):
      learner.update(make_sm(25., saturated=True, actual_lat_accel=1.30))
    self.assertGreaterEqual(learner.sat_samples, SAT_SAMPLES_FULL_TRUST)
    self.assertAlmostEqual(learner.limit, 1.30, delta=0.03)

  def test_limit_blends_from_prior_with_evidence(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    learner.update(make_sm(25., saturated=True, actual_lat_accel=1.0))
    # one sample: barely trusted, limit stays near the prior
    self.assertGreater(learner.limit, 1.35)
    self.assertLess(learner.limit, SIENNA_PRIOR)

  def test_saturation_ignored_when_driver_steering_or_slow_or_inactive(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    learner.update(make_sm(25., saturated=True, actual_lat_accel=1.0, steering_pressed=True))
    learner.update(make_sm(5., saturated=True, actual_lat_accel=1.0))
    learner.update(make_sm(25., saturated=True, actual_lat_accel=1.0, lat_active=False))
    self.assertEqual(learner.sat_samples, 0)

  def test_saturation_at_negligible_lat_accel_ignored(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    learner.update(make_sm(25., saturated=True, actual_lat_accel=0.2))
    self.assertEqual(learner.sat_samples, 0)

  def test_samples_are_clipped_relative_to_prior(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    # 0.55 m/s^2 is above the noise floor but below half the prior: clipped to 0.5 * prior
    for _ in range(SAT_SAMPLES_FULL_TRUST * 3):
      learner.update(make_sm(25., saturated=True, actual_lat_accel=0.55))
    self.assertAlmostEqual(learner.limit, 0.5 * SIENNA_PRIOR, delta=0.02)

  def test_sustained_unsaturated_lat_accel_raises_floor(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    # bad saturation evidence says 1.0...
    for _ in range(SAT_SAMPLES_FULL_TRUST * 3):
      learner.update(make_sm(25., saturated=True, actual_lat_accel=1.0))
    self.assertAlmostEqual(learner.limit, 1.0, delta=0.03)
    # ...but the car then sustains 1.6 without saturating: that is proof
    for _ in range(100):
      learner.update(make_sm(25., saturated=False, actual_lat_accel=1.6))
    self.assertAlmostEqual(learner.limit, 1.6, delta=0.02)

  def test_unsaturated_bump_does_not_raise_floor(self):
    learner = LateralLimitLearner(make_cp(), cast(Params, FakeParams()))
    learner.update(make_sm(25., saturated=False, actual_lat_accel=3.0))
    self.assertLess(learner.unsat_max, 0.5)

  def test_cache_round_trip(self):
    params = FakeParams()
    learner = LateralLimitLearner(make_cp(), cast(Params, params))
    with mock.patch("openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.lat_limit_learner.time.monotonic") as mono:
      mono.return_value = 0.
      for _ in range(SAT_SAMPLES_FULL_TRUST * 3):
        learner.update(make_sm(25., saturated=True, actual_lat_accel=1.30))
      mono.return_value = CACHE_WRITE_PERIOD + 1.
      learner.update(make_sm(25., saturated=True, actual_lat_accel=1.30))
    self.assertIn(CACHE_KEY, params.values)
    self.assertEqual(params.values[CACHE_KEY]["fingerprint"], "TOYOTA_SIENNA")

    fresh = LateralLimitLearner(make_cp(), cast(Params, params))
    self.assertAlmostEqual(fresh.limit, learner.limit, places=3)
    self.assertEqual(fresh.sat_samples, learner.sat_samples)

  def test_cache_ignored_for_other_fingerprint(self):
    params = FakeParams({CACHE_KEY: {"fingerprint": "TOYOTA_RAV4_TSS2", "latAccelLimit": 0.5, "samples": 9999}})
    learner = LateralLimitLearner(make_cp(), cast(Params, params))
    self.assertEqual(learner.sat_samples, 0)
    self.assertAlmostEqual(learner.limit, SIENNA_PRIOR, places=4)


if __name__ == "__main__":
  unittest.main()
