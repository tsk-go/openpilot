"""StarView's tablet in lane changes and turns (starview/lanes.py): a lane change confirmed on the tablet needs no
nudge, once; the route's exit from our lane is a signal only; the tablet's street map has a say in Turn Signal Guidance;
the tablet's nudge strength. Moved here from selfdrive/controls/tests/test_starview_signal.py and the end of
navigation/tests/test_intent.py (Nov 24) so upstream's files carry only the hooks."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from openpilot.cereal import log
from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy
from openpilot.starpilot.system.starview import blinker_turn
from openpilot.starpilot.system.starview.blinker_signal import StarViewSignal
from openpilot.starpilot.system.starview.lanes import CONFIRM_MAX_S, NUDGE_HOLD_S, SETTLE_S, LaneInputs, StarViewLanes

LCS = log.LaneChangeState
SETTLE_FRAMES = round(SETTLE_S / DT_MDL)
CONFIRMED = {"why": "lane", "evidence": True}
NOW = 20_000_000_000
OPENPILOT = Path(__file__).resolve().parents[4]


def car(**changes):
  values = {"vEgo": 30 * CV.MPH_TO_MS, "leftBlinker": False, "rightBlinker": False,
            "steeringPressed": False, "steeringTorque": 0.0, "leftBlindspot": False, "rightBlindspot": False}
  values.update(changes)
  return NS(**values)


def run(helper, state, n=1, active=True, prob=1.0, why=None, evidence=False, nudge_torque=None, **kw):
  """n frames of DesireHelper.update with what modeld's StarViewLanes would have set for them."""
  for _ in range(n):
    helper.starview.why, helper.starview.evidence, helper.starview.nudge_torque = why, evidence, nudge_torque
    helper.update(state, active, prob, engaged=active, **kw)
  return helper.lane_change_state


# ---- the desire helper (fork patches 2, 10, 80)

def test_without_the_tablet_nothing_changes():
  h = DesireHelper()
  assert type(h.starview) is LaneInputs
  left = car(leftBlinker=True)
  assert run(h, left, 40) == LCS.preLaneChange
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=1.0)) == LCS.laneChangeStarting


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
  assert run(h, left, 40, why="lane", evidence=False) == LCS.preLaneChange


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
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=1.0), why="lane") == LCS.laneChangeStarting
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
  run(h, left, round(CONFIRM_MAX_S / DT_MDL) + 2, why="lane", evidence=False)
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


def test_lane_and_exit_are_never_a_turn():
  # "lane" / "exit": upstream's forecast turn and the route's turn don't take the blinker away from the lane change
  for why in ("lane", "exit"):
    h = DesireHelper()
    assert run(h, car(leftBlinker=True), 3, why=why, navigation_turn=True) == LCS.preLaneChange


def test_tablet_turn_is_a_route_turn_with_automatic_turn_initiation():
  # Nov 22 sync: upstream made automatic turns their own switch (Galaxy's Automatic Turn Initiation, off by default);
  # the owner chose that the tablet's "turn" (its blinker at the route's turn) follows it too. Nov 24 sync: upstream's
  # route turns wait for the lane at speed (a lane change toward the turn may start) - the tablet's "turn" is one
  for automatic in (False, True):
    lanes = StarViewLanes("toyota", NS(automatic_turn_enabled=automatic))
    lanes.why = "turn"
    assert lanes.begin(DesireHelper(), car(leftBlinker=True), True, True, False, False) == (False, automatic)
    assert lanes.begin(DesireHelper(), car(leftBlinker=True), True, True, True, True) == (True, True)


def test_a_route_turn_waits_for_the_lane_and_a_forecast_turn_alone_does_not():
  h = DesireHelper()
  assert run(h, car(leftBlinker=True), 3, navigation_turn=True, route_turn=True) == LCS.preLaneChange
  assert run(h, car(leftBlinker=True, steeringPressed=True, steeringTorque=1.0), navigation_turn=True,
             route_turn=True) == LCS.laneChangeStarting
  for why in ("lane", "exit"):
    lanes = StarViewLanes("toyota", NS(automatic_turn_enabled=True))
    lanes.why = why
    assert lanes.begin(DesireHelper(), car(leftBlinker=True), True, True, True, True) == (False, False)


