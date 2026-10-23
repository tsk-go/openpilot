"""StarView's street map on whether your blinker is for a turn (fork patch 38), on top of upstream's Turn Signal Guidance.

Turn Signal Guidance (StarPilot, Oct 22) makes any blinker under 20 mph without a route a turn - signalling to pull over
too. StarView's tablet knows the streets: while a blinker is on, its switch ("Remember my turn signal") is on and it has
our street on its map, it says every half second (starviewd "turn_intent" {side}) whether there is a street to turn into
on that side within about 250 ft ahead - not a one-way coming at us, not a driveway - or right at the corner while we
wait: "left" / "right" = yes for that side, "none" = no street there. starviewd writes PATH: "<side> <monotonic>".
navigation/intent.py then gives the turn only when the tablet says yes (or has no say). Older than MAX_AGE, the switch
off, or no map: no say - Turn Signal Guidance as upstream. Guidance off in Galaxy: no turn either way.
"""
import os
import time

PATH = "/dev/shm/starview_turn"
MAX_AGE = 1.5
SIDES = ("left", "right", "none")


def write(side, path: str = PATH, clock=time.monotonic) -> str | None:
  """Store what the tablet says (None = no say)."""
  if side is None:
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    return None
  if side not in SIDES:
    raise ValueError("side must be left, right, none or null")
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
    """'left' / 'right' / 'none' while the tablet has a say, else ''."""
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

  def for_blinker(self, car_state) -> str | None:
    """'turn': a street to turn into on the side of the one blinker that is on; 'no': the tablet sees none; None: no say."""
    if car_state.leftBlinker == car_state.rightBlinker:
      return None
    side = self.read()
    if not side:
      return None
    return "turn" if side == ("left" if car_state.leftBlinker else "right") else "no"
