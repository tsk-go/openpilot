from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
import math

from openpilot.starpilot.navigation.owner import ValidationError, response_json

EARTH_RADIUS = 6371007.2
MAX_POINTS = 20000


def point(value) -> tuple[float, float]:
  if (not isinstance(value, (list, tuple)) or len(value) < 2 or
      any(type(v) not in (int, float) or not math.isfinite(v) for v in value[:2]) or
      not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90):
    raise ValidationError('The route contains invalid coordinates')
  return float(value[0]), float(value[1])


def distance(a, b) -> float:
  lat1, lat2 = math.radians(a[1]), math.radians(b[1])
  h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b[0] - a[0]) / 2) ** 2
  return 2 * EARTH_RADIUS * math.asin(math.sqrt(min(1., max(0., h))))


def project(a, b, p) -> tuple[float, float]:
  latitude_scale = EARTH_RADIUS * math.pi / 180
  longitude_scale = latitude_scale * math.cos(math.radians((a[1] + b[1] + p[1]) / 3))
  x, y = (b[0] - a[0]) * longitude_scale, (b[1] - a[1]) * latitude_scale
  px, py = (p[0] - a[0]) * longitude_scale, (p[1] - a[1]) * latitude_scale
  fraction = min(1., max(0., (px * x + py * y) / (x * x + y * y))) if x * x + y * y > 1e-6 else 0.
  return fraction, math.hypot(px - fraction * x, py - fraction * y)


def number(value, maximum=1e8) -> float:
  if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
    raise ValidationError('The route contains invalid distances')
  return float(value)


def modifier(value) -> str:
  return str(value).replace('slight left', 'slightLeft').replace('slight right', 'slightRight').replace(
    'sharp left', 'sharpLeft').replace('sharp right', 'sharpRight')


@dataclass(frozen=True)
class Step:
  start: float
  end: float
  duration: float
  text: str
  maneuver_type: str
  modifier: str


@dataclass(frozen=True)
class Progress:
  instruction: dict
  next_maneuver: dict
  off_route: bool
  arrived: bool


