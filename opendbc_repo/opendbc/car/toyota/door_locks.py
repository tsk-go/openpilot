"""Stationary Toyota door commands on actual observed gear transitions, and one-off lock / unlock asked for by StarView.

Command payloads from Dom StarPilot, credited there to AlexandreSato.
This owner never changes Panda safety mode or sends diagnostics directly.

StarView: the 4th-gen Sienna's Main Body module refuses that KWP command (7F 30 11, service not supported) and takes
Toyota's UDS active test instead (GTS+ "Door Lock" / "Door Unlock": 2F 2810 / 2F 2811). A request from the tablet runs
it as a short sequence over the normal link - nothing is paused, so cruise never sees a gap:
  extended session (10 03) -> 0.1 s -> lock / unlock on -> 1 s -> back to the module -> 0.1 s -> default session (10 01)
Only started in Park and standing still with no gas (Panda safety checks stationary + no gas again). If that stops
being true while it runs, control goes straight back to the module.
"""

import math

from opendbc.car.structs import CarState

# Credit: AlexandreSato (original Dom Toyota controller).
LOCK_CMD = b"\x40\x05\x30\x11\x00\x80\x00\x00"
UNLOCK_CMD = b"\x40\x05\x30\x11\x00\x40\x00\x00"
Gear = CarState.GearShifter

# UDS active test, Main Body (0x750 sub-address 0x40); padded with 0x00 like opendbc's ISO-TP
UDS_EXTENDED = b"\x40\x02\x10\x03\x00\x00\x00\x00"
UDS_DEFAULT = b"\x40\x02\x10\x01\x00\x00\x00\x00"
UDS_ON = {"lock": b"\x40\x06\x2f\x28\x10\x03\x01\x80", "unlock": b"\x40\x06\x2f\x28\x11\x03\x01\x80"}
UDS_OFF = {"lock": b"\x40\x05\x2f\x28\x10\x00\x80\x00", "unlock": b"\x40\x05\x2f\x28\x11\x00\x80\x00"}
# controller frames (100 Hz) after the request
STEP_ON, STEP_OFF, STEP_DEFAULT = 10, 110, 120


class DoorLocks:
  def __init__(self):
    self.lock = self.unlock = False
    self.previous_gear = None
    # StarView: "lock" / "unlock" asked for from the tablet; manual_result says what happened to it
    self.manual = None
    self.manual_result = ""
    self.sequence = None   # {"cmd", "n", "aborted"} while the UDS active test runs

  @staticmethod
  def _blocker(state):
    if not state.canValid or state.canTimeout:
      return "no car data"
    if state.gearShifter != Gear.park:
      return "not in Park"
    if not (state.standstill and math.isfinite(state.vEgoRaw) and abs(state.vEgoRaw) <= .01):
      return "not stopped"
    if state.gasPressed:
      return "gas pressed"
    if state.vehicleSensorsInvalid:
      return "car sensors not ready"
    return ""

  def _step(self, why):
    s = self.sequence
    if why and s["n"] < STEP_ON:              # nothing taken over yet: just leave the session
      s["n"], s["aborted"] = STEP_DEFAULT, why
    elif why and s["n"] < STEP_OFF:           # holding the output: give it back now
      s["n"], s["aborted"] = STEP_OFF, why
    n = s["n"]
    s["n"] += 1
    if n == 0:
      return UDS_EXTENDED
    if n == STEP_ON:
      return UDS_ON[s["cmd"]]
    if n == STEP_OFF:
      return UDS_OFF[s["cmd"]]
    if n == STEP_DEFAULT:
      self.sequence = None
      self.manual_result = f"{s['cmd']}: " + (f"stopped ({s['aborted']})" if s["aborted"] else "sent")
      return UDS_DEFAULT
    return None

  def update(self, state):
    manual, self.manual = self.manual, None
    if manual is not None:
      why = "busy" if self.sequence is not None else self._blocker(state)
      if why:
        self.manual_result = f"{manual}: not sent ({why})"
      else:
        self.sequence = {"cmd": manual, "n": 0, "aborted": ""}
    if self.sequence is not None:
      self.previous_gear = state.gearShifter
      return self._step(self._blocker(state))

    gear = state.gearShifter
    if not state.canValid or state.canTimeout or gear not in (Gear.park, Gear.drive, Gear.reverse, Gear.neutral):
      self.previous_gear = None
      return None
    previous, self.previous_gear = self.previous_gear, gear
    if (previous is None or previous == gear or not state.standstill or not math.isfinite(state.vEgoRaw) or
        abs(state.vEgoRaw) > .01 or state.doorOpen or state.gasPressed or state.vehicleSensorsInvalid):
      return None
    if previous == Gear.park and gear != Gear.park and self.lock:
      return LOCK_CMD
    if previous != Gear.park and gear == Gear.park and self.unlock:
      return UNLOCK_CMD
    return None
