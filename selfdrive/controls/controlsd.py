#!/usr/bin/env python3
import os
import math

from cereal import car, log
from openpilot.common.conversions import Conversions as CV
from openpilot.common.realtime import DT_CTRL, Ratekeeper, Priority
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.car.car_helpers import get_car, get_startup_event
from openpilot.selfdrive.controls.lib.drive_helpers import VCruiseHelper, clip_curvature
from openpilot.selfdrive.controls.lib.events import Events
from openpilot.selfdrive.controls.lib.latcontrol import LatControl, MIN_LATERAL_CONTROL_SPEED
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.controls.lib.vehicle_model import VehicleModel
from openpilot.selfdrive.sunnypilot.live_torque_params import LiveTorqueParams

import cereal.messaging as messaging

ThermalStatus = log.DeviceState.ThermalStatus
LongitudinalPlanSource = log.LongitudinalPlan.LongitudinalPlanSource


def controls_thread(sm=None, pm=None, can_sock=None):
  CP = sm["carParams"]

  # Ensure carParams are within a valid range
  if CP.mass < 1 or CP.rotationalInertia < 1 or CP.wheelbase < 1 or CP.centerToFront < 1:
    cloudlog.error(f"Invalid carParams {CP.carName}: {CP.to_dict()}")

  # Set priority to max
  os.system(f"chrt -f -p {Priority.CTRL_HIGH} {os.getpid()}")

  params = Params()
  params_memory = Params("/dev/shm/params")
  with car.CarParams.from_bytes(params.get("CarParamsPersistent", block=True)) as p:
    CP_SP = p.as_reader()

  # Read car specific parameters from a file
  params_file = os.path.expanduser("~/params.json")
  if os.path.isfile(params_file):
    with open(params_file, "r") as f:
      params_json = json.load(f)
      if "CarParams" in params_json:
        CP.override_from_dict(params_json["CarParams"])

  # Standstill events
  events = Events()

  # Initalize car interface
  CI = get_car(can_sock, pm, CP)
  CI.init(CP, can_sock, pm)

  # TODO: move this to sync from CI
  if sm["liveParameters"].valid:
    CP.torqueRampMin = sm["liveParameters"].torqueRampMin
    CP.torqueRampMax = sm["liveParameters"].torqueRampMax

  # Initialize controls
  # We need to use the car specific params to initialize the lateral controller
  LaC = LatControl(CP, CP_SP, CI)
  LoC = LongControl(CP, CI)
  VM = VehicleModel(CP)
  VC = VCruiseHelper(CP)

  sm["liveParameters"].steerRatio = CP.steerRatio
  sm["liveParameters"].stiffnessFactor = CP.stiffnessFactor

  # live torque params
  live_torque_params = LiveTorqueParams(CP)

  rk = Ratekeeper(100, print_delay_threshold=None)
  while True:
    sm.update(0)

    if not sm.updated["controlsState"]:
      continue

    # Get latest carState
    CS = sm["carState"]
    # Get latest modelV2
    model_v2 = sm["modelV2"]
    # Get latest longitudinalPlan
    long_plan = sm["longitudinalPlan"]

    # Get latest carControl
    CC = car.CarControl.new_message()

    # Check for events, standstill, and brake hold
    events.update(CS, sm["driverMonitoringState"], sm["events"], sm["standstill"], sm["roadLimitSpeed"])

    # Update VehicleModel
    VM.update(CS, model_v2)

    # Update Longitudinal Controller
    LoC.update(CS, sm["controlsState"], VC, long_plan, model_v2, events)

    # Update Lateral Controller
    LaC.update(CS, sm["controlsState"], VC, long_plan, model_v2, events, live_torque_params)

    # Get desired curvature and lateral acceleration
    desired_curvature, desired_lateral_accel = LaC.get_desired_curvature_and_lateral_accel(CS, model_v2, long_plan)

    # Send car controls
    CC.latActive = LaC.active and not CS.steerFaultTemporary and CS.vEgo > MIN_LATERAL_CONTROL_SPEED
    CC.longActive = LoC.active and not CS.brakePressed and not CS.gasPressed

    # Steer
    # ADDED: model_v2 and long_plan to the LaC.update call (Vision-Only)
    CC.actuators.steer, CC.actuators.steeringAngleDeg, lac_log = LaC.update(CC.latActive, CS, VM, sm["liveParameters"],
                                                                              sm["liveTorqueParameters"], desired_curvature,
                                                                              model_v2, long_plan)

    # Gas and brake
    CC.actuators.gas, CC.actuators.brake = LoC.update(CC.longActive, CS, sm["controlsState"], VC, long_plan, model_v2, events)

    # Send actuators
    CC.actuators.accel = LoC.actuators.accel
    CC.actuators.curvature = desired_curvature

    # Send car controls
    pm.send("carControl", CC)

    # Log
    log_data = {
      "lac_log": lac_log,
      "loc_log": LoC.get_log(),
      "events": events.to_msg(),
      "model_v2": model_v2,
      "long_plan": long_plan,
      "live_torque_params": live_torque_params.get_log(),
    }
    pm.send("controlsState", log_data)

    rk.keep_time()


def main(sm=None, pm=None, can_sock=None):
  # ADDED: 'modelV2' and 'longitudinalPlan' to the SubMaster list
  sm = messaging.SubMaster(['carState', 'controlsState', 'driverMonitoringState', 'events', 'liveParameters',
                            'liveTorqueParameters', 'modelV2', 'longitudinalPlan', 'roadLimitSpeed', 'standstill'])
  pm = messaging.PubMaster(['carControl', 'controlsState'])
  controls_thread(sm, pm, can_sock)


if __name__ == "__main__":
  main()