class NavigationRoute:
  def __init__(self, data: dict):
    try:
      coordinates = data['geometry']['coordinates']
      if not 2 <= len(coordinates) <= MAX_POINTS:
        raise ValidationError('The route is too long')
      self.points = [point(row) for row in coordinates]
      self.cumulative = [0.]
      for a, b in zip(self.points, self.points[1:], strict=False):
        self.cumulative.append(self.cumulative[-1] + distance(a, b))
      steps = data['legs'][0]['steps']
      if not 1 <= len(steps) <= 2048:
        raise ValidationError('The route has too many instructions')
      self.steps = []
      offset = 0.
      for index, step in enumerate(steps):
        end = offset + number(step['distance'])
        maneuver = steps[min(index + 1, len(steps) - 1)]['maneuver']
        banners = step.get('bannerInstructions', [])
        primary = banners[0].get('primary', {}) if banners else {}
        text = str(primary.get('text') or maneuver.get('instruction', ''))[:256]
        self.steps.append(Step(offset, end, number(step['duration']), text,
                               str(primary.get('type') or maneuver['type'])[:40],
                               modifier(primary.get('modifier') or maneuver.get('modifier', 'none'))[:40]))
        offset = end
      self.total_distance = number(data['distance'])
      self.total_duration = number(data['duration'])
      if self.total_distance < 1 or offset < 1:
        raise ValidationError('The route is empty')
      self.starts = [step.start for step in self.steps]
    except (KeyError, TypeError, IndexError, AttributeError):
      raise ValidationError('The map service returned an incomplete route') from None
    # StarView's map: traffic, incidents and the step list. Optional: a route without them still drives.
    try:
      self.details = route_details(data, self.points, self.cumulative)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError):
      self.details = {}

  def preview(self) -> list[dict]:
    stride = max(1, math.ceil((len(self.points) - 1) / 511))
    points = self.points[::stride]
    if points[-1] != self.points[-1]:
      points.append(self.points[-1])
    return [{'longitude': x, 'latitude': y} for x, y in points]

  def progress(self, position, speed: float, bearing: float | None = None) -> Progress:
    best = (float('inf'), 0., 0)
    for index, (a, b) in enumerate(zip(self.points, self.points[1:], strict=False)):
      fraction, separation = project(a, b, position)
      along = self.cumulative[index] + fraction * (self.cumulative[index + 1] - self.cumulative[index])
      if separation < best[0]:
        best = separation, along, index
    separation, along, segment = best
    # Directions step lengths and geometry lengths can differ slightly.
    along *= self.steps[-1].end / max(self.cumulative[-1], 1.)
    index = min(len(self.steps) - 1, max(0, bisect_right(self.starts, along + .001) - 1))
    step = self.steps[index]
    remaining = max(0., step.end - along)
    duration = step.duration * min(1., remaining / max(step.end - step.start, 1.))
    duration += sum(row.duration for row in self.steps[index + 1:])
    instruction = {'text': step.text, 'maneuverType': step.maneuver_type, 'maneuverModifier': step.modifier,
                       'distanceMeters': remaining, 'remainingDistanceMeters': max(0., self.steps[-1].end - along),
                       'remainingDurationSeconds': duration}
    upcoming = self.steps[min(index + 1, len(self.steps) - 1)]
    next_maneuver = {'maneuverType': upcoming.maneuver_type, 'maneuverModifier': upcoming.modifier,
                         'distanceMeters': max(0., upcoming.end - along)}
    speeds, distances = (0., 5., 10., 20., 40.), (40., 50., 60., 80., 100.)
    bucket = min(3, max(0, bisect_right(speeds, speed) - 1))
    fraction = min(1., max(0., (speed - speeds[bucket]) / (speeds[bucket + 1] - speeds[bucket])))
    threshold = distances[bucket] + fraction * (distances[bucket + 1] - distances[bucket])
    misaligned = False
    if bearing is not None and speed >= 2.5:
      a, b = self.points[segment], self.points[segment + 1]
      lat1, lat2, delta = math.radians(a[1]), math.radians(b[1]), math.radians(b[0] - a[0])
      direction = math.degrees(math.atan2(math.sin(delta) * math.cos(lat2),
                              math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta)))
      misaligned = abs((direction - bearing + 180) % 360 - 180) > 75
    arrived = speed < 2 and distance(position, self.points[-1]) < 40 and instruction['remainingDistanceMeters'] < 40
    return Progress(instruction, next_maneuver, separation > threshold or misaligned, arrived)


CONGESTION = {'unknown': 0, 'low': 1, 'moderate': 2, 'heavy': 3, 'severe': 4}
CLOSED = 5
# Values sent to Mapbox's `exclude` that are still beta: a route request refused with them is asked again without them.
BETA_EXCLUSIONS = ('tunnel', 'country_border')


def encode_polyline(points) -> str:
  """Google's encoded polyline (precision 5, ~1 m): a 20000-point route in about 100 kB instead of 600 kB of JSON."""
  out, last = [], (0, 0)
  for lon, lat in points:
    now = (round(lat * 1e5), round(lon * 1e5))
    for value in (now[0] - last[0], now[1] - last[1]):
      value = ~(value << 1) if value < 0 else value << 1
      while value >= 0x20:
        out.append(chr((0x20 | (value & 0x1f)) + 63))
        value >>= 5
      out.append(chr(value + 63))
    last = now
  return ''.join(out)


def _text(value, limit=160) -> str:
  return value.strip()[:limit] if isinstance(value, str) else ''


def _lanes(leg, index) -> list:
  try:
    return _lane_list(leg, index)
  except (AttributeError, TypeError, KeyError, IndexError):
    return []   # lanes are a nicety: never lose the route's details over them


