from openpilot.starpilot.navigation.wire import navigation_envelope
from types import SimpleNamespace as NS

import pytest

from openpilot.cereal import messaging, log
from openpilot.common.constants import CV
from openpilot.starpilot.navigation.intent import current_instruction, turn_desire, cruise_ceiling, turn_speed


NOW = 20_000_000_000


@pytest.fixture
def sm():
  class SM(dict):
    valid = dict.fromkeys(('starpilotNavigation', 'deviceState', 'carState', 'carControl'), True)
    alive = dict(valid)
    logMonoTime = dict.fromkeys(valid, NOW)
  instruction = NS(maneuverType='turn', maneuverModifier='right', distanceMeters=30.)
  nav = NS(enabled=True, controlValid=True, status='guiding', sessionId='producer', revision='one', frameMonoTime=NOW,
           startedMonoTime=10_000_000_000, locationMonoTime=NOW, instruction=instruction, nextManeuver=instruction)
  nav.version = 2
  return SM(starpilotNavigation=NS(navigation=nav), deviceState=NS(started=True, startedMonoTime=10_000_000_000),
            carState=NS(canValid=True, canTimeout=False, gearShifter='drive', vEgo=5., standstill=False, leftBlinker=False,
                        rightBlinker=True, leftBlindspot=False, rightBlindspot=False, gasPressed=False, brakePressed=False),
            carControl=NS(latActive=True, longActive=True))


def test_signal_turn_and_existing_desire_preserved(sm):
  assert turn_desire(sm, NOW, log.Desire.none, supported=True) == log.Desire.turnRight
  assert turn_desire(sm, NOW, log.Desire.laneChangeLeft, supported=True) == log.Desire.laneChangeLeft
  assert turn_desire(sm, NOW, log.Desire.none, supported=False) == log.Desire.none
  sm['carState'].rightBlinker = False
  assert turn_desire(sm, NOW, log.Desire.none, supported=True) == log.Desire.none


@pytest.mark.parametrize('field,value', [('standstill', True), ('rightBlindspot', True), ('leftBlinker', True),
                                        ('vEgo', 14.), ('gearShifter', 'reverse'), ('canValid', False), ('canTimeout', True)])
def test_no_turn_without_vehicle_admission(sm, field, value):
  setattr(sm['carState'], field, value)
  assert turn_desire(sm, NOW, log.Desire.none, supported=True) == log.Desire.none


@pytest.mark.parametrize('field,value', [('controlValid', False), ('enabled', False), ('frameMonoTime', NOW-3_000_000_000),
                                        ('locationMonoTime', NOW+1), ('startedMonoTime', 1), ('sessionId', '')])
def test_stale_previous_drive_and_disabled_nav_are_inert(sm, field, value):
  setattr(sm['starpilotNavigation'].navigation, field, value)
  assert current_instruction(sm, NOW) is None


def test_original_turn_ceiling_and_override(sm):
  cp = NS(openpilotLongitudinalControl=True, passive=False, dashcamOnly=False, minSteerSpeed=0.)
  expected = ((14 * CV.MPH_TO_MS) ** 2 + 2 * .45 * (30 - 8)) ** .5
  assert cruise_ceiling(sm, cp, NOW, 20.) == pytest.approx(expected)
  sm['carState'].gasPressed = True
  assert cruise_ceiling(sm, cp, NOW, 20.) is None
  sm['carState'].gasPressed = False
  cp.openpilotLongitudinalControl = False
  assert cruise_ceiling(sm, cp, NOW, 20.) is None


@pytest.mark.parametrize('kind,modifier,mph', [('turn', 'left', 14), ('turn', 'sharpRight', 10), ('turn', 'uturn', 5),
                                             ('roundabout', 'right', 12), ('fork', 'right', None)])
def test_turn_target_matches_dom_table(kind, modifier, mph):
  result = turn_speed(NS(maneuverType=kind, maneuverModifier=modifier, distanceMeters=8.), 0.)
  assert result == pytest.approx(mph * CV.MPH_TO_MS) if mph is not None else result is None


