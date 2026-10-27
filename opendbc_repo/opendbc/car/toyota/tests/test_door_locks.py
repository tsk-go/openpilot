"""Actual factory Toyota controller emits only one stationary transition command."""

import pytest

from opendbc.car import structs
from opendbc.car.toyota.door_locks import LOCK_CMD, UNLOCK_CMD
from opendbc.car.toyota.tests.test_auto_hold import setup_hold, step_hold
from opendbc.car.toyota.values import CAR

Gear = structs.CarState.GearShifter


def body_commands(controller, command, state):
  return [frame for frame in step_hold(controller, command, state) if frame[0] == 0x750 and frame[1] in (LOCK_CMD, UNLOCK_CMD)]


@pytest.mark.parametrize('car', [CAR.TOYOTA_PRIUS, CAR.TOYOTA_COROLLA_TSS2, CAR.TOYOTA_RAV4_TSS2])
def test_actual_controller_park_drive_park_one_shot_with_no_control_enable(car):
  _, controller, command, state = setup_hold(car, enabled=False)
  assert not command.enabled and not command.latActive and not command.longActive
  controller.door_locks.lock = controller.door_locks.unlock = True
  state.out.gearShifter = Gear.park
  assert body_commands(controller, command, state) == []
  state.out.gearShifter = Gear.drive
  assert body_commands(controller, command, state) == [(0x750, LOCK_CMD, 0)]
  assert body_commands(controller, command, state) == []
  state.out.gearShifter = Gear.park
  assert body_commands(controller, command, state) == [(0x750, UNLOCK_CMD, 0)]
  assert body_commands(controller, command, state) == []


@pytest.mark.parametrize('fault', ['moving', 'door', 'gas', 'invalid_can', 'timeout', 'invalid_sensors'])
def test_actual_controller_rejects_physical_or_source_fault_at_transition(fault):
  _, controller, command, state = setup_hold(enabled=False)
  controller.door_locks.lock = controller.door_locks.unlock = True
  state.out.gearShifter = Gear.park
  assert body_commands(controller, command, state) == []
  state.out.gearShifter = Gear.drive
  if fault == 'moving':
    state.out.standstill, state.out.vEgoRaw = False, 1.0
  elif fault == 'door':
    state.out.doorOpen = True
  elif fault == 'gas':
    state.out.gasPressed = True
  elif fault == 'invalid_can':
    state.out.canValid = False
  elif fault == 'timeout':
    state.out.canTimeout = True
  else:
    state.out.vehicleSensorsInvalid = True
  assert body_commands(controller, command, state) == []


def test_defaults_off_and_starting_in_drive_never_create_transition():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  assert body_commands(controller, command, state) == []
  state.out.gearShifter = Gear.drive
  assert body_commands(controller, command, state) == []
  _, controller, command, state = setup_hold(enabled=False)
  controller.door_locks.lock = True
  assert body_commands(controller, command, state) == []


from opendbc.car.toyota.door_locks import UDS_DEFAULT, UDS_EXTENDED, UDS_OFF, UDS_ON  # noqa: E402


def door_frames(controller, command, state, frames):
  """{frame index: payload} of everything sent to 0x750 over [frames] controller steps (radar tester present aside)"""
  out = {}
  for i in range(frames):
    for f in step_hold(controller, command, state):
      if f[0] == 0x750 and f[1][0] == 0x40:
        out[i] = f[1]
  return out


def test_tablet_lock_runs_the_uds_active_test_in_park():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = "lock buzzer"
  assert door_frames(controller, command, state, 140) == {0: UDS_EXTENDED, 10: UDS_ON["lock"], 20: UDS_ON["buzzer"],
                                                          35: UDS_OFF["buzzer"], 110: UDS_OFF["lock"], 120: UDS_DEFAULT}
  assert controller.door_locks.manual_result == "lock: sent"
  controller.door_locks.manual = "unlock buzzer"
  assert door_frames(controller, command, state, 140) == {0: UDS_EXTENDED, 10: UDS_ON["unlock"], 20: UDS_ON["buzzer"],
                                                          35: UDS_OFF["buzzer"], 50: UDS_ON["buzzer"], 65: UDS_OFF["buzzer"],
                                                          110: UDS_OFF["unlock"], 120: UDS_DEFAULT}


def test_tablet_lock_hands_back_at_once_when_the_car_leaves_park():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = "lock"
  first = door_frames(controller, command, state, 50)
  assert first == {0: UDS_EXTENDED, 10: UDS_ON["lock"], 20: UDS_ON["horn"], 28: UDS_OFF["horn"]}
  state.out.gearShifter = Gear.drive
  rest = door_frames(controller, command, state, 30)
  assert rest == {0: UDS_OFF["lock"], 1: UDS_DEFAULT}
  assert controller.door_locks.manual_result == "lock: stopped (not in Park)"


@pytest.mark.parametrize('fault, why', [('drive', 'not in Park'), ('moving', 'not stopped'), ('gas', 'gas pressed')])
def test_tablet_request_is_refused_out_of_park_moving_or_on_gas(fault, why):
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  if fault == 'drive':
    state.out.gearShifter = Gear.drive
  elif fault == 'moving':
    state.out.standstill, state.out.vEgoRaw = False, 1.0
  else:
    state.out.gasPressed = True
  controller.door_locks.manual = "lock"
  assert door_frames(controller, command, state, 20) == {}
  assert controller.door_locks.manual_result == f"lock: not sent ({why})"


def test_answer_is_ready_as_soon_as_the_doors_move():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = "unlock"
  door_frames(controller, command, state, 11)        # extended session, then unlock on at frame 10
  assert controller.door_locks.manual_result == "unlock: sent"
  assert controller.door_locks.sequence is not None  # the hand-back still follows



@pytest.mark.parametrize('request_, expect', [
  ("lock horn", {20: "horn", 28: "horn"}),
  ("unlock horn", {20: "horn", 28: "horn", 45: "horn", 53: "horn"}),
  ("lock none", {}),
  ("unlock none", {}),
])
def test_sound_choice(request_, expect):
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = request_
  frames = door_frames(controller, command, state, 140)
  sound = {n: f for n, f in frames.items() if n not in (0, 10, 110, 120)}
  assert {n: ("horn" if f in (UDS_ON["horn"], UDS_OFF["horn"]) else f) for n, f in sound.items()} == expect
  assert all(f != UDS_ON["buzzer"] for f in frames.values())


def test_leaving_park_mid_beep_silences_first_then_hands_back():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = "unlock"
  assert door_frames(controller, command, state, 25)[20] == UDS_ON["horn"]        # the horn is on now
  state.out.gearShifter = Gear.reverse
  assert door_frames(controller, command, state, 5) == {0: UDS_OFF["horn"], 1: UDS_OFF["unlock"], 2: UDS_DEFAULT}
  assert controller.door_locks.manual_result == "unlock: stopped (not in Park)"


def test_bad_sound_is_refused():
  _, controller, command, state = setup_hold(enabled=False)
  state.out.gearShifter = Gear.park
  step_hold(controller, command, state)
  controller.door_locks.manual = "lock siren"
  assert door_frames(controller, command, state, 20) == {}
  assert controller.door_locks.manual_result == "lock: not sent (bad request)"