def _lane_list(leg, index) -> list:
  """The lanes at step `index`'s maneuver, as Waze / Google Maps show them: [{"d": arrows, "ok": a lane for the route,
  "use": its arrow}]. From the banner shown before the maneuver (Mapbox's lane guidance), else the intersection."""
  out = []
  if index:
    for banner in leg['steps'][index - 1].get('bannerInstructions') or []:
      for part in ((banner.get('sub') or {}).get('components') or []):
        if part.get('type') == 'lane' and isinstance(part.get('directions'), list):
          d = [_text(v, 20) for v in part['directions'][:4] if isinstance(v, str)]
          use = part.get('active_direction') if isinstance(part.get('active_direction'), str) else (d[0] if d and part.get('active') else '')
          out.append({'d': d, 'ok': part.get('active') is True, 'use': _text(use, 20)})
      if out:
        break
  if not out:
    crossings = leg['steps'][index].get('intersections') or []
    for lane in (crossings[0].get('lanes') or []) if crossings else []:
      d = [_text(v, 20) for v in (lane.get('indications') or [])[:4] if isinstance(v, str)]
      ok = lane.get('valid') is True
      use = lane.get('valid_indication') if isinstance(lane.get('valid_indication'), str) else (d[0] if d and ok else '')
      out.append({'d': d, 'ok': ok, 'use': _text(use, 20)})
  return out[:12] if len(out) >= 2 else []


def route_details(data: dict, points, cumulative) -> dict:
  """What the StarView tablet's map shows beside the route line: live traffic along it (distance runs), closures,
  incidents, the turn-by-turn list, what kind of roads it uses and how long it usually takes."""
  leg = data['legs'][0]
  last = len(points) - 1
  # in Mapbox's step metres, like the steps and progress() (the line's own length differs a little)
  scale = sum(float(step['distance']) for step in leg['steps']) / max(cumulative[-1], 1.)
  cumulative = [value * scale for value in cumulative]

  def along(index):
    return cumulative[min(max(int(index), 0), last)]

  levels = (leg.get('annotation') or {}).get('congestion') or []
  closed = [0] * max(0, last)
  for row in leg.get('closures') or []:
    for index in range(max(0, int(row['geometry_index_start'])), min(last, int(row['geometry_index_end']))):
      closed[index] = 1
  traffic = []
  for index in range(last):
    level = CLOSED if closed[index] else CONGESTION.get(levels[index], 0) if index < len(levels) else 0
    if traffic and traffic[-1][2] == level:
      traffic[-1][1] = round(cumulative[index + 1], 1)
    else:
      traffic.append([round(cumulative[index], 1), round(cumulative[index + 1], 1), level])
  if len(traffic) == 1 and traffic[0][2] == 0:
    traffic = []
  incidents = []
  for row in (leg.get('incidents') or [])[:40]:
    start = int(row.get('geometry_index_start', 0))
    point = points[min(max(start, 0), last)]
    incidents.append({'id': _text(str(row.get('id', '')), 64), 'type': _text(row.get('type'), 40),
                      'subType': _text(row.get('sub_type'), 40), 'impact': _text(row.get('impact'), 20),
                      'description': _text(row.get('description')), 'closed': row.get('closed') is True,
                      'startMeters': round(along(start), 1), 'endMeters': round(along(row.get('geometry_index_end', start)), 1),
                      'longitude': round(point[0], 6), 'latitude': round(point[1], 6)})
  steps, classes, voice, offset = [], set(), [], 0.
  for index, step in enumerate(leg['steps'][:2048]):
    # Mapbox's spoken guidance, timed for the road: [metres from the start where it is said, words]
    for row in step.get('voiceInstructions') or []:
      if len(voice) < 600 and isinstance(row.get('announcement'), str) and type(row.get('distanceAlongGeometry')) in (int, float):
        voice.append([round(offset + max(0., float(step['distance']) - float(row['distanceAlongGeometry'])), 1), row['announcement'].strip()[:300]])
    maneuver = step['maneuver']
    for crossing in step.get('intersections') or []:
      classes.update(value for value in crossing.get('classes') or [] if value in ('toll', 'motorway', 'ferry', 'tunnel', 'restricted'))
    location = maneuver.get('location') or points[0]
    previous = leg['steps'][index - 1].get('bannerInstructions') if index else None
    text = maneuver.get('instruction') or (previous[-1].get('primary', {}).get('text') if previous else None) or ''
    steps.append({'text': _text(text, 256), 'type': _text(maneuver.get('type'), 40), 'modifier': _text(modifier(maneuver.get('modifier', '')), 40),
                  'road': _text(step.get('name'), 120), 'ref': _text(step.get('ref'), 60), 'startMeters': round(offset, 1),
                  'distanceMeters': round(float(step['distance']), 1), 'durationSeconds': round(float(step['duration']), 1),
                  'longitude': round(float(location[0]), 6), 'latitude': round(float(location[1]), 6), 'lanes': _lanes(leg, index)})
    offset += float(step['distance'])
  typical = data.get('duration_typical')
  return {'via': _text(leg.get('summary'), 120), 'typicalSeconds': float(typical) if type(typical) in (int, float) and math.isfinite(typical) else None,
          'classes': sorted(classes), 'traffic': traffic, 'incidents': incidents, 'steps': steps, 'voice': voice,
          'polyline': encode_polyline(points)}


