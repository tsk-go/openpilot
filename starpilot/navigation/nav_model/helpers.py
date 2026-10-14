"""Model inputs for navigation (ported from commaai/openpilot nav-model-integration, Oct 2026)."""
import json
import math
from datetime import UTC, datetime
import re
import time
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from cereal import log


def latest_gps_source(sm) -> str | None:
  """The service with the freshest usable GPS fix, or None."""
  now = time.monotonic()
  sources = [s for s in ('gpsLocation', 'gpsLocationExternal')
             if sm.valid[s] and sm[s].hasFix and 0 <= now - sm.recv_time[s] < 2]
  return max(sources, key=lambda s: sm.logMonoTime[s]) if sources else None


# convert mapbox steps to valhalla enums the model was trained on
VALHALLA_COMMAND_COUNT = 46
VALHALLA_SIDED_TYPES = {  # (straight, right, left)
  'depart': (1, 2, 3), 'arrive': (4, 5, 6),
  'on ramp': (17, 18, 19), 'off ramp': (20, 20, 21), 'fork': (22, 23, 24),
  'roundabout': (26, 26, 26), 'rotary': (26, 26, 26), 'roundabout turn': (26, 26, 26),
  'exit roundabout': (27, 27, 27), 'exit rotary': (27, 27, 27), 'notification': (28, 28, 28),
}
VALHALLA_TURN_TYPES = {'straight': 8, 'slight right': 9, 'right': 10, 'sharp right': 11, 'uturn': 13,
                       'sharp left': 14, 'left': 15, 'slight left': 16}  # turn, continue, new name, end of road


def valhalla_type(maneuver_type: str, modifier: str) -> int | None:
  if maneuver_type == 'merge':
    return None  # Valhalla gives no maneuver at a merge, so the model never saw one
  if maneuver_type in VALHALLA_SIDED_TYPES:
    straight, right, left = VALHALLA_SIDED_TYPES[maneuver_type]
    return right if 'right' in modifier else left if 'left' in modifier else straight
  return VALHALLA_TURN_TYPES.get(modifier, 8)


def navigation_input(maneuvers: Any, traveled: float) -> np.ndarray:
  """comma's encoding: maneuvers are the route steps not yet passed, each at the distance to where it starts."""
  navigation = np.zeros(VALHALLA_COMMAND_COUNT + 1, dtype=np.float32)
  for maneuver in maneuvers:
    command, distance = valhalla_type(maneuver.type, maneuver.modifier), maneuver.distance - traveled
    if command is not None and command > 6 and distance >= 0:
      navigation[command], navigation[-1] = 1, distance / 100
      break
  return navigation


class _Maneuver(NamedTuple):
  type: str
  modifier: str
  distance: float


def mapbox_modifier(modifier: str) -> str:
  """Mapbox's own modifier from StarPilot's: its route engine renames them for the UI ("slight left" -> "slightLeft",
  no modifier -> "none"), and the Valhalla mapping above only knows Mapbox's words - "slightLeft" has no "left" in it,
  so every slight / sharp maneuver went in as straight (or, on an off ramp, as a right exit)."""
  if modifier in ('', 'none'):
    return ''
  return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', modifier).lower()


def starpilot_navigation_input(maneuvers: Any, traveled: float) -> np.ndarray:
  """The model's navigation input from StarPilot's navInstruction.allManeuvers.

  StarPilot lists the current step first (its maneuver already done, with the distance to the end of the step), then
  the next steps at the distance to where each starts. comma's model wants only maneuvers ahead, so the current step
  is left out - otherwise the turn just made would be fed as the next one.
  """
  ahead = [_Maneuver(str(m.type), mapbox_modifier(str(m.modifier)), float(m.distance)) for m in list(maneuvers)[1:]]
  return navigation_input(ahead, traveled)


def advance_maneuvers(maneuvers: list, driven: float) -> list:
  """Maneuver distances as of now rather than as of the GPS position they were measured from, which navigationd reads
  up to 2.5 s old (30-75 m at highway speed): the model takes them as the distance to the next maneuver. A maneuver
  passed in the meantime is left at 0, so the model's own "driven since" correction drops it."""
  if driven <= 0.0:
    return maneuvers
  return [dict(m, distance=max(0.0, float(m.get("distance") or 0.0) - driven)) if isinstance(m, dict) else m for m in maneuvers]


