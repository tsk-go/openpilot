"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import time

from opendbc.car import structs
from opendbc.car.lateral import ISO_LATERAL_ACCEL
from openpilot.cereal import messaging
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.common.swaglog import cloudlog

CACHE_KEY = "TorqueLimitCurveControlCache"
CACHE_WRITE_PERIOD = 60.  # s

# Saturation samples are the ground truth for the ceiling. They are filtered
# slowly (in "saturated seconds") so a single odd sample can't move the limit much.
SAT_SAMPLE_RC = 20.  # s of saturated driving for ~63% convergence
# The limit is blended from the prior to the learned value as evidence accumulates.
SAT_SAMPLES_FULL_TRUST = int(10. / DT_MDL)  # 10 s of saturation → fully trust the learned value
# Clip each sample relative to the prior to reject garbage (e.g. sensor glitches).
SAT_SAMPLE_MIN_RATIO = 0.5
SAT_SAMPLE_MAX_RATIO = 1.5
# Only count saturation while there is a meaningful lateral request.
SAT_MIN_LAT_ACCEL = 0.5  # m/s^2

# Lateral accel sustained without saturation is a lower bound on the ceiling.
UNSAT_FILTER_RC = 0.5  # s, must be sustained, not a bump
UNSAT_DECAY_RATE = 0.2 / 3600.  # m/s^2 per second (~0.2 m/s^2 per hour) so stale evidence fades

MIN_SPEED = 10.  # m/s, same as latcontrol sat_check_min_speed


class LateralLimitLearner:
  """
  Learns the maximum lateral acceleration the car's steering can actually deliver.

  Sources, in order of trust:
    1. Saturation samples: whenever the lateral controller reports `saturated`, the
       measured lateral acceleration at that moment *is* the ceiling.
    2. Unsaturated evidence: lateral acceleration sustained without saturating is a
       floor under the ceiling.
    3. Prior: for torque-controlled cars, `latAccelFactor * (1 - friction)` — the
       lateral accel at full actuator output after the friction feedforward has
       eaten its share. Kept live from `lateralTorqueParameters`. For angle/curvature
       cars, the ISO 11270 lateral accel limit enforced by the car interface.

  The learned limit is cached per car fingerprint in a param.
  """

  def __init__(self, CP: structs.CarParams, params: Params | None = None):
    self.params = params or Params()
    self.fingerprint = str(CP.carFingerprint)
    self.torque_control = CP.lateralTuning.which() == 'torque'

    if self.torque_control:
      tp = CP.lateralTuning.torque
      self.prior = self._prior_from_torque_params(float(tp.latAccelFactor), float(tp.friction))
    else:
      self.prior = float(ISO_LATERAL_ACCEL)
    self.offline_prior = self.prior

    self.sat_filter = FirstOrderFilter(self.prior, SAT_SAMPLE_RC, DT_MDL)
    self.sat_samples = 0
    self.unsat_filter = FirstOrderFilter(0., UNSAT_FILTER_RC, DT_MDL)
    self.unsat_max = 0.

    self.saturated = False
    self.measured_lat_accel = 0.
    self._last_cache_write = 0.
    self._dirty = False

    self._load_cache()

  @staticmethod
  def _prior_from_torque_params(lat_accel_factor: float, friction: float) -> float:
    # lateral_accel_from_torque(steer_max=1.0) = latAccelFactor; the friction feedforward
    # (friction * latAccelFactor) is consumed whenever the controller is pushing hard.
    return max(lat_accel_factor * (1. - max(min(friction, 0.9), 0.)), 0.1)

  # ---- persistence ------------------------------------------------------------

  def _load_cache(self) -> None:
    try:
      cache = self.params.get(CACHE_KEY)
    except Exception:
      cache = None
    if not isinstance(cache, dict) or cache.get("fingerprint") != self.fingerprint:
      return
    try:
      self.sat_filter.x = float(cache["latAccelLimit"])
      self.sat_samples = int(cache.get("samples", 0))
      self.unsat_max = float(cache.get("unsatMax", 0.))
      cloudlog.info(f"TLCC: loaded cached lateral limit {self.sat_filter.x:.2f} m/s^2 ({self.sat_samples} samples)")
    except (KeyError, TypeError, ValueError):
      cloudlog.warning("TLCC: ignoring malformed cache")

  def _write_cache(self, now: float) -> None:
    if not self._dirty or now - self._last_cache_write < CACHE_WRITE_PERIOD:
      return
    self.params.put(CACHE_KEY, {
      "fingerprint": self.fingerprint,
      "latAccelLimit": round(float(self.sat_filter.x), 4),
      "unsatMax": round(float(self.unsat_max), 4),
      "samples": int(self.sat_samples),
    })
    self._last_cache_write = now
    self._dirty = False

  # ---- estimate ---------------------------------------------------------------

  @property
  def limit(self) -> float:
    """Best estimate of the lateral acceleration ceiling (m/s^2), before any usable margin."""
    trust = min(self.sat_samples / SAT_SAMPLES_FULL_TRUST, 1.)
    est = (1. - trust) * self.prior + trust * self.sat_filter.x
    # sustained, unsaturated lateral accel proves the ceiling is at least that high
    return max(est, self.unsat_max)

  def update_prior(self, sm: messaging.SubMaster) -> None:
    if not self.torque_control:
      return
    ltp = sm['lateralTorqueParameters']
    if sm.updated['lateralTorqueParameters'] and ltp.useParams and ltp.latAccelFactorFiltered > 0:
      self.prior = self._prior_from_torque_params(float(ltp.latAccelFactorFiltered), float(ltp.frictionCoefficientFiltered))

  def update(self, sm: messaging.SubMaster) -> None:
    now = time.monotonic()
    self.update_prior(sm)

    CS = sm['carState']
    CC = sm['carControl']
    lcs = sm['controlsState'].lateralControlState
    which = lcs.which()

    if which == 'torqueState':
      st = lcs.torqueState
      self.saturated = bool(st.saturated)
      self.measured_lat_accel = abs(float(st.actualLateralAccel))
    elif which == 'curvatureState':
      st = lcs.curvatureState
      self.saturated = bool(st.saturated)
      self.measured_lat_accel = abs(float(st.actualCurvature)) * CS.vEgo ** 2
    elif which == 'angleState':
      self.saturated = bool(lcs.angleState.saturated)
      self.measured_lat_accel = abs(float(sm['controlsState'].curvature)) * CS.vEgo ** 2
    else:
      self.saturated = False
      self.measured_lat_accel = abs(float(sm['controlsState'].curvature)) * CS.vEgo ** 2

    # decay stale unsaturated evidence
    self.unsat_max = max(self.unsat_max - UNSAT_DECAY_RATE * DT_MDL, 0.)

    valid = CC.latActive and not CS.steeringPressed and CS.vEgo > MIN_SPEED
    if not valid:
      self.unsat_filter.x = 0.
      self._write_cache(now)
      return

    if self.saturated:
      self.unsat_filter.x = 0.
      if self.measured_lat_accel > SAT_MIN_LAT_ACCEL:
        sample = min(max(self.measured_lat_accel, SAT_SAMPLE_MIN_RATIO * self.prior), SAT_SAMPLE_MAX_RATIO * self.prior)
        if self.sat_samples == 0:
          self.sat_filter.x = sample
        else:
          self.sat_filter.update(sample)
        self.sat_samples += 1
        self._dirty = True
    else:
      sustained = self.unsat_filter.update(self.measured_lat_accel)
      if sustained > self.unsat_max:
        self.unsat_max = sustained
        self._dirty = True

    self._write_cache(now)