def test_exit_signal_is_a_signal_only():
  # fork patch 80: the route's exit taken from our own lane - the tablet signals before the ramp opens beside us. Even
  # with automatic lane changes on and a lane seen there (a wide shoulder), nothing starts until the tablet says "lane"
  # at the opening; the driver's own nudge still does
  auto = LaneChangePolicy(auto_lane_change=True, auto_delay_s=0.5)
  right = car(rightBlinker=True)
  h = DesireHelper(auto)
  run(h, right)
  assert run(h, right, 100, auto_evidence=True, why="exit") == LCS.preLaneChange
  assert h.pre_lane_change_timer == 0.0
  assert run(h, right, SETTLE_FRAMES - 1, **CONFIRMED) == LCS.preLaneChange
  assert run(h, right, 2, **CONFIRMED) == LCS.laneChangeStarting
  assert h.desire == log.Desire.laneChangeRight
  # the same held blinker without the hold: the automatic lane change starts by itself (as before)
  h = DesireHelper(auto)
  run(h, right)
  assert run(h, right, round(0.5 / DT_MDL) + 2, auto_evidence=True) == LCS.laneChangeStarting
  # a nudge during the hold: the driver decides
  h = DesireHelper(auto)
  run(h, right)
  run(h, right, 10, auto_evidence=True, why="exit")
  assert run(h, car(rightBlinker=True, steeringPressed=True, steeringTorque=-1.0), auto_evidence=True,
             why="exit") == LCS.laneChangeStarting


def test_nudge_strength_from_the_tablet():
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


def test_a_push_held_before_the_blinker_starts_over():
  # the nudge time restarts with every new wait for a lane change (it used to be zeroed where preLaneChange begins)
  hold = round(NUDGE_HOLD_S / DT_MDL)
  h = DesireHelper()
  run(h, car(leftBlinker=True))
  run(h, car(leftBlinker=True, steeringTorque=70.0), hold - 1, nudge_torque=60.0)
  run(h, car(), 2, nudge_torque=60.0)                                      # blinker off: back to off
  run(h, car(leftBlinker=True), nudge_torque=60.0)
  assert run(h, car(leftBlinker=True, steeringTorque=70.0), hold - 1, nudge_torque=60.0) == LCS.preLaneChange


# ---- the tablet's files

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
  tmp.write_text("exit right 101.400")
  tmp.replace(tmp_path / "starview_signal")
  assert sig.for_blinker(car(rightBlinker=True)) == "exit"
  for junk in ("", "lane", "honk left 101.4", "lane up 101.4", "lane left soon"):
    tmp.write_text(junk)
    tmp.replace(tmp_path / "starview_signal")
    assert sig.read() == "", junk


def test_tablet_turn_file(tmp_path):
  path = str(tmp_path / "turn")
  clock = [100.0]
  reader = blinker_turn.BlinkerTurn(path, clock=lambda: clock[0])
  right, left = NS(leftBlinker=False, rightBlinker=True), NS(leftBlinker=True, rightBlinker=False)
  assert reader.for_blinker(right) is None                     # no say
  blinker_turn.write("right", path, clock=lambda: clock[0])
  assert reader.for_blinker(right) == "turn"
  assert reader.for_blinker(left) == "no"
  blinker_turn.write("none", path, clock=lambda: clock[0])
  assert reader.for_blinker(right) == "no"
  assert reader.for_blinker(NS(leftBlinker=False, rightBlinker=False)) is None
  clock[0] += 2.0                                              # the tablet stopped saying: no say
  assert reader.for_blinker(right) is None
  blinker_turn.write(None, path)
  assert reader.read() == ""
  with pytest.raises(ValueError):
    blinker_turn.write("straight", path)


# ---- Turn Signal Guidance (fork patch 38: StarView's street map has a say)

def _guided(on=True):
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  owner.guidance = NS(sample=lambda *a, **k: on)   # Automatic Turn Initiation (upstream's own switch since Nov 20)
  owner.steering_capable = True
  sm = {'carState': NS(canValid=True, canTimeout=False, gearShifter='drive', vEgo=5., standstill=False,
                       leftBlinker=True, rightBlinker=False, leftBlindspot=False, rightBlindspot=False),
        'carControl': NS(latActive=True), 'deviceState': NS(started=True, startedMonoTime=1),
        'longitudinalPlan': NS(shouldStop=False, modelMonoTime=NOW)}
  class SM(dict):
    valid = dict.fromkeys(sm, True)
    alive = dict(valid)
    logMonoTime = dict.fromkeys(sm, NOW)
  return owner, SM(sm)


