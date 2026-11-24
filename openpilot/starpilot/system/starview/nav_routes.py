"""StarView's navigation additions, beside upstream's (fork patches 9-12, 28, 76: CLAUDE.md "Fork history" 7, 17, 45).

Upstream's navigation files only call in here, so a sync meets a few hook lines instead of our logic:
  route_engine.py  NavigationRoute keeps `details(...)` (StarView's map: traffic along the route, closures, incidents,
                   the turn-by-turn list with lanes, spoken guidance, the full line); MapboxRouteEngine.fetch asks
                   through `fetch_json(...)` (traffic and voice annotations, StarView's route options, Mapbox's beta
                   exclusions dropped when refused)
  owner.py         MAP_STYLES gets TRAFFIC_STYLES; routing_fields count ROUTE_MORE_KEYS; record_routes calls
                   `record_details`; Google tiles for the traffic styles via `google_theme`; Mapbox search rows get
                   `search_extras` (distance, maki icon, category)
  runtime.py       route_exclusions (upstream's three options + ours), and the live-traffic refresh every REFRESH_NS
                   with keep_road / fastest_first (that state stays in RouteRuntime.update, marked "fork")
  google_places.py autocomplete's `google_origin` (distances) and `google_row` (distance, icon, category)
StarView's own callers (nav_link.py) use route_more, route_exclusions, offered_details and configure_more here.
Standard library only at import: upstream's navigation modules import this one, so theirs are imported in functions.
"""
import json
import math
import os
import tempfile
import time
from pathlib import Path


def owner_module():
  from openpilot.starpilot.navigation import owner   # owner.py imports this module
  return owner


# ---- route options (owner.py, runtime.py, nav_link.py)

# StarView's further route options, beside upstream's three (missing in older settings = off). Carpool lanes (HOV) are
# left out of routes unless the car has the people for them; express lanes (HOT) charge a toll below that.
ROUTE_MORE_AVOIDANCES = {'avoidUnpaved': 'unpaved', 'avoidCashTolls': 'cash_only_tolls', 'avoidTunnels': 'tunnel',
                         'avoidBorders': 'country_border'}
CARPOOL_INCLUDES = {0: (), 2: ('hov2',), 3: ('hov2', 'hov3')}
ROUTE_MORE_KEYS = (*ROUTE_MORE_AVOIDANCES, 'carpool', 'expressLanes')


def route_more(settings: dict) -> dict:
  carpool = settings.get('carpool')
  return {**{key: settings.get(key) is True for key in ROUTE_MORE_AVOIDANCES},
          'carpool': carpool if type(carpool) is int and carpool in CARPOOL_INCLUDES else 0,
          'expressLanes': settings.get('expressLanes') is True}


def route_exclusions(settings: dict) -> tuple[str, ...]:
  """Mapbox `exclude` values for the saved route options; `include` values carry a leading '+'."""
  from openpilot.starpilot.navigation.owner import ROUTE_AVOIDANCES
  more = route_more(settings)
  values = [value for key, value in ROUTE_AVOIDANCES.items() if settings.get(key) is True]
  values += [value for key, value in ROUTE_MORE_AVOIDANCES.items() if more[key]]
  values += ['+' + value for value in CARPOOL_INCLUDES[more['carpool']]]
  if more['expressLanes'] and settings.get('avoidTolls') is not True:
    values.append('+hot')
  return tuple(values)

# StarView's map: Mapbox's navigation styles, with live traffic drawn on every road
TRAFFIC_STYLES = {'trafficLight': 'mapbox/navigation-day-v1', 'trafficDark': 'mapbox/navigation-night-v1'}


def google_theme(theme: str) -> str:
  """owner.py's Google tiles: StarView's traffic styles are Mapbox's; Google draws them as its light / dark map."""
  return 'light' if theme in ('light', 'trafficLight') else 'dark'


def search_extras(row: dict, item: dict) -> dict:
  """owner.py's Mapbox search rows, for StarView's search list: how far, and what kind of place."""
  if type(item.get('distance')) in (int, float) and math.isfinite(item['distance']):
    row['distanceMeters'] = float(item['distance'])
  if isinstance(item.get('maki'), str):
    row['maki'] = item['maki'][:40]
  if isinstance(item.get('poi_category'), list) and item['poi_category'] and isinstance(item['poi_category'][0], str):
    row['category'] = item['poi_category'][0][:60]
  return row


