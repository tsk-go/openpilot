"""When the nav model gets the route: only for the next turn within the horizon, never during a driver's lane change."""
import json
import math

import numpy as np
import pytest

from cereal import log
from openpilot.starpilot.navigation.nav_model.helpers import (DEFAULT_NAV_HORIZON_M, DRIVER_LANE_CHANGE_TAIL_S, DriverLaneChange,
                                                              VALHALLA_COMMAND_COUNT, gate_nav_inputs, nav_horizon_m, next_turn_distance,
                                                              write_gate_status)

LCS = log.LaneChangeState


def nav(command, distance_m):
  v = np.zeros(VALHALLA_COMMAND_COUNT + 1, dtype=np.float32)
  if command is not None:
    v[command], v[-1] = 1, distance_m / 100
  return v


def inputs(command=20, distance_m=500.0):
  return {"nav_map": np.ones((256, 256), dtype=np.uint8), "navigation": nav(command, distance_m)}


def test_turn_within_horizon_gets_the_route():
  given, why = gate_nav_inputs(inputs(20, 1500.0), 2000.0, False)
  assert why == "" and set(given) == {"nav_map", "navigation"}


def test_far_turn_gets_nothing_like_no_destination():
  # 00000a2d 13:08: "exit right in 16.7 km" while the model moved three lanes left
  given, why = gate_nav_inputs(inputs(20, 16714.0), 2000.0, False)
  assert given == {} and why == "next turn beyond 2000 m"


def test_no_turn_ahead_gets_nothing():
  given, why = gate_nav_inputs(inputs(None, 0.0), 2000.0, False)
  assert given == {} and why == "no turn ahead"


def test_horizon_off_always_gives_the_route():
  given, why = gate_nav_inputs(inputs(20, 16714.0), math.inf, False)
  assert why == "" and "navigation" in given


def test_driver_lane_change_gets_nothing_even_for_a_near_turn():
  given, why = gate_nav_inputs(inputs(20, 500.0), 2000.0, True)
  assert given == {} and why == "driver lane change"


def test_no_destination_stays_empty():
  assert gate_nav_inputs({}, 2000.0, True) == ({}, "")


def test_driver_lane_change_holds_through_the_tail():
  d = DriverLaneChange()
  assert not d.update(LCS.preLaneChange, False, 10.0)        # blinker on, waiting for the nudge: route still given
  assert d.update(LCS.laneChangeStarting, False, 11.0)
  assert d.update(LCS.laneChangeFinishing, False, 14.0)
  assert d.update(LCS.off, False, 14.0 + DRIVER_LANE_CHANGE_TAIL_S - 0.1)
  assert not d.update(LCS.off, False, 14.0 + DRIVER_LANE_CHANGE_TAIL_S + 0.1)


def test_system_lane_change_keeps_the_route():
  # reserved for an automatic blinker that follows the model's own forecast
  assert not DriverLaneChange().update(LCS.laneChangeStarting, True, 5.0)


def test_horizon_file(tmp_path):
  f = tmp_path / "h"
  assert nav_horizon_m(f) == DEFAULT_NAV_HORIZON_M            # missing
  for text, expected in (("3000\n", 3000.0), ("0", math.inf), ("junk", DEFAULT_NAV_HORIZON_M), ("-5", DEFAULT_NAV_HORIZON_M)):
    f.write_text(text)   # "0" = always give the route
    assert nav_horizon_m(f) == expected


def test_next_turn_distance():
  assert next_turn_distance(nav(20, 1234.0)) == pytest.approx(1234.0, abs=0.01)   # float32 input
  assert next_turn_distance(nav(None, 0.0)) is None and next_turn_distance(None) is None


def test_gate_status_file(tmp_path):
  f = tmp_path / "gate.json"
  write_gate_status("next turn beyond 2000 m", nav(20, 16714.0), f)
  s = json.loads(f.read_text())
  assert s["routeGiven"] is False and s["nextTurnType"] == 20 and s["nextTurnM"] == 16714
