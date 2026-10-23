"""Your own turn signal kept as a turn without a route (patch 38), decided on StarView's tablet.

Without a route the blinker only ever meant a lane change (from 5 mph): at a corner the car started moving over, and
braking under 5 mph cancelled it. StarView's tablet knows the streets: with your blinker on, no route, under 20 mph and a
street you can turn into on that side within about 250 ft ahead (or right at the corner while stopped), it sends
starviewd "turn_intent" {"side"} every half second; starviewd writes PATH: "<side> <monotonic>". modeld then gives the
model the turn desire for that blinker the same way as a route turn (navigation/intent.py TurnIntent: kept through a
long stop, pulsed again every 5 s) and no lane change starts for it. Older than MAX_AGE (the tablet stopped asking, or
is gone): ignored.
"""
import os
import time

PATH = "/dev/shm/starview_turn"
MAX_AGE = 1.5
SIDES = ("left", "right")


def write(side, path: str = PATH, clock=time.monotonic) -> str | None:
  """Store the side the tablet wants to turn to (None = nothing)."""
  if side is None:
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    return None
  if side not in SIDES:
    raise ValueError("side must be left, right or null")
  tmp = f"{path}.tmp"
  with open(tmp, "w") as f:
    f.write(f"{side} {clock():.3f}")
  os.replace(tmp, path)
  return side


class BlinkerTurn:
  def __init__(self, path: str = PATH, clock=time.monotonic):
    self.path, self.clock = path, clock
    self._key = (0, 0)
    self._side = ""
    self._t = 0.0

  def read(self) -> str:
    """'left' / 'right' while the tablet asks, else ''."""
    try:
      st = os.stat(self.path)
    except OSError:
      return ""
    key = (st.st_ino, st.st_mtime_ns)
    if key != self._key:
      self._key, self._side, self._t = key, "", 0.0
      try:
        with open(self.path) as f:
          side, t = f.read(64).split()
        if side in SIDES:
          self._side, self._t = side, float(t)
      except (OSError, ValueError):
        pass
    if not -0.05 <= self.clock() - self._t <= MAX_AGE:
      return ""
    return self._side

  def for_blinker(self, car_state) -> bool:
    """True when the tablet's turn is for the one blinker that is on."""
    if car_state.leftBlinker == car_state.rightBlinker:
      return False
    return self.read() == ("left" if car_state.leftBlinker else "right")