# ---- the routes last offered, with their details (owner.py's record_routes; StarView's map reads them)


def offered_details(owner) -> list[dict]:
  """Traffic, incidents, steps and full geometry of the routes last offered (StarView's map), matched to
  route_options() rows by distance and duration."""
  try:
    value = json.loads((owner.transient_root / 'routes.detail').read_text())
    return value['routes'] if time.monotonic() < value['expires'] else []
  except (OSError, ValueError, KeyError, TypeError):
    return []


def record_details(owner, routes):
  rows = [dict(getattr(route, 'details', None) or {}, durationSeconds=route.total_duration, distanceMeters=route.total_distance)
          for route in routes]
  fd, name = tempfile.mkstemp(dir=owner.transient_root, prefix='.details-')
  try:
    with os.fdopen(fd, 'w') as out:
      json.dump({'expires': time.monotonic() + owner_module().ACTIVE_TTL, 'routes': rows}, out, allow_nan=False, separators=(',', ':'))
    os.replace(name, owner.transient_root / 'routes.detail')
  except (OSError, ValueError, TypeError):
    pass
  finally:
    Path(name).unlink(missing_ok=True)


def configure_more(owner, patch: dict, expected_revision: str, authorized) -> dict:
  """StarView's further route options (ROUTE_MORE_KEYS); a change asks for new routes like upstream's options."""
  if not isinstance(patch, dict) or not patch or set(patch) - set(ROUTE_MORE_KEYS):
    raise owner_module().ValidationError('Unknown navigation setting')
  if any(type(patch[key]) is not bool for key in patch if key != 'carpool'):
    raise owner_module().ValidationError('Route avoidance settings must be on or off')
  if 'carpool' in patch and (type(patch['carpool']) is not int or patch['carpool'] not in CARPOOL_INCLUDES):
    raise owner_module().ValidationError('Carpool lanes are off, 2+ or 3+ people')
  def update(value):
    if any(patch[key] != route_more(value)[key] for key in patch):
      value['routeChoice'] = 0
    value.update(patch)
  return owner._change(update, expected_revision, authorized, preserve_active=True)


# ---- route details (route_engine.py)


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
  from openpilot.starpilot.navigation.route_engine import modifier   # route_engine imports this module
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


def details(data: dict, points, cumulative) -> dict:
  """NavigationRoute's hook. Optional: a route without them still drives."""
  try:
    return route_details(data, points, cumulative)
  except (KeyError, TypeError, IndexError, AttributeError, ValueError):
    return {}


def fetch_json(engine, url: str, params: dict, exclusions, response_json) -> dict:
  """MapboxRouteEngine.fetch's request: upstream's params plus traffic and spoken guidance, StarView's options split into
  `exclude` and `include`. Mapbox's beta exclusions and lane includes can be refused: then the route is asked again
  without them rather than not at all. response_json: upstream's request (owner.py)."""
  params.update({'annotations': 'congestion,closure', 'voice_instructions': 'true', 'voice_units': _voice_units()})
  exclude, include = _request_values(exclusions)
  params.pop('exclude', None)
  if exclude:
    params['exclude'] = ','.join(exclude)
  if include:
    params['include'] = ','.join(include)
  try:
    return response_json(engine.session, url, params)
  except owner_module().ValidationError:
    if not include and not any(value in BETA_EXCLUSIONS for value in exclude):
      raise
    stable = [value for value in exclude if value not in BETA_EXCLUSIONS]
    if stable:
      params['exclude'] = ','.join(stable)
    else:
      params.pop('exclude', None)
    params.pop('include', None)
    if engine.budget is not None:
      engine.budget.spend(enforce=False)
    return response_json(engine.session, url, params)


# ---- the live-traffic refresh while guiding (runtime.py)


REFRESH_NS = 300_000_000_000    # while guiding, routes are asked again this often for live traffic and arrival time


def _cells(points, step=25.):
  """Grid cells (about 33 m) a route line passes through, filled in every `step` metres."""
  from openpilot.starpilot.navigation.route_engine import distance
  cells = set()
  for a, b in zip(points, points[1:], strict=False):
    count = max(1, int(distance(a, b) / step))
    for k in range(count + 1):
      cells.add((round((a[0] + (b[0] - a[0]) * k / count) * 3000), round((a[1] + (b[1] - a[1]) * k / count) * 3000)))
  return cells