# ---------------------------------------------------------------------------------------------------------------------
# When the model gets the route (Oct 14 2026, drive 00000a2d--4071d6c156): with a destination set the nav model moved
# three lanes left in 12 s after merging onto a highway (two of them unasked) while being told "exit right in 16.7 km",
# and refused the driver's right lane changes (its own lane-change forecast stayed at 0.01-0.08 while openpilot asked).
# Without a destination it drives fine. Without a destination the model gets a black map and no maneuver - the same as
# passing it nothing - so both rules below do exactly that.
#   1. the next turn is farther than the horizon (default 2 km): no route yet, it holds its lane like without one;
#   2. the driver is changing lanes with the stalk: no route until the lane change is over (+ a short tail).
# Lane changes started by StarPilot itself (a future automatic blinker that follows the model's own forecast,
# DesireHelper.lane_change_by_system) keep the route.

NAV_HORIZON_FILE = Path('/data/starview/nav_model_horizon_m')   # metres; 0 = always give the route
DEFAULT_NAV_HORIZON_M = 2000.0
NAV_GATE_STATUS_FILE = Path('/dev/shm/nav_model_gate.json')     # what the model got last, for StarView / debugging
DRIVER_LANE_CHANGE_TAIL_S = 1.5
_ACTIVE_LANE_CHANGE = (log.LaneChangeState.laneChangeStarting, log.LaneChangeState.laneChangeFinishing)


def nav_horizon_m(path: Path = NAV_HORIZON_FILE) -> float:
  """How far ahead (m) the next turn may be for the model to get the route; inf when the file says 0."""
  try:
    value = float(path.read_text().strip())
  except (OSError, ValueError):
    return DEFAULT_NAV_HORIZON_M
  if not math.isfinite(value) or value < 0:
    return DEFAULT_NAV_HORIZON_M
  return math.inf if value == 0 else value


def next_turn_distance(navigation: np.ndarray | None) -> float | None:
  """Distance (m) to the maneuver in the model's navigation input, None when it holds none."""
  if navigation is None or not np.any(navigation[:-1] > 0):
    return None
  return float(navigation[-1]) * 100.0


class DriverLaneChange:
  """True while a lane change the driver started is running, and DRIVER_LANE_CHANGE_TAIL_S after."""
  def __init__(self):
    self.until = 0.0

  def update(self, lane_change_state, by_system: bool, now: float) -> bool:
    if lane_change_state in _ACTIVE_LANE_CHANGE and not by_system:
      self.until = now + DRIVER_LANE_CHANGE_TAIL_S
    return now < self.until


def gate_nav_inputs(nav_inputs: dict, horizon_m: float, driver_lane_change: bool) -> tuple[dict, str]:
  """The inputs to give the model and why some were held back ('' = all given)."""
  if not nav_inputs:
    return nav_inputs, ""
  if driver_lane_change:
    return {}, "driver lane change"
  if math.isfinite(horizon_m):
    distance = next_turn_distance(nav_inputs.get("navigation"))
    if distance is None:
      return {}, "no turn ahead"
    if distance > horizon_m:
      return {}, f"next turn beyond {horizon_m:.0f} m"
  return nav_inputs, ""


def write_gate_status(reason: str, navigation: np.ndarray | None, path: Path = NAV_GATE_STATUS_FILE) -> None:
  """Write what the model gets now (on change only), for StarView and for reading back after a drive."""
  try:
    distance = next_turn_distance(navigation)
    command = int(np.argmax(navigation[:-1])) if distance is not None else None
    path.write_text(json.dumps({"destination": navigation is not None, "routeGiven": reason == "" and navigation is not None,
                                "reason": reason, "nextTurnType": command,
                                "nextTurnM": None if distance is None else round(distance), "t": datetime.now(UTC).timestamp()}))
  except Exception:
    pass