@pytest.mark.parametrize('no_turn,expected', [(None, log.Desire.turnLeft), (False, log.Desire.turnLeft), (True, log.Desire.none)])
def test_tablet_map_says_whether_the_blinker_is_a_turn(no_turn, expected):
  owner, sm = _guided()
  if no_turn is not None:
    owner.starview_no_turn = no_turn
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False) == expected


def test_guidance_off_means_no_turn_whatever_the_tablet_says():
  owner, sm = _guided(on=False)
  owner.starview_no_turn = False
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False) == log.Desire.none


def test_before_turn_reads_the_tablet(tmp_path):
  clock = [100.0]
  owner = NS(automatic_turn_enabled=True)
  lanes = StarViewLanes("toyota", owner)
  lanes.signal = StarViewSignal(str(tmp_path / "signal"), clock=lambda: clock[0])
  lanes.street = blinker_turn.BlinkerTurn(str(tmp_path / "turn"), clock=lambda: clock[0])
  sm = {'carState': car(leftBlinker=True)}
  lanes.before_turn(sm)
  assert lanes.why == "" and owner.starview_no_turn is False               # no say: upstream as it is
  blinker_turn.write("left", str(tmp_path / "turn"), clock=lambda: clock[0])
  lanes.before_turn(sm)
  assert owner.starview_no_turn is False
  blinker_turn.write("none", str(tmp_path / "turn"), clock=lambda: clock[0])
  lanes.before_turn(sm)
  assert owner.starview_no_turn is True                                    # no street there: pulling over
  blinker_turn.write("left", str(tmp_path / "turn"), clock=lambda: clock[0])
  for why in ("lane", "exit"):
    (tmp_path / "signal").write_text(f"{why} left 100.000")
    lanes.before_turn(sm)
    assert lanes.why == why and owner.starview_no_turn is True             # the tablet's lane change, never a turn
    assert lanes.after_turn(log.Desire.turnLeft, NS(desire=log.Desire.laneChangeLeft)) == log.Desire.laneChangeLeft
  (tmp_path / "signal").write_text("turn left 100.000")
  lanes.before_turn(sm)
  assert owner.starview_no_turn is False
  assert lanes.after_turn(log.Desire.turnLeft, NS(desire=log.Desire.none)) == log.Desire.turnLeft


# ---- the hooks in upstream's files

def _calls(path, fn=None):
  """Source text of every call in `path` (in `fn` only, if given), in file order."""
  tree = ast.parse((OPENPILOT / path).read_text())
  if fn is not None:
    tree = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == fn)
  calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
  return [ast.unparse(node) for node in sorted(calls, key=lambda node: (node.lineno, node.col_offset))]


def _index(calls, start):
  return next(i for i, call in enumerate(calls) if call.startswith(start))


def test_modeld_calls_the_hooks_in_order():
  calls = _calls("selfdrive/modeld/modeld.py", "main")
  assert any(call.startswith("StarViewLanes(CP.brand, navigation_turn)") for call in calls)
  src = (OPENPILOT / "selfdrive/modeld/modeld.py").read_text()
  assert "starview = DH.starview = StarViewLanes(CP.brand, navigation_turn)" in src
  assert _index(calls, "starview.before_turn(sm)") < _index(calls, "navigation_turn.select(") < \
         _index(calls, "starview.after_turn(desire, DH)")
  assert _index(calls, "navigation_turn.signal_model.observe(") < _index(calls, "starview.before_lane_change(") < \
         _index(calls, "DH.update(")


def test_desire_helper_calls_the_hooks():
  calls = _calls("selfdrive/controls/lib/desire_helper.py", "update")
  assert calls[0] == "self.starview.begin(self, carstate, lateral_active, engaged, navigation_turn, route_turn)"
  assert any(call.startswith("self.starview.pre_lane_change(self, carstate, blindspot_detected, torque_applied, auto_ready")
             for call in calls)
