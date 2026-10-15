"""StarView's automatic blinker (/dev/shm/starview_signal, written by starviewd's PicoBlinker): a route turn signal never
starts a lane change, and a lane change the driver confirmed on the tablet (tap / steering nudge) needs no further nudge."""
import os
from time import monotonic

import pytest

from cereal import log

from openpilot.selfdrive.controls.lib import desire_helper
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper, LaneChangeState
from openpilot.selfdrive.controls.tests.test_navigation_desires import make_car_state, make_plan, make_toggles


@pytest.fixture
def signal(tmp_path, monkeypatch):
  path = tmp_path / "starview_signal"
  monkeypatch.setattr(desire_helper, "STARVIEW_SIGNAL_PATH", str(path))

  def write(text, age=0.0):                    # like starviewd: a new file replaces the old one
    tmp = tmp_path / "starview_signal.tmp"
    tmp.write_text(f"{text} {monotonic() - age:.3f}")
    os.replace(tmp, path)
  return write


def helper():
  h = DesireHelper()
  h._update_nav_params = lambda: None          # no route
  return h


def step(h, n=1, toggles=None, plan=None, **cs):
  for _ in range(n):
    h.update(make_car_state(**cs), True, 1.0, plan or make_plan(), toggles or make_toggles(nudgeless=False))


def test_confirmed_lane_change_starts_without_a_nudge(signal):
  signal("lane left")
  h = helper()
  step(h, 2, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.laneChangeStarting
  assert h.lane_change_by_system


def test_nudge_mode_still_waits_without_confirmation():
  h = helper()
  step(h, 10, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange
  assert not h.lane_change_by_system


def test_stale_or_wrong_side_confirmation_is_ignored(signal):
  h = helper()
  signal("lane left", age=2.0)                 # starviewd gone
  step(h, 4, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange
  signal("lane right")                         # the other side
  step(h, 4, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange


def test_confirmed_but_lane_too_narrow_waits(signal):
  signal("lane right")
  h = helper()
  step(h, 4, plan=make_plan(laneWidthRight=2.0), rightBlinker=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange


def test_blind_spot_still_blocks_a_confirmed_change(signal):
  signal("lane left")
  h = helper()
  step(h, 4, leftBlinker=True, leftBlindspot=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange


def test_turn_signal_never_starts_a_lane_change(signal):
  signal("turn right")
  h = helper()
  step(h, 20, toggles=make_toggles(nudgeless=True), vEgo=15.0, rightBlinker=True)
  assert h.lane_change_state == LaneChangeState.off


def test_turn_signal_cancels_a_pending_lane_change(signal):
  h = helper()
  step(h, 2, toggles=make_toggles(nudgeless=False), vEgo=15.0, rightBlinker=True)
  assert h.lane_change_state == LaneChangeState.preLaneChange
  signal("turn right")
  step(h, 1, toggles=make_toggles(nudgeless=False), vEgo=15.0, rightBlinker=True)
  assert h.lane_change_state == LaneChangeState.off


def test_by_system_resets_after_the_lane_change(signal):
  signal("lane left")
  h = helper()
  step(h, 2, leftBlinker=True)
  assert h.lane_change_by_system
  h.lane_change_state = LaneChangeState.laneChangeFinishing
  h.lane_change_ll_prob = 1.0
  step(h, 1)                                   # blinker off: back to off
  assert h.lane_change_state == LaneChangeState.off and not h.lane_change_by_system


def test_one_confirmation_is_one_lane_change(signal):
  signal("lane left")
  h = helper()
  step(h, 2, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.laneChangeStarting
  h.lane_change_state = LaneChangeState.laneChangeFinishing
  h.lane_change_ll_prob = 1.0
  step(h, 1, leftBlinker=True)                 # done, the blinker (and the file) still on: back to pre, not a second change
  step(h, 10, leftBlinker=True)
  assert h.lane_change_state in (LaneChangeState.off, LaneChangeState.preLaneChange)
  assert h.lane_change_state != LaneChangeState.laneChangeStarting


def test_a_confirmed_lane_change_beats_a_same_side_route_turn(signal):
  signal("lane left")
  h = helper()
  h._nav_instruction_state = {"valid": True, "maneuverType": "turn", "maneuverModifier": "left",
                              "maneuverDistance": 200.0, "updatedAtMonotonic": monotonic()}
  step(h, 2, vEgo=20.0, leftBlinker=True)
  assert h.lane_change_state == LaneChangeState.laneChangeStarting


def test_slow_lane_hold_is_no_turn(signal):
  signal("lane left")
  h = helper()
  step(h, 3, toggles=make_toggles(nudgeless=False, use_turn_desires=True), vEgo=5.0, leftBlinker=True)
  assert h.desire == log.Desire.none


def test_turn_signal_turn_desire_only_near_the_turn(signal):
  signal("turn right")
  h = helper()
  nav = {"valid": True, "maneuverType": "turn", "maneuverModifier": "right", "maneuverDistance": 150.0, "updatedAtMonotonic": monotonic()}
  h._nav_instruction_state = nav
  toggles = make_toggles(use_turn_desires=True, nav_desires_allowed=False)
  step(h, 3, toggles=toggles, vEgo=6.0, rightBlinker=True)
  assert h.desire == log.Desire.none           # 150 m out at 6 m/s: not yet
  nav["maneuverDistance"] = 30.0
  nav["updatedAtMonotonic"] = monotonic()
  step(h, 1, toggles=toggles, vEgo=6.0, rightBlinker=True)
  assert h.desire == log.Desire.turnRight