def test_new_event_roundtrip_keeps_route_and_control_evidence():
  message = messaging.new_message('starpilotNavigation')
  message.starpilotNavigation = navigation_envelope({'sessionId': 'owner', 'frameMonoTime': NOW, 'startedMonoTime': 10_000_000_000,
                                    'enabled': True, 'revision': 'one', 'controlValid': True, 'status': 'guiding',
                                    'instruction': {'text': 'Turn right', 'maneuverType': 'turn', 'maneuverModifier': 'right', 'distanceMeters': 30.},
                                    'route': [{'latitude': 1., 'longitude': 2.}], 'locationMonoTime': NOW})
  with log.Event.from_bytes(message.to_bytes()) as received:
    assert received.which() == 'starpilotNavigation'
    assert received.starpilotNavigation.navigation.route[0].latitude == 1.
    assert received.starpilotNavigation.navigation.controlValid


def test_native_planner_navigation_cap_and_default_equivalence():
  import numpy as np
  from unittest.mock import patch
  from opendbc.car.hyundai.interface import CarInterface
  from opendbc.car.hyundai.values import CAR
  from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
  from openpilot.starpilot.longitudinal.tests.test_conditional_handoff import Frame, NOW as FRAME_NOW, DRIVE

  cp = CarInterface.get_non_essential_params(CAR.HYUNDAI_IONIQ_6)
  cp.openpilotLongitudinalControl = True
  baseline, absent, guided = (LongitudinalPlanner(cp, init_v=20.) for _ in range(3))
  changed = False
  for tick in range(40):
    frame = Frame()
    now = FRAME_NOW + tick * 50_000_000
    frame['carState'].vEgo = 20.
    frame['carState'].gearShifter = 'drive'
    frame.logMonoTime = dict.fromkeys(frame, now)
    with patch('openpilot.selfdrive.controls.lib.longitudinal_planner.navigation_ceiling', return_value=None):
      baseline.update(frame, now_ns=now)
    absent.update(frame, now_ns=now)
    assert baseline.output_a_target == absent.output_a_target
    np.testing.assert_array_equal(baseline.mpc.params, absent.mpc.params)
    nav = messaging.new_message('starpilotNavigation')
    nav.starpilotNavigation = navigation_envelope({'enabled': True, 'controlValid': True, 'status': 'guiding', 'sessionId': 'test',
                              'revision': 'one', 'frameMonoTime': now, 'startedMonoTime': DRIVE, 'locationMonoTime': now,
                              'instruction': {'maneuverType': 'turn', 'maneuverModifier': 'right', 'distanceMeters': 20.}})
    frame['starpilotNavigation'] = nav.starpilotNavigation
    frame.logMonoTime['starpilotNavigation'] = now
    frame.valid['starpilotNavigation'] = frame.alive['starpilotNavigation'] = True
    guided.update(frame, now_ns=now)
    assert guided.output_a_target <= baseline.output_a_target
    changed |= guided.output_a_target < baseline.output_a_target
  assert changed


def test_turn_stop_hold_reuses_planner_stop_until_standstill(sm):
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  sm['longitudinalPlan'] = NS(modelMonoTime=NOW, shouldStop=False)
  sm.logMonoTime['longitudinalPlan'] = NOW
  sm.valid['longitudinalPlan'] = sm.alive['longitudinalPlan'] = True
  def sample(model_stop=False):
    return owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=model_stop)
  assert sample() == log.Desire.turnRight
  sm['longitudinalPlan'].shouldStop = True
  assert sample() == log.Desire.none
  sm['longitudinalPlan'].shouldStop = False
  sm['starpilotNavigation'].navigation.revision = 'favorite-added'
  assert sample() == log.Desire.none
  sm['carState'].standstill = True
  assert sample() == log.Desire.none
  sm['carState'].standstill = False
  assert sample() == log.Desire.turnRight
  assert sample(model_stop=True) == log.Desire.none
  sm.valid['longitudinalPlan'] = False
  assert sample() == log.Desire.none


