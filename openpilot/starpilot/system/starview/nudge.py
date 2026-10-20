"""How hard a steering nudge has to be to start a lane change, set from StarView's tablet.

Stock, desire_helper starts a signalled lane change on carState.steeringPressed toward that side: on Toyota the
EPS driver torque past STEER_THRESHOLD (100), one frame. With Always On Lateral openpilot holds the wheel, so the
nudge pushes against it. The tablet's "Blinker & lane changes" page sets a strength as a percentage of the car's
own threshold (30-150 %); starviewd keeps it in PATH. desire_helper then counts a nudge as driver torque toward
that side at or above that many units, held NUDGE_HOLD_S so a bump in the road doesn't start a lane change.

No file (or 100 %) or a car other than Toyota: the stock steeringPressed rule, unchanged.
"""
import os
import time

PATH = "/data/starview/nudge_pct"
MIN_PCT, MAX_PCT = 30, 150
CHECK_EVERY_S = 1.0


def write(pct, path: str = PATH) -> int | None:
  """Store the strength (None / 100 = stock). Returns what is in force."""
  if pct is None or int(pct) == 100:
    try:
      os.unlink(path)
    except FileNotFoundError:
      pass
    return None
  value = int(pct)
  if not MIN_PCT <= value <= MAX_PCT:
    raise ValueError(f"nudge strength must be {MIN_PCT}-{MAX_PCT} %")
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = f"{path}.tmp"
  with open(tmp, "w") as f:
    f.write(str(value))
  os.replace(tmp, path)
  return value


def read(path: str = PATH) -> int | None:
  try:
    with open(path) as f:
      value = int(f.read(16).strip())
  except (OSError, ValueError):
    return None
  return value if MIN_PCT <= value <= MAX_PCT and value != 100 else None


def car_threshold(brand: str) -> float | None:
  """The car's own driver-torque threshold for steeringPressed, where it is a plain torque threshold."""
  if brand == "toyota":
    try:
      from opendbc.car.toyota.values import STEER_THRESHOLD
      return float(STEER_THRESHOLD)
    except Exception:
      return None
  return None


class NudgeSetting:
  """Read once a second at most (modeld calls it every frame)."""

  def __init__(self, brand: str, path: str = PATH, clock=time.monotonic):
    self.base = car_threshold(brand)
    self.path, self.clock = path, clock
    self._checked = -1e9
    self._torque: float | None = None

  def torque(self) -> float | None:
    """Driver torque (car units) a nudge needs, or None for the stock rule."""
    if self.base is None:
      return None
    now = self.clock()
    if now - self._checked >= CHECK_EVERY_S:
      self._checked = now
      pct = read(self.path)
      self._torque = None if pct is None else self.base * pct / 100.
    return self._torque
