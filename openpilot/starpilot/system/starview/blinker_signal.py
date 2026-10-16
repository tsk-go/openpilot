"""Why StarView's automatic blinker holds a turn signal, for modeld's desire helper.

starviewd's PicoBlinker writes /dev/shm/starview_signal while it holds a blinker: "<why> <side> <monotonic>", rewritten
every 250 ms, removed on release. why:
  turn  a route turn: never a lane change (the route's turn desire still comes from navigation/intent.py)
  lane  a lane change the driver confirmed on the tablet (tap, steering nudge, or the automatic countdown): starts it
        without a further nudge, once per blinker hold, only with an adjacent lane seen (same check as automatic lane
        changes) and the blind spot clear
Older than MAX_AGE = starviewd or the tablet is gone: ignored.
"""
import os
import time

PATH = "/dev/shm/starview_signal"
MAX_AGE = 1.0
WHYS = ("turn", "lane")


class StarViewSignal:
  def __init__(self, path: str = PATH, clock=time.monotonic):
    self.path, self.clock = path, clock
    self._key = (0, 0)
    self._text = ""
    self._t = 0.0

  def read(self) -> str:
    """'turn left' / 'turn right' / 'lane left' / 'lane right', or ''."""
    try:
      st = os.stat(self.path)
    except OSError:
      return ""
    key = (st.st_ino, st.st_mtime_ns)    # starviewd replaces the file: a new inode every time
    if key != self._key:
      self._key, self._text, self._t = key, "", 0.0
      try:
        with open(self.path) as f:
          why, side, t = f.read(64).split()
        if why in WHYS and side in ("left", "right"):
          self._text, self._t = f"{why} {side}", float(t)
      except (OSError, ValueError):
        pass
    if not -0.05 <= self.clock() - self._t <= MAX_AGE:   # -: the stamp is rounded to ms
      return ""
    return self._text

  def for_blinker(self, car_state) -> str:
    """'turn' / 'lane' when the signal is for the one blinker that is on, else ''."""
    if car_state.leftBlinker == car_state.rightBlinker:
      return ""
    side = "left" if car_state.leftBlinker else "right"
    why, _, s = self.read().partition(" ")
    return why if s == side else ""
