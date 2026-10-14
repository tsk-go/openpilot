"""Model inputs for navigation (ported from commaai/openpilot nav-model-integration, Oct 2026)."""
import re
import time
from typing import Any, NamedTuple

import numpy as np


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