def _slot(choice, count: int) -> int:
  # where the driven route sits: the chosen index, or 0 when that index is gone (the runtime then drives routes[0])
  return choice if type(choice) is int and 0 <= choice < count else 0


def keep_road(current, current_along: float, routes: list, choice) -> list:
  """Refreshed routes ordered so the one that follows the road being driven takes the driven route's place: a traffic
  refresh updates times and traffic without moving the driver onto another road. current_along: metres along
  `current`'s line. The whole rest of the driven route is compared (alternatives often share the first miles); a tie
  goes to the route whose length is closest to what is left."""
  ahead = [p for p, along in zip(current.points, current.cumulative, strict=False) if along >= current_along]
  if len(routes) < 2 or len(ahead) < 2:
    return routes
  samples = ahead[::max(1, len(ahead) // 120)] + [ahead[-1]]
  remaining = current.cumulative[-1] - current_along

  def score(index):
    route = routes[index]
    cells = _cells(route.points, step=max(25., route.cumulative[-1] / 20000.))
    near = sum(any((round(lon * 3000) + i, round(lat * 3000) + j) in cells for i in (-1, 0, 1) for j in (-1, 0, 1)) for lon, lat in samples)
    return round(near / len(samples), 2), -abs(route.cumulative[-1] - remaining)
  best = max(range(len(routes)), key=score)
  ordered = [route for index, route in enumerate(routes) if index != best]
  ordered.insert(_slot(choice, len(routes)), routes[best])
  return ordered


def fastest_first(routes: list, choice) -> list:
  """After leaving the route, Mapbox's best new route goes where the driven one is (not an arbitrary alternative)."""
  slot = _slot(choice, len(routes))
  return routes if slot == 0 or len(routes) < 2 else [*routes[1:slot + 1], routes[0], *routes[slot + 1:]]


# ---- Google place suggestions (google_places.py)

# Google's place types as the Mapbox (maki) icon names StarView's search list draws
MAKI = {"gas_station": "fuel", "electric_vehicle_charging_station": "charging-station", "cafe": "cafe", "coffee_shop": "cafe",
        "restaurant": "restaurant", "fast_food_restaurant": "fast-food", "bakery": "bakery", "bar": "bar", "parking": "parking",
        "supermarket": "grocery", "grocery_store": "grocery", "convenience_store": "shop", "store": "shop", "shopping_mall": "shop",
        "pharmacy": "pharmacy", "drugstore": "pharmacy", "hospital": "hospital", "doctor": "doctor", "lodging": "lodging",
        "hotel": "lodging", "school": "school", "university": "college", "bank": "bank", "atm": "bank", "airport": "airport",
        "park": "park", "car_repair": "car-repair", "car_wash": "car", "car_dealer": "car", "post_office": "post",
        "library": "library", "museum": "museum", "place_of_worship": "place-of-worship", "synagogue": "religious-jewish",
        "church": "religious-christian", "mosque": "religious-muslim", "train_station": "rail", "subway_station": "rail-metro",
        "bus_station": "bus", "gym": "fitness-centre", "police": "police", "fire_station": "fire-station", "zoo": "zoo"}
GENERIC_TYPES = {"point_of_interest", "establishment", "geocode", "premise", "street_address", "route", "political",
                 "locality", "sublocality", "neighborhood", "food", "store"}


def google_origin(body: dict, proximity) -> None:
  """google_places.autocomplete: with an origin Google gives each suggestion's distance (same request, same SKU)."""
  if proximity is not None:
    body["origin"] = {"latitude": proximity[1], "longitude": proximity[0]}


def google_row(row: dict, prediction: dict) -> dict:
  """google_places.autocomplete's rows, for StarView's search list: how far, and what kind of place."""
  distance = prediction.get("distanceMeters")
  if type(distance) in (int, float) and math.isfinite(distance) and distance >= 0:
    row["distanceMeters"] = float(distance)
  kinds = prediction.get("types")
  if isinstance(kinds, list):
    kinds = [k for k in kinds if isinstance(k, str)]
    maki = next((MAKI[k] for k in kinds if k in MAKI), None)
    if maki:
      row["maki"] = maki
    named = next((k for k in kinds if k not in GENERIC_TYPES), None)
    if named:
      row["category"] = named.replace("_", " ").capitalize()[:60]
  return row
