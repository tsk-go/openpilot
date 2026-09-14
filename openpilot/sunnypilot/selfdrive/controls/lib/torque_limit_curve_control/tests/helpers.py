"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from typing import cast

import numpy as np

from opendbc.car import structs
from openpilot.cereal import log, messaging
from openpilot.selfdrive.modeld.constants import ModelConstants

SIENNA_LAT_ACCEL_FACTOR = 1.69
SIENNA_FRICTION = 0.14


class FakeParams:
  def __init__(self, values: dict | None = None):
    self.values: dict = dict(values or {})

  def get(self, key, block=False, return_default=False):
    return self.values.get(key)

  def get_bool(self, key, block=False):
    return bool(self.values.get(key, False))

  def put(self, key, dat, block=False):
    self.values[key] = dat

  def put_bool(self, key, val, block=False):
    self.values[key] = bool(val)


class _FakeSubMaster:
  def __init__(self, msgs: dict):
    self.msgs = msgs
    self.updated = dict.fromkeys(msgs, True)
    self.valid = dict.fromkeys(msgs, True)

  def __getitem__(self, k):
    return self.msgs[k]


def make_cp(torque: bool = True, lat_accel_factor: float = SIENNA_LAT_ACCEL_FACTOR, friction: float = SIENNA_FRICTION,
            fingerprint: str = "TOYOTA_SIENNA"):
  CP = structs.CarParams()
  CP.carFingerprint = fingerprint
  if torque:
    CP.lateralTuning.init('torque')
    CP.lateralTuning.torque.latAccelFactor = lat_accel_factor
    CP.lateralTuning.torque.friction = friction
  else:
    CP.steerControlType = structs.CarParams.SteerControlType.angle
    CP.lateralTuning.init('pid')
  return CP


def make_model(v_ego: float, curve_kappa: float = 0., curve_start_m: float = 1e9, curve_len_m: float = 40.):
  """
  Build a modelV2 plan for a car travelling at v_ego with a constant-curvature
  curve of `curve_kappa` [1/m] beginning `curve_start_m` ahead and lasting `curve_len_m`.
  Path distance follows constant speed (the model isn't planning to slow).
  """
  md = log.ModelDataV2.new_message()
  t = np.array(ModelConstants.T_IDXS)
  x = v_ego * t
  v = np.full_like(t, v_ego)
  in_curve = (x >= curve_start_m) & (x <= curve_start_m + curve_len_m)
  yaw = np.where(in_curve, curve_kappa * v_ego, 0.)
  for name, arr in (('t', t), ('x', x)):
    md.position.init(name, len(t))
    for i, val in enumerate(arr):
      getattr(md.position, name)[i] = float(val)
  md.velocity.init('x', len(t))
  md.orientationRate.init('z', len(t))
  for i in range(len(t)):
    md.velocity.x[i] = float(v[i])
    md.orientationRate.z[i] = float(yaw[i])
  return md


def make_controls_state(saturated: bool = False, actual_lat_accel: float = 0., curvature: float = 0.):
  cs = log.ControlsState.new_message()
  cs.curvature = curvature
  cs.lateralControlState.init('torqueState')
  cs.lateralControlState.torqueState.saturated = saturated
  cs.lateralControlState.torqueState.actualLateralAccel = actual_lat_accel
  return cs


def make_sm(v_ego: float, *, md=None, saturated: bool = False, actual_lat_accel: float = 0., lat_active: bool = True,
            steering_pressed: bool = False, roll: float = 0., ltp_use_params: bool = False, ltp_factor: float = 0.,
            ltp_friction: float = 0.) -> messaging.SubMaster:
  CS = structs.CarState()
  CS.vEgo = v_ego
  CS.steeringPressed = steering_pressed
  CC = structs.CarControl()
  CC.latActive = lat_active
  CC.enabled = True
  vp = log.VehicleParameters.new_message()
  vp.roll = roll
  ltp = log.LateralTorqueParameters.new_message()
  ltp.useParams = ltp_use_params
  ltp.latAccelFactorFiltered = ltp_factor
  ltp.frictionCoefficientFiltered = ltp_friction
  return cast(messaging.SubMaster, _FakeSubMaster({
    'carState': CS,
    'carControl': CC,
    'controlsState': make_controls_state(saturated, actual_lat_accel),
    'vehicleParameters': vp,
    'lateralTorqueParameters': ltp,
    'modelV2': md if md is not None else make_model(v_ego),
  }))