def _voice_units() -> str:
  try:
    from openpilot.common.params import Params
    return 'metric' if Params().get_bool('IsMetric') else 'imperial'
  except Exception:
    return 'imperial'


def _request_values(exclusions):
  """exclusions: Mapbox `exclude` values, and `include` values marked with a leading '+' (carpool / express lanes)."""
  return [value for value in exclusions if not value.startswith('+')], [value[1:] for value in exclusions if value.startswith('+')]


class MapboxRouteEngine:
  def __init__(self, session, budget=None):
    self.session = session
    self.budget = budget  # MonthlyBudget for directions; None in tests

  def fetch(self, token: str, position, destination: dict, bearing: float | None = None,
            exclusions: tuple[str, ...] = ()) -> NavigationRoute:
    if self.budget is not None:
      self.budget.spend(enforce=False)  # upstream routing: counted for Setup, never refused
    url = ('https://api.mapbox.com/directions/v5/mapbox/driving-traffic/' +
           f'{position[0]},{position[1]};{destination["longitude"]},{destination["latitude"]}')
    params = {'access_token': token, 'geometries': 'geojson', 'steps': 'true', 'overview': 'full', 'banner_instructions': 'true', 'alternatives': 'true',
              'annotations': 'congestion,closure', 'voice_instructions': 'true', 'voice_units': _voice_units()}
    exclude, include = _request_values(exclusions)
    if exclude:
      params['exclude'] = ','.join(exclude)
    if include:
      params['include'] = ','.join(include)
    if bearing is not None:
      params['bearings'] = f'{int(bearing % 360)},90;'
    try:
      data = response_json(self.session, url, params)
    except ValidationError:
      if not include and not any(value in BETA_EXCLUSIONS for value in exclude):
        raise
      # Mapbox's beta exclusions and lane includes can be refused: route without them rather than not at all.
      stable = [value for value in exclude if value not in BETA_EXCLUSIONS]
      if stable:
        params['exclude'] = ','.join(stable)
      else:
        params.pop('exclude', None)
      params.pop('include', None)
      if self.budget is not None:
        self.budget.spend(enforce=False)
      data = response_json(self.session, url, params)
    if data.get('code') != 'Ok' or not data.get('routes'):
      raise ValidationError('No driving route was found')
    routes = [NavigationRoute(row) for row in data['routes'][:3]]
    routes[0].alternatives = routes
    return routes[0]