def test_approaching_turn_does_not_start_or_replace_lane_change(sm):
  from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
  from openpilot.starpilot.navigation.intent import matching_turn_signal
  from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy
  cs = sm['carState']
  cs.steeringPressed, cs.steeringTorque = True, -1.
  helper = DesireHelper(LaneChangePolicy(minimum_speed_mps=0.))
  turn = matching_turn_signal(sm, NOW, supported=True)
  assert turn
  helper.update(cs, True, 1., navigation_turn=turn)
  assert helper.lane_change_state == log.LaneChangeState.off
  helper.lane_change_state = log.LaneChangeState.preLaneChange
  helper.update(cs, True, 1., navigation_turn=turn)
  assert helper.lane_change_state == log.LaneChangeState.off
  helper.lane_change_state = log.LaneChangeState.laneChangeStarting
  helper.lane_change_direction = log.LaneChangeDirection.right
  helper.update(cs, True, 1., navigation_turn=turn)
  assert helper.lane_change_state == log.LaneChangeState.laneChangeStarting
  assert helper.desire == log.Desire.laneChangeRight


def _at(sm, now):
  """The fixture's messages, all fresh at now."""
  for k in sm.logMonoTime:
    sm.logMonoTime[k] = now
  nav = sm['starpilotNavigation'].navigation
  nav.frameMonoTime = nav.locationMonoTime = now
  if 'longitudinalPlan' in sm:
    sm['longitudinalPlan'].modelMonoTime = now


def _plan(sm):
  sm['longitudinalPlan'] = NS(modelMonoTime=NOW, shouldStop=False)
  sm.logMonoTime['longitudinalPlan'] = NOW
  sm.valid['longitudinalPlan'] = sm.alive['longitudinalPlan'] = True


def test_turn_pulse_sent_again_while_still_wanted(sm):
  # fork fix (patch 36): the model remembers a desire pulse ~6.6 s; while the turn is still wanted it is pulsed again
  from openpilot.starpilot.navigation.intent import TurnIntent, REPULSE_S
  owner = TurnIntent()
  _plan(sm)
  out = []
  for k in range(int(12 / 0.05)):
    now = NOW + int(k * 0.05e9)
    _at(sm, now)
    out.append(owner.select(sm, now, log.Desire.none, supported=True, model_stop=False))
  gaps = [k for k in range(1, len(out)) if out[k] == log.Desire.none]
  assert len(gaps) == 2                                     # at 5 s and 10 s: one frame each
  assert abs(gaps[0] * 0.05 - REPULSE_S) < 0.06 and out[gaps[0] + 1] == log.Desire.turnRight
  assert out[0] == log.Desire.turnRight


def test_long_stop_then_stop_request_at_pull_away_does_not_lose_the_turn(sm):
  # approaching the light: the planner stops for it (latch), the car stands, pulls away while a stop is still asked for
  # a moment - before patch 36 the turn stayed blocked until the next standstill
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  _plan(sm)
  t = [NOW]
  def step(dt=0.05, model_stop=False):
    t[0] += int(dt * 1e9)
    _at(sm, t[0])
    return owner.select(sm, t[0], log.Desire.none, supported=True, model_stop=model_stop)
  assert step() == log.Desire.turnRight
  sm['longitudinalPlan'].shouldStop = True
  assert step() == log.Desire.none                          # braking for the light: latched (upstream behaviour)
  sm['carState'].standstill, sm['carState'].vEgo = True, 0.
  for _ in range(int(40 / 0.05)):                           # a 40 s red light
    assert step() == log.Desire.none
  sm['carState'].standstill, sm['carState'].vEgo = False, 1.
  assert step(model_stop=True) == log.Desire.none           # pulling away, the model still says stop for a moment
  sm['longitudinalPlan'].shouldStop = False
  assert step() == log.Desire.none
  outs = [step() for _ in range(25)]                        # nothing asks to stop for 1 s: the latch lets go
  assert outs[-1] == log.Desire.turnRight
  first = outs.index(log.Desire.turnRight)
  assert all(o == log.Desire.turnRight for o in outs[first:])


def test_latch_without_a_stop_still_holds(sm):
  # a stop request while rolling (no standstill since) keeps blocking the turn: upstream's behaviour, unchanged
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  _plan(sm)
  sm['longitudinalPlan'].shouldStop = True
  _at(sm, NOW)
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False) == log.Desire.none
  sm['longitudinalPlan'].shouldStop = False
  for k in range(1, 60):
    now = NOW + int(k * 0.05e9)
    _at(sm, now)
    assert owner.select(sm, now, log.Desire.none, supported=True, model_stop=False) == log.Desire.none


