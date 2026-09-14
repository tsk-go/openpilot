"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import numpy as np

from opendbc.car import structs
import openpilot.cereal.messaging as messaging
from openpilot.cereal import custom
from openpilot.common.constants import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.car.cruise import V_CRUISE_UNSET
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control import (
  MIN_V, USABLE_FRACTION, A_ENGAGE, A_RELEASE, A_MAX, D_MIN, ROLL_HORIZON_T, KAPPA_MIN, RESPONSE_LAG_T,
)
from openpilot.sunnypilot.selfdrive.controls.lib.torque_limit_curve_control.lat_limit_learner import LateralLimitLearner

State = custom.LongitudinalPlanSP.TorqueLimitCurveControl.TorqueLimitCurveControlState

ACTIVE_STATES = (State.braking, State.limited)
ENABLED_STATES = (State.enabled, State.overriding, *ACTIVE_STATES)

# smooth the required deceleration a little so the model's frame-to-frame plan noise
# doesn't chatter the engage/release decision
A_REQ_FILTER_RC = 0.3  # s


class TorqueLimitCurveControl:
  """
  Physics-only curve speed control.

  Each frame, for every point of the model's path plan:
    kappa_i   = |yaw_rate_i| / v_i                         curvature of the path there
    v_req_i   = sqrt(a_lat_usable / kappa_i)               fastest we can take that point
    a_req_i   = (v_ego^2 - v_req_i^2) / (2 * d_i)          constant decel needed to get there in time

  The most demanding point wins. Nothing happens until a_req >= A_ENGAGE; then the
  car is asked for exactly a_req (capped at A_MAX) until it's no longer needed.
  """

  def __init__(self, CP: structs.CarParams, params: Params | None = None):
    self.params = params or Params()
    self.learner = LateralLimitLearner(CP, self.params)
    self.frame = -1
    self.enabled_toggle = self.params.get_bool("TorqueLimitCurveControl")

    self.state = State.disabled
    self.is_enabled = False
    self.is_active = False

    self.long_enabled = False
    self.long_override = False
    self.v_ego = 0.
    self.a_ego = 0.

    # telemetry
    self.lat_accel_limit = 0.  # learned ceiling
    self.lat_accel_usable = 0.  # what we plan against
    self.lat_accel_required = 0.  # max lat accel the path ahead would need at current speed
    self.v_curve = 0.  # speed the limiting point allows
    self.dist_to_curve = 0.
    self.a_required = 0.  # decel needed to reach v_curve at the limiting point
    self.a_req_filter = FirstOrderFilter(0., A_REQ_FILTER_RC, DT_MDL)

    self.a_target = 0.
    self.output_v_target = V_CRUISE_UNSET
    self.output_a_target = 0.

  # ---- params --------------------------------------------------------------------

  def _update_params(self) -> None:
    if self.frame % int(PARAMS_UPDATE_PERIOD / DT_MDL) == 0:
      self.enabled_toggle = self.params.get_bool("TorqueLimitCurveControl")

  # ---- physics -------------------------------------------------------------------

  def _update_calculations(self, sm: messaging.SubMaster) -> None:
    self.lat_accel_limit = self.learner.limit
    self.lat_accel_usable = self.lat_accel_limit * USABLE_FRACTION

    md = sm['modelV2']
    if len(md.position.x) == 0 or len(md.velocity.x) == 0 or len(md.orientationRate.z) == 0:
      self.a_required = 0.
      self.lat_accel_required = 0.
      return

    t = np.asarray(md.position.t, dtype=float) if len(md.position.t) else np.zeros(len(md.position.x))
    x = np.asarray(md.position.x, dtype=float)
    v_plan = np.maximum(np.asarray(md.velocity.x, dtype=float), 1.0)
    yaw_rate = np.asarray(md.orientationRate.z, dtype=float)

    n = min(len(x), len(v_plan), len(yaw_rate), len(t))
    x, v_plan, yaw_rate, t = x[:n], v_plan[:n], yaw_rate[:n], t[:n]

    kappa = np.abs(yaw_rate) / v_plan

    # Road roll: current roll is only trusted for the near horizon and only used to
    # tighten the limit (a bank against the turn), never to relax it.
    usable = np.full(n, self.lat_accel_usable)
    roll = float(sm['vehicleParameters'].roll) if sm.valid['vehicleParameters'] else 0.
    if roll != 0.:
      near = t <= ROLL_HORIZON_T
      roll_term = np.sign(yaw_rate) * roll * ACCELERATION_DUE_TO_GRAVITY  # + helps, - hurts
      usable[near] = np.minimum(usable[near], usable[near] + roll_term[near])
    usable = np.maximum(usable, 0.1)

    v_ego = max(self.v_ego, 0.1)
    self.lat_accel_required = float(np.max(kappa) * v_ego ** 2)

    curved = kappa > KAPPA_MIN
    if not np.any(curved):
      self.a_required = 0.
      self.v_curve = V_CRUISE_UNSET
      self.dist_to_curve = 0.
      return

    v_req = np.full(n, np.inf)
    v_req[curved] = np.sqrt(usable[curved] / kappa[curved])

    too_fast = v_req < v_ego
    if not np.any(too_fast):
      self.a_required = 0.
      self.v_curve = float(np.min(v_req))
      self.dist_to_curve = float(x[int(np.argmin(v_req))])
      return

    d = np.maximum(x - v_ego * RESPONSE_LAG_T, D_MIN)
    a_req = np.zeros(n)
    a_req[too_fast] = (v_ego ** 2 - v_req[too_fast] ** 2) / (2. * d[too_fast])

    i = int(np.argmax(a_req))
    self.a_required = float(a_req[i])
    self.v_curve = float(v_req[i])
    self.dist_to_curve = float(max(x[i], 0.))

  # ---- state machine ---------------------------------------------------------------

  def _update_state_machine(self) -> tuple[bool, bool]:
    a_req = self.a_req_filter.x

    if self.state != State.disabled:
      if not self.long_enabled or not self.enabled_toggle:
        self.state = State.disabled
      elif self.long_override:
        self.state = State.overriding
      elif self.state == State.enabled:
        if self.v_ego > MIN_V and a_req >= A_ENGAGE:
          self.state = State.braking
      elif self.state == State.overriding:
        if not self.long_override:
          self.state = State.enabled
      elif self.state in ACTIVE_STATES:
        if self.v_ego <= MIN_V or a_req < A_RELEASE:
          self.state = State.enabled
        else:
          # "limited": even max braking can't reach the curve speed in time; the
          # steering limit will be exceeded unless the driver intervenes
          self.state = State.limited if a_req > A_MAX else State.braking
    elif self.long_enabled and self.enabled_toggle:
      self.state = State.overriding if self.long_override else State.enabled

    return self.state in ENABLED_STATES, self.state in ACTIVE_STATES

  # ---- solution --------------------------------------------------------------------

  def _update_solution(self) -> float:
    if self.state not in ACTIVE_STATES:
      return 0.
    # ask for exactly what's needed, never less than the release threshold (so the
    # brake request doesn't fade to nothing right at the edge), never more than the
    # planner's cruise path can deliver.
    return -float(np.clip(self.a_req_filter.x, A_RELEASE, A_MAX))

  def get_v_target_from_control(self) -> float:
    if not self.is_active:
      return V_CRUISE_UNSET
    # The planner's cruise path does target_accel = clip(v_cruise - v_ego, A_CRUISE_MIN, ...),
    # so v_ego + a_target requests exactly a_target. Never ask to go below the speed the
    # curve itself allows.
    return max(self.v_ego + self.a_target, self.v_curve)

  # ---- main --------------------------------------------------------------------------

  def update(self, sm: messaging.SubMaster, long_enabled: bool, long_override: bool, v_ego: float, a_ego: float) -> None:
    self.long_enabled = long_enabled
    self.long_override = long_override
    self.v_ego = v_ego
    self.a_ego = a_ego

    self._update_params()
    self.learner.update(sm)

    if self.enabled_toggle and self.long_enabled:
      self._update_calculations(sm)
    else:
      self.a_required = 0.
    self.a_req_filter.update(self.a_required)

    self.is_enabled, self.is_active = self._update_state_machine()
    self.a_target = self._update_solution()

    self.output_v_target = self.get_v_target_from_control()
    self.output_a_target = self.a_target

    self.frame += 1
