"""StarView's automatic blinker in the desire helper: a lane change confirmed on the tablet needs no nudge, once."""

from types import SimpleNamespace

from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_helper import STARVIEW_CONFIRM_MAX_S, STARVIEW_SETTLE_S, DesireHelper
from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy
from openpilot.starpilot.system.starview.blinker_signal import StarViewSignal

LCS = log.LaneChangeState
SETTLE_FRAMES = round(STARVIEW_SETTLE_S / DT_MDL)
CONFIRMED = {"starview_lane": True, "starview_evidence": True}


def car(**changes):
  values = {"vEgo": 30 * CV.MPH_TO_MS, "leftBlinker": False, "rightBlinker": False,
            "steeringPressed": False, "steeringTorque": 0.0, "leftBlindspot": False, "rightBlindspot": False}
  values.update(changes)
  return SimpleNamespace(**values)


def run(helper, state, n=1, active=True, prob=1.0, **kw):
  for _ in range(n):
    helper.update(state, active, prob, engaged=active, **kw)
  return helper.lane_change_state


def test_confirmed_lane_change_starts_without_a_nudge():
  h = DesireHelper()
  left = car(leftBlinker=True)
  assert run(h, left) == LCS.preLaneChange
  assert run(h, left, 30) == LCS.preLaneChange                             # a plain blinker still waits for the nudge
  assert run(h, left, SETTLE_FRAMES - 1, **CONFIRMED) == LCS.preLaneChange  # the lane has to be seen for a moment
  assert run(h, left, 2, **CONFIRMED) == LCS.laneChangeStarting
  assert h.desire == log.Desire.laneChangeLeft


def test_no_adjacent_lane_no_lane_change():
  h = DesireHelper()
  left = car(leftBlinker=True)
  run(h, left)
  assert run(h, left, 40, starview_lane=True, starview_evidence=False) == LCS.preLaneChange


def test_one_confirmation_is_one_lane_change():
  h = DesireHelper(LaneChangePolicy(one_per_signal=False))
  left = car(leftBlinker=True)
  run(h, left)
  assert run(h, left, SETTLE_FRAMES + 1, **CONFIRMED) == LCS.laneChangeStarting
  run(h, left, 20, prob=0.0, **CONFIRMED)                                  # finished: back to waiting
  assert run(h, left, 40, **CONFIRMED) == LCS.preLaneChange                # not a second one on the same hold
  run(h, car(), 2)                                                         # blinker off
  run(h, left)
  assert run(h, left, SETTLE_FRAMES + 1, **CONFIRMED) == LCS.laneChangeStarting


def test_nudge_during_a_confirmation_uses_it_up():
  h = DesireHelper(LaneChangePolicy(one_per_signal=False))
  left = car(leftBlinker=True)
  run(h, left)
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=1.0), starview_lane=True) == LCS.laneChangeStarting
  run(h, left, 20, prob=0.0, **CONFIRMED)
  assert run(h, left, 40, **CONFIRMED) == LCS.preLaneChange


def test_occupied_blind_spot_voids_the_confirmation():
  # review: a one-frame clear of the BSM flag must not start a lane change confirmed while the lane was occupied
  h = DesireHelper()
  occupied = car(rightBlinker=True, rightBlindspot=True)
  run(h, occupied)
  assert run(h, occupied, 100, **CONFIRMED) == LCS.preLaneChange
  assert run(h, car(rightBlinker=True), 40, **CONFIRMED) == LCS.preLaneChange
  assert run(h, car(rightBlinker=True, steeringPressed=True, steeringTorque=-1.0)) == LCS.laneChangeStarting  # a nudge still works


def test_old_confirmation_expires():
  h = DesireHelper()
  left = car(leftBlinker=True)
  run(h, left)
  run(h, left, round(STARVIEW_CONFIRM_MAX_S / DT_MDL) + 2, starview_lane=True, starview_evidence=False)
  assert run(h, left, 40, **CONFIRMED) == LCS.preLaneChange                # the lane showed up too late


def test_confirmation_from_before_engaging_doesnt_count():
  # review: blinker held as "lane" while openpilot wasn't steering, then it engages -> no lane change on its own
  h = DesireHelper()
  left = car(leftBlinker=True)
  run(h, left, 5, active=False, **CONFIRMED)
  run(h, left, **CONFIRMED)
  assert run(h, left, 40, **CONFIRMED) == LCS.preLaneChange


def test_route_turn_signal_is_never_a_lane_change():
  h = DesireHelper()
  left = car(leftBlinker=True)
  assert run(h, left, 3, navigation_turn=True) == LCS.off


def test_signal_file(tmp_path):
  now = [100.0]
  sig = StarViewSignal(str(tmp_path / "starview_signal"), clock=lambda: now[0])
  left = car(leftBlinker=True)
  assert sig.read() == "" and sig.for_blinker(left) == ""
  (tmp_path / "starview_signal").write_text("lane left 100.000")
  assert sig.read() == "lane left" and sig.for_blinker(left) == "lane"
  assert sig.for_blinker(car(rightBlinker=True)) == ""                     # another side's signal
  assert sig.for_blinker(car()) == ""
  now[0] = 101.5                                                           # starviewd stopped renewing it
  assert sig.read() == ""
  tmp = tmp_path / "x"
  tmp.write_text("turn right 101.400")
  tmp.replace(tmp_path / "starview_signal")                                # starviewd's os.replace: new inode
  assert sig.for_blinker(car(rightBlinker=True)) == "turn"
  for junk in ("", "lane", "honk left 101.4", "lane up 101.4", "lane left soon"):
    tmp.write_text(junk)
    tmp.replace(tmp_path / "starview_signal")
    assert sig.read() == "", junk


def test_nudge_strength_from_the_tablet():
  from openpilot.selfdrive.controls.lib.desire_helper import NUDGE_HOLD_S
  hold = round(NUDGE_HOLD_S / DT_MDL)
  left = car(leftBlinker=True)
  # lighter than the car's own threshold (60 of 100): a 70 push held 0.15 s starts it, without steeringPressed
  h = DesireHelper()
  run(h, left)
  push = car(leftBlinker=True, steeringTorque=70.0)
  assert run(h, push, hold - 1, nudge_torque=60.0) == LCS.preLaneChange
  assert run(h, push, 1, nudge_torque=60.0) == LCS.laneChangeStarting
  # a push the wrong way, or a short bump, does nothing
  h = DesireHelper()
  run(h, left)
  assert run(h, car(leftBlinker=True, steeringTorque=-90.0), 10, nudge_torque=60.0) == LCS.preLaneChange
  for _ in range(5):
    run(h, push, hold - 1, nudge_torque=60.0)
    run(h, left, 1, nudge_torque=60.0)
  assert h.lane_change_state == LCS.preLaneChange
  # firmer (130): the car's own steeringPressed at 110 is not enough any more
  h = DesireHelper()
  run(h, left)
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=110.0), 10, nudge_torque=130.0) == LCS.preLaneChange
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=140.0), hold, nudge_torque=130.0) == LCS.laneChangeStarting
  # no setting: the stock rule, one frame of steeringPressed toward that side
  h = DesireHelper()
  run(h, left)
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=110.0)) == LCS.laneChangeStarting