# ---- patch 38: your own blinker kept as a turn without a route (StarView's tablet sees a street on that side)

def _no_route(sm):
  sm['starpilotNavigation'].navigation.enabled = False
  _plan(sm)


def test_blinker_turn_without_a_route(sm):
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  _no_route(sm)
  _at(sm, NOW)
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False) == log.Desire.none   # the tablet didn't ask
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False, blinker_turn=True) == log.Desire.turnRight
  sm['carState'].rightBlinker, sm['carState'].leftBlinker = False, True
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False, blinker_turn=True) == log.Desire.turnLeft
  sm['carState'].leftBlindspot = True
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False, blinker_turn=True) == log.Desire.none
  sm['carState'].leftBlindspot = False
  sm['carState'].vEgo = 9.0                                   # over 20 mph: a lane change, not a turn
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False, blinker_turn=True) == log.Desire.none
  sm['carState'].vEgo = 5.
  assert owner.select(sm, NOW, log.Desire.laneChangeLeft, supported=True, model_stop=False, blinker_turn=True) == \
    log.Desire.laneChangeLeft                                 # a lane change already under way is kept
  assert owner.select(sm, NOW, log.Desire.none, supported=False, model_stop=False, blinker_turn=True) == log.Desire.none


def test_blinker_turn_kept_through_a_long_red_light(sm):
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  _no_route(sm)
  t = [NOW]
  def step(dt=0.05, model_stop=False):
    t[0] += int(dt * 1e9)
    _at(sm, t[0])
    return owner.select(sm, t[0], log.Desire.none, supported=True, model_stop=model_stop, blinker_turn=True)
  assert step() == log.Desire.turnRight
  sm['longitudinalPlan'].shouldStop = True
  assert step() == log.Desire.none                            # braking for the light
  sm['carState'].standstill, sm['carState'].vEgo = True, 0.
  for _ in range(int(60 / 0.05)):                             # a minute at the light
    assert step() == log.Desire.none
  sm['carState'].standstill, sm['carState'].vEgo = False, 1.
  sm['longitudinalPlan'].shouldStop = False
  outs = [step() for _ in range(25)]
  assert outs[-1] == log.Desire.turnRight                     # still remembered when pulling away
  outs = [step() for _ in range(int(11 / 0.05))]
  assert outs.count(log.Desire.none) == 2                     # and pulsed again every 5 s while it's wanted


def test_route_wins_over_the_blinker_turn(sm):
  from openpilot.starpilot.navigation.intent import TurnIntent
  owner = TurnIntent()
  _plan(sm)
  _at(sm, NOW)
  sm['starpilotNavigation'].navigation.instruction.maneuverModifier = 'left'   # the route turns left, blinker right
  assert owner.select(sm, NOW, log.Desire.none, supported=True, model_stop=False, blinker_turn=True) == log.Desire.none


def test_blinker_turn_stops_a_lane_change_starting(sm):
  from openpilot.selfdrive.controls.lib.desire_helper import DesireHelper
  from openpilot.starpilot.lateral.lane_change_preferences import LaneChangePolicy
  cs = sm['carState']
  cs.steeringPressed, cs.steeringTorque = True, -1.
  helper = DesireHelper(LaneChangePolicy(minimum_speed_mps=0.))
  helper.update(cs, True, 1., navigation_turn=True)
  assert helper.lane_change_state == log.LaneChangeState.off


def test_tablet_turn_file(tmp_path):
  from openpilot.starpilot.system.starview import blinker_turn
  path = str(tmp_path / "turn")
  clock = [100.0]
  reader = blinker_turn.BlinkerTurn(path, clock=lambda: clock[0])
  right = NS(leftBlinker=False, rightBlinker=True)
  assert not reader.for_blinker(right)
  blinker_turn.write("right", path, clock=lambda: clock[0])
  assert reader.for_blinker(right)
  assert not reader.for_blinker(NS(leftBlinker=True, rightBlinker=False))
  clock[0] += 2.0                                              # the tablet stopped asking
  assert not reader.for_blinker(right)
  blinker_turn.write(None, path)
  assert reader.read() == ""
  with pytest.raises(ValueError):
    blinker_turn.write("straight", path)
