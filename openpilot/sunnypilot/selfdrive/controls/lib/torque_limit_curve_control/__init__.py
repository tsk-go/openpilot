"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
# Torque Limit Curve Control (TLCC)
#
# Slows the car before a curve only when the steering system physically cannot
# deliver the lateral acceleration the upcoming path requires. It has no comfort
# constants: the single limit it enforces is the car's own learned lateral
# acceleration ceiling (the point at which the torque controller saturates and
# openpilot raises "Turn Exceeds Steering Limit").
#
# This module is fully independent from Smart Cruise Control (SCC-V / SCC-M).

from openpilot.common.constants import CV

# Do not operate below this speed. Torque saturation is only meaningful at speed
# (matches latcontrol's sat_check_min_speed of 10 m/s with a little headroom to
# keep braking active until we're clearly below any limit).
MIN_V = 5.0  # m/s

# Fraction of the learned ceiling that we plan against. The remaining headroom is
# what the lateral PID needs to actually track the path (error correction +
# friction feedforward) without pinning the actuator.
USABLE_FRACTION = 0.90

# Deceleration profile. We start braking exactly when a constant deceleration of
# A_ENGAGE would be required to reach the curve's speed at the curve. Below that,
# nothing is done. Once engaged we command whatever deceleration is actually
# required (which grows if we are late), capped at A_MAX, which is the most the
# cruise path of the longitudinal planner will deliver (A_CRUISE_MIN = -1.2).
A_ENGAGE = 0.8  # m/s^2
A_RELEASE = 0.3  # m/s^2, hysteresis: release when the required decel drops below this
A_MAX = 1.2  # m/s^2

# Longitudinal response lag: the planner's cruise path ramps to the requested accel
# through a jerk limit and the car's actuators follow after that. Plan against the
# limiting point as if it were this much closer so the speed is reached at the point,
# not shortly after it.
RESPONSE_LAG_T = 0.5  # s

# Minimum distance used in the required-deceleration division. Prevents blow-up
# when the limiting point is (nearly) under the car.
D_MIN = 5.0  # m

# Only trust the *current* road roll for points within this horizon. Roll is only
# ever used to make the limit more conservative, never to relax it.
ROLL_HORIZON_T = 3.0  # s

# Ignore path points with curvature below this (straight road numerical noise).
KAPPA_MIN = 1e-4  # 1/m

MIN_V_KPH = MIN_V * CV.MS_TO_KPH
