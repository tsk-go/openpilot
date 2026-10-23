"""Advice from StarView's tablet to the planner and Lane Centering (fork patch 39, the "New ideas" tab).

All the thinking runs on the tablet (speed bumps, potholes, cut-ins, uncertain model, light timing...). The comma only
reads one tiny file, and every piece of advice can only make the drive gentler, inside hard limits:
  cap     m/s  the set speed may be lowered to this - never raised, never below MIN_CAP_MPS
  follow  s    extra following time, 0..MAX_EXTRA_FOLLOW
  offset  m    added to Lane Centering's offset (+ = right), clipped to +-MAX_OFFSET; only while Lane Centering is on
starviewd action "advice" {"cap", "follow", "offset", "why"} writes PATH: "<monotonic> <cap|-> <follow> <offset> <why>".
Older than MAX_AGE (the tablet stopped, or is gone): no advice. The file is looked at no more than every CHECK_S.
"""
import math
import os
import time

PATH = "/dev/shm/starview_advice"
MAX_AGE = 1.5
CHECK_S = 0.25
MIN_CAP_MPS = 10 * 0.44704
MAX_EXTRA_FOLLOW = 0.6
MAX_OFFSET = 0.3


def _num(v):
  if v is None or isinstance(v, bool):
    return None
  try:
    f = float(v)
  except (TypeError, ValueError):
    return None
  return f if math.isfinite(f) else None


def write(req: dict, path: str = PATH, clock=time.monotonic) -> dict | None:
  """Store the tablet's advice; None / {} clears it. Returns what is in force."""
  if not req:
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    return None
  cap = _num(req.get("cap"))
  follow = _num(req.get("follow")) or 0.0
  offset = _num(req.get("offset")) or 0.0
  why = str(req.get("why") or "-").replace(" ", "_")[:24]
  cap = None if cap is None else max(MIN_CAP_MPS, cap)
  follow = min(max(0.0, follow), MAX_EXTRA_FOLLOW)
  offset = min(max(-MAX_OFFSET, offset), MAX_OFFSET)
  tmp = f"{path}.tmp"
  with open(tmp, "w") as f:
    f.write(f"{clock():.3f} {'-' if cap is None else f'{cap:.3f}'} {follow:.3f} {offset:.3f} {why}")
  os.replace(tmp, path)
  return {"cap": cap, "follow": follow, "offset": offset, "why": why}


class Advice:
  def __init__(self, path: str = PATH, clock=time.monotonic):
    self.path, self.clock = path, clock
    self._checked = -1e9
    self._key = (0, 0)
    self._t = -1e9
    self._cap: float | None = None
    self._follow = 0.0
    self._offset = 0.0
    self.why = ""

  def _fresh(self) -> bool:
    now = self.clock()
    if now - self._checked >= CHECK_S:
      self._checked = now
      try:
        st = os.stat(self.path)
        key = (st.st_ino, st.st_mtime_ns)
      except OSError:
        key = None
      if key is None:
        self._key, self._t = (0, 0), -1e9
      elif key != self._key:
        self._key = key
        try:
          with open(self.path) as f:
            t, cap, follow, offset, why = f.read(96).split()
          self._t = float(t)
          c = None if cap == "-" else _num(cap)
          self._cap = None if c is None else max(MIN_CAP_MPS, c)
          self._follow = min(max(0.0, _num(follow) or 0.0), MAX_EXTRA_FOLLOW)
          self._offset = min(max(-MAX_OFFSET, _num(offset) or 0.0), MAX_OFFSET)
          self.why = why
        except (OSError, ValueError):
          self._t = -1e9
    return -0.05 <= now - self._t <= MAX_AGE

  def speed_cap(self) -> float | None:
    return self._cap if self._fresh() else None

  def extra_follow(self) -> float:
    return self._follow if self._fresh() else 0.0

  def offset(self) -> float:
    return self._offset if self._fresh() else 0.0
