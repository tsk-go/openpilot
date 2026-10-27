"""Stationary Toyota door commands on actual observed gear transitions, and one-off lock / unlock asked for by StarView.

Command payloads from Dom StarPilot, credited there to AlexandreSato.
This owner never changes Panda safety mode or sends diagnostics directly.

StarView: the 4th-gen Sienna's Main Body module refuses that KWP command (7F 30 11, service not supported) and takes
Toyota's UDS active test instead (GTS+ "Door Lock" / "Door Unlock": 2F 2810 / 2F 2811). A request from the tablet runs
it as a short sequence over the normal link - nothing is paused, so cruise never sees a gap:
  extended session (10 03) -> 0.1 s -> lock / unlock on -> answer-back (horn chirp by default: one for lock, two for
  unlock; StarLock can set how many, how long and how far apart) -> 1 s after "on": back to the module -> 0.1 s after
  the last beep (at least): default session (10 01)
The wireless buzzer (2F 284A) is allowed too, but on the Sienna it doesn't stop on "return control" - it sounds until
the session ends, so its beeps merge into one long one; the horn is what StarLock offers.
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
UDS_ON = {"lock": b"\x40\x06\x2f\x28\x10\x03\x01\x80", "unlock": b"\x40\x06\x2f\x28\x11\x03\x01\x80",
          "buzzer": b"\x40\x06\x2f\x28\x4a\x03\x01\x80", "horn": b"\x40\x06\x2f\x28\x02\x03\x01\x80"}
UDS_OFF = {"lock": b"\x40\x05\x2f\x28\x10\x00\x80\x00", "unlock": b"\x40\x05\x2f\x28\x11\x00\x80\x00",
           "buzzer": b"\x40\x05\x2f\x28\x4a\x00\x80\x00", "horn": b"\x40\x05\x2f\x28\x02\x00\x80\x00"}
SOUNDS = ("buzzer", "horn", "none")
# controller frames (100 Hz) after the request: the door output, then the answer-back - one beep for lock, two for
# unlock (buzzer 0.15 s each, horn a 0.08 s chirp) - then the door goes back to the module and the session ends
STEP_ON, STEP_OFF, STEP_DEFAULT = 10, 110, 120
NO_ANSWER_FRAMES = 30   # 0.3 s without the module's reply to "on": answered as sent but unconfirmed
BEEPS = {"buzzer": ((20, 35), (50, 65)), "horn": ((20, 28), (45, 53)), "none": ()}
# StarLock can set its own pattern per lock / unlock (see parse_pattern); it starts at the same frame as the default
BEEP_START = 20
PATTERN_LIMITS = {"n": (1, 5), "on": (3, 100), "gap": (5, 100)}
UDS_TESTER_PRESENT = b"\x40\x02\x3e\x00\x00\x00\x00\x00"
KEEPALIVE = 150


def parse_pattern(text):
  """StarLock's own horn pattern, "2x8x17": beeps x frames on x frames between (100 Hz); None if malformed or out of
  range. 1-5 beeps of 0.03-1 s, 0.05-1 s apart."""
  try:
    n, on, gap = (int(v) for v in text.split("x"))
  except ValueError:
    return None
  if not (PATTERN_LIMITS["n"][0] <= n <= PATTERN_LIMITS["n"][1] and PATTERN_LIMITS["on"][0] <= on <= PATTERN_LIMITS["on"][1]
          and PATTERN_LIMITS["gap"][0] <= gap <= PATTERN_LIMITS["gap"][1]):
    return None
  return n, on, gap


def schedule(cmd, sound, pattern=None):
  """{frame: (action, output)} for one request; action "on" / "off" / "ext" / "tp" / "default". One output per frame:
  anything landing on a taken frame moves to the next free one. A long horn pattern gets a tester present every 1.5 s
  so the module keeps the session."""
  if sound == "none":
    beeps = ()
  elif pattern is None:
    beeps = BEEPS[sound][:1 if cmd == "lock" else 2]
  else:
    n, on, gap = pattern
    beeps = tuple((BEEP_START + i * (on + gap), BEEP_START + i * (on + gap) + on) for i in range(n))
  events = [(0, "ext", None), (STEP_ON, "on", cmd), (STEP_OFF, "off", cmd)]
  for on, off in beeps:
    events += [(on, "on", sound), (off, "off", sound)]
  plan = {}

  def put(frame, action, out):
    while frame in plan:
      frame += 1
    plan[frame] = (action, out)

  for frame, action, out in sorted(events, key=lambda e: e[0]):
    put(frame, action, out)
  for frame in range(KEEPALIVE, max(plan), KEEPALIVE):
    put(frame, "tp", None)
  put(max(STEP_DEFAULT, max(plan) + 10), "default", None)
  return plan


class DoorLocks:
  def __init__(self):
    self.lock = self.unlock = False
    self.previous_gear = None
    # StarView: "lock" / "unlock" (+ " horn" (default) / " buzzer" / " none", + optional pattern " 2x8x17") asked for
    # from the tablet or phone;
    # manual_result says what happened to it
    self.manual = None
    self.manual_result = ""
    self.sequence = None   # while the UDS active test runs: {"cmd", "plan", "n", "held", "aborted"}

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

  def response(self, dat: bytes):
    """The Main Body module's reply on 0x758 (card hands these over only while a request runs): its "done" to the door
    output (6F 28 1x 03) is the answer - the car itself confirming it took the lock / unlock."""
    s = self.sequence
    if s is None or s.get("on_at") is None or s.get("answered") or len(dat) < 5 or dat[0] != 0x40:
      return
    did = 0x10 if s["cmd"] == "lock" else 0x11
    if dat[2] == 0x6F and dat[3] == 0x28 and dat[4] == did and (len(dat) < 6 or dat[5] == 0x03):
      s["answered"] = s["final"] = True
      self.manual_result = f"{s['cmd']}: confirmed"
    elif dat[2] == 0x7F and dat[3] == 0x2F:
      s["answered"] = s["final"] = True
      self.manual_result = f"{s['cmd']}: refused by the car (code {dat[4]:02X})"
      s["aborted"] = s["aborted"] or "refused by the car"

  def _finish(self):
    s, self.sequence = self.sequence, None
    if s["aborted"] and not s.get("final"):       # the car's own answer stands; otherwise say why it stopped
      self.manual_result = f"{s['cmd']}: stopped ({s['aborted']})"
    return UDS_DEFAULT

  def _step(self, why):
    s = self.sequence
    if why and not s["aborted"]:
      s["aborted"] = why
    if s["aborted"]:
      # hand everything back right away, one output per frame (the buzzer / horn first), then leave the session
      if s["held"]:
        out = s["held"].pop()
        return UDS_OFF[out]
      return self._finish()
    n = s["n"]
    s["n"] += 1
    if s.get("on_at") is not None and not s.get("answered") and n - s["on_at"] >= NO_ANSWER_FRAMES:
      s["answered"] = True
      self.manual_result = f"{s['cmd']}: sent, no answer from the car"
    action, out = s["plan"].get(n, (None, None))
    if action == "ext":
      return UDS_EXTENDED
    if action == "tp":
      return UDS_TESTER_PRESENT
    if action == "on":
      s["held"].append(out)
      if out == s["cmd"]:
        s["on_at"] = n                          # the answer is the module's reply to this (see response())
      return UDS_ON[out]
    if action == "off":
      s["held"].remove(out)
      return UDS_OFF[out]
    if action == "default":
      return self._finish()
    return None

  def update(self, state):
    manual, self.manual = self.manual, None
    if manual is not None:
      parts = manual.split(" ")
      cmd, sound = parts[0], (parts[1] if len(parts) > 1 else "horn")
      pattern = parse_pattern(parts[2]) if len(parts) == 3 else None
      why = ("bad request" if cmd not in ("lock", "unlock") or sound not in SOUNDS or len(parts) > 3 or
             (len(parts) == 3 and pattern is None) else
             "busy" if self.sequence is not None else self._blocker(state))
      if why:
        self.manual_result = f"{cmd}: not sent ({why})"
      else:
        self.sequence = {"cmd": cmd, "plan": schedule(cmd, sound, pattern), "n": 0, "held": [], "aborted": ""}
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
