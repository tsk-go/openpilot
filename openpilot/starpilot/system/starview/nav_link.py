"""The StarView tablet's navigation map, on StarPilot 7's own navigation (starpilot/navigation).

  tablet --control "nav_state" {routeKey?, detailKey?}--> destination, status, the route choices (time, usual time,
                                     distance, "via", road kinds), the chosen one, the route options, and - only when
                                     they changed - each route's full line, live traffic, closures, incidents and steps
         --control "nav_set" {name, address?, latitude, longitude}   StarPilot's destination (Galaxy's way: owner.select)
         --control "nav_cancel"                                      ends the route
         --control "nav_route" {index}                               drive another of the offered routes
         --control "nav_options" {avoidTolls: true, carpool: 2, ...} route options (upstream's three + StarView's)
         --control "nav_list"                                        favourites and recent destinations
         --control "nav_favorite" {name, address?, latitude, longitude, label?}   save a place (label home / work)
         --control "nav_unfavorite" {id} / "nav_label" {id, label}   remove a saved place / make it Home or Work
         --control "nav_search" {query, searchId, clientId, latitude?, longitude?}   places as you type (Mapbox Search
                                     Box, one billed session per search; near the car)
         --control "nav_pick" {id, searchId}                         drive to a place from those results
         --control "nav_category" {category, latitude, longitude, route?}   gas, EV charging, coffee, food ... near the car,
                                     or along the route (route: encoded polyline of the road ahead)
         --GET /nav/tile/{style}/{z}/{x}/{y}.png-->                  Mapbox map tiles through owner.map_tile (cached,
                                                                     counted in the comma's Mapbox usage)
         --control "nav_tiles" {count}                               tiles the tablet fetched from Mapbox itself (with
                                                                     the key nav_state gives it), added to that count
navigationd plans the route, offers the alternatives, follows the drive and asks again for live traffic every 5 minutes
(runtime.py); this module only reads its results and changes its settings, like Galaxy does.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import threading
import time

from openpilot.starpilot.navigation.owner import (ConflictError, NavigationOwner, ROUTE_AVOIDANCES, ROUTE_MORE_KEYS,
                                                  ValidationError, response_json, route_more)
from openpilot.starpilot.navigation.wire import navigation_state

CALLER = "starview"
SEARCH_URL = "https://api.mapbox.com/search/searchbox/v1"
# the tablet's quick searches -> Mapbox canonical categories (the first one Mapbox lists is used)
CATEGORIES = {
  "gas": ("gas_station",), "ev": ("charging_station", "ev_charging_station", "electric_vehicle_charging_station"),
  "coffee": ("coffee", "cafe", "coffee_shop"), "food": ("restaurant", "food"), "fast_food": ("fast_food", "fast_food_restaurant"),
  "parking": ("parking_lot", "parking", "parking_garage"), "grocery": ("grocery", "supermarket", "grocery_store"),
  "pharmacy": ("pharmacy", "drugstore"), "hotel": ("hotel", "lodging"), "rest_area": ("rest_area", "rest_stop"),
}
CATEGORY_WORDS = {"gas": "gas station", "ev": "EV charging", "coffee": "coffee", "food": "restaurant", "fast_food": "fast food",
                  "parking": "parking", "grocery": "grocery store", "pharmacy": "pharmacy", "hotel": "hotel", "rest_area": "rest area"}

TILE_STYLES = ("light", "dark", "trafficLight", "trafficDark")
# What the old Waze bridge left behind (StarView 2.48 has no Waze): removed once
OLD_FILES = ("/dev/shm/starview_waze.json", "/data/starview/waze_destination.json", "/data/starview/no_waze")
OLD_DIRS = ("/data/media/0/waze_logs",)


class _HubNavigation:
  """NavigationOwner's runtime source from starviewd's own starpilotNavigation reader (no extra msgq subscriber)."""

  def __init__(self, newest):
    self.newest = newest   # () -> the newest starpilotNavigation message reader (cereal NavigationState) or None

  def snapshot(self):
    try:
      nav = self.newest()
      state = navigation_state(_Envelope(nav)) if nav is not None else None
      if state is None:
        return None
      return {"revision": state.revision, "status": str(state.status),
              "instruction": state.instruction.to_dict() if str(state.status) in ("guiding", "arrived") else None, "route": []}
    except Exception:
      return None

  def map_position(self):
    return None   # the owner falls back to the saved last position

  position = None   # (lon, lat, monotonic time) the tablet sent with its last search

  def search_position(self):
    p = self.position
    return (p[0], p[1]) if p is not None and time.monotonic() - p[2] < 120 else None

  def network_status(self):
    return "unknown"


class _Envelope:
  def __init__(self, navigation):
    self.navigation = navigation


def _key(value) -> str:
  return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


class NavLink:
  def __init__(self, newest=None, owner: NavigationOwner | None = None):
    self._owner = owner
    self._newest = newest or (lambda: None)
    self._lock = threading.Lock()
    self._source = _HubNavigation(self._newest)
    self._category_ids = None   # Mapbox's category list (asked once)

  @property
  def owner(self) -> NavigationOwner:
    with self._lock:
      if self._owner is None:
        self._owner = NavigationOwner(runtime_source=self._source)
      return self._owner

  # ------------------------------------------------------------------ reads
  def state(self, route_key: str | None = None, detail_key: str | None = None) -> dict:
    owner = self.owner
    snap = owner.snapshot()
    document = owner.read()
    alternatives = snap.get("alternatives") or []
    details = owner.route_details()
    routes, lines = [], []
    for row in alternatives:
      index = row.get("index", len(routes))
      d = details[index] if index < len(details) else {}
      if d.get("distanceMeters") != row.get("distanceMeters") or d.get("durationSeconds") != row.get("durationSeconds"):
        d = {}
      incidents = d.get("incidents") or []
      routes.append({"index": index, "durationSeconds": row.get("durationSeconds"), "distanceMeters": row.get("distanceMeters"),
                     "typicalSeconds": d.get("typicalSeconds"), "via": d.get("via", ""), "classes": d.get("classes", []),
                     "incidents": len(incidents), "closed": any(i.get("closed") for i in incidents) or
                     any(run[2] == 5 for run in d.get("traffic") or [])})
      lines.append({key: d.get(key) for key in ("polyline", "traffic", "incidents", "steps")} if d else None)
    usage = snap.get("mapboxUsage") or {}
    # like navigationd: a choice past the routes offered now means the first one is driven
    selected = snap.get("selectedRoute", 0)
    selected = selected if type(selected) is int and 0 <= selected < max(len(routes), 1) else 0
    out = {"ok": True, "revision": snap.get("revision"), "status": snap.get("status"), "enabled": snap.get("enabled"),
           "hasKey": snap.get("hasKey"), "destination": snap.get("destination"), "selectedRoute": selected,
           "isMetric": snap.get("isMetric"), "routes": routes,
           "options": {**{key: document.get(key) is True for key in ROUTE_AVOIDANCES}, **route_more(document)},
           "usage": {k: usage[k] for k in ("directions", "staticTiles") if k in usage}}
    # the tablet fetches map tiles straight from Mapbox when it is online (the comma's link is often the slower one);
    # it reports how many (nav_tiles) so the month's count stays whole, and stops at the same free allowance
    tiles = owner.tile_budget
    if tiles.remaining() > 0 and document.get("token"):
      out["tileKey"] = document["token"]
    out["routeKey"] = _key([out["revision"], routes, out["selectedRoute"], out["status"], out["destination"], "tileKey" in out])
    out["detailKey"] = _key([(r["durationSeconds"], r["distanceMeters"]) for r in routes] +
                            [hashlib.sha256((x or {}).get("polyline", "").encode()).hexdigest()[:8] + _key((x or {}).get("traffic"))
                             for x in lines])
    if route_key is not None and route_key == out["routeKey"] and detail_key == out["detailKey"]:
      return {"ok": True, "unchanged": True, "routeKey": route_key, "detailKey": out["detailKey"]}
    if detail_key is None or detail_key != out["detailKey"]:
      out["details"] = lines
    return out

  def favorite(self, name, address, lat, lon, label=None) -> dict:
    """Save a place in StarPilot's favourites (shared with Galaxy). Mapbox search results can't be saved (their terms):
    the tablet saves those with the address from Android's own search."""
    try:
      lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
      raise ValidationError("latitude / longitude missing") from None
    value = {"name": str(name or address or "Saved place")[:256], "latitude": lat, "longitude": lon}
    if address and address != name:
      value["address"] = str(address)[:512]
    label = label if label in ("home", "work") else None
    self._change(lambda rev: self.owner.favorite(value, rev, True, label))
    return self.lists()

  def unfavorite(self, identity) -> dict:
    if not isinstance(identity, str) or not identity:
      raise ValidationError("Choose a saved place")
    self._change(lambda rev: self.owner.remove_favorite(identity, rev, True))
    return self.lists()

  def label(self, identity, label) -> dict:
    self._change(lambda rev: self.owner.label_favorite(identity, label if label in ("home", "work") else None, rev, True))
    return self.lists()

  def lists(self) -> dict:
    doc = self.owner.read()
    # Home and Work lead, then places in the order they were saved (as Galaxy lists them)
    order = {"home": 0, "work": 1}
    favorites = sorted(doc.get("favorites", []), key=lambda row: order.get(row.get("label"), 2))
    return {"ok": True, "favorites": favorites, "recents": doc.get("recents", [])}

  # ------------------------------------------------------------------ search
  def _near(self, lat, lon) -> None:
    try:
      lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
      return
    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
      self._source.position = (lon, lat, time.monotonic())

  def search(self, query, search_id, client_id, lat=None, lon=None) -> dict:
    """Places as the driver types (owner.search_places, autocomplete: one Mapbox session until a place is picked)."""
    self._near(lat, lon)
    if not isinstance(query, str) or len(query.strip()) < 2:
      return {"ok": True, "results": []}
    results = self.owner.search_places(query[:256], CALLER, search_id, client_id, autocomplete=True)
    return {"ok": True, "results": results}

  def pick(self, identity, search_id) -> dict:
    """A place from the search list becomes the destination (Mapbox's retrieve; kept as a temporary destination)."""
    self._change(lambda rev: self.owner.select_place(identity, search_id, CALLER, rev, True))
    return {"ok": True, "destination": self.owner.read_routing().get("destination")}

  def _categories(self, token) -> set:
    if self._category_ids is None:
      try:
        data = response_json(self.owner.session, f"{SEARCH_URL}/list/category", {"access_token": token, "language": "en"})
        self._category_ids = {row["canonical_id"] for row in data.get("listItems", []) if isinstance(row, dict) and isinstance(row.get("canonical_id"), str)}
      except (ValidationError, AttributeError, TypeError):
        return set()
    return self._category_ids

  def category(self, name, lat, lon, route=None) -> dict:
    """Places of a kind near the car, or along the route ahead (Mapbox category search; counted with the searches)."""
    from openpilot.starpilot.navigation.mapbox_budget import BudgetExhausted
    if name not in CATEGORIES:
      raise ValidationError("Unknown kind of place")
    self._near(lat, lon)
    position = self._source.search_position()
    if position is None:
      raise ValidationError("The car's position isn't known yet")
    token = self.owner.read()["token"]
    if not token:
      raise ValidationError("Add your Mapbox access token first")
    known = self._categories(token)
    canonical = next((c for c in CATEGORIES[name] if c in known), CATEGORIES[name][0])
    try:
      self.owner.search_budget.spend()
    except BudgetExhausted as error:
      raise ValidationError(str(error)) from None
    params = {"access_token": token, "limit": 15, "language": "en", "proximity": f"{position[0]:.6f},{position[1]:.6f}"}
    along = isinstance(route, str) and 10 <= len(route) <= 6000
    if along:
      params.update(sar_type="isochrone", route=route, route_geometry="polyline", time_deviation=8)
    try:
      data = response_json(self.owner.session, f"{SEARCH_URL}/category/{canonical}", params)
    except ValidationError:
      if not along:
        raise
      along = False
      for key in ("sar_type", "route", "route_geometry", "time_deviation"):
        params.pop(key)
      data = response_json(self.owner.session, f"{SEARCH_URL}/category/{canonical}", params)
    results = [row for row in (_place(f) for f in (data.get("features") or [])[:25]) if row is not None]
    return {"ok": True, "results": results, "alongRoute": along, "words": CATEGORY_WORDS[name]}

  def tiles_used(self, count) -> dict:
    """Map tiles the tablet fetched from Mapbox itself, added to the comma's count of the month's map views."""
    if type(count) is int and 0 < count <= 5000:
      self.owner.tile_budget.spend(count, enforce=False)
    return {"ok": True, "remaining": self.owner.tile_budget.remaining()}

  def tile(self, style: str, z: int, x: int, y: int) -> bytes:
    if style not in TILE_STYLES:
      raise ValidationError("Invalid map style")
    owner = self.owner
    if owner.tile_budget.remaining() <= 0:
      raise ValidationError("This month's free Mapbox map views are used up. They reset on the 1st.")
    return owner.map_tile(z, x, y, style)

  # ------------------------------------------------------------------ changes (retried when Galaxy changed something in between)
  def _change(self, fn):
    for _ in range(3):
      try:
        return fn(self.owner.read()["revision"])
      except ConflictError:
        continue
    raise RuntimeError("navigation kept changing")

  def set_destination(self, name: str, address: str, lat: float, lon: float) -> dict:
    value = {"name": (name or address or "Destination")[:256], "latitude": lat, "longitude": lon}
    if address and address != name:
      value["address"] = address[:512]
    self._change(lambda rev: self.owner.select(value, rev, True))
    return {"ok": True, "destination": self.owner.read()["destination"]}

  def cancel(self) -> dict:
    if self.owner.read_routing().get("destination") is not None:
      self._change(lambda rev: self.owner.clear(rev, True))
    return {"ok": True}

  def select_route(self, index) -> dict:
    if type(index) is not int:
      raise ValidationError("Choose a route")
    self._change(lambda rev: self.owner.select_route(index, rev, True))
    return {"ok": True, "selectedRoute": index}

  def options(self, patch: dict) -> dict:
    if not isinstance(patch, dict) or not patch:
      raise ValidationError("No route option given")
    upstream = {k: v for k, v in patch.items() if k in ROUTE_AVOIDANCES}
    more = {k: v for k, v in patch.items() if k in ROUTE_MORE_KEYS}
    if set(patch) - set(upstream) - set(more):
      raise ValidationError("Unknown route option")
    if upstream:
      self._change(lambda rev: self.owner.configure(upstream, rev, True))
    if more:
      self._change(lambda rev: self.owner.configure_more(more, rev, True))
    doc = self.owner.read()
    return {"ok": True, "options": {**{key: doc.get(key) is True for key in ROUTE_AVOIDANCES}, **route_more(doc)}}


def _place(feature) -> dict | None:
  try:
    p = feature["properties"]
    lon, lat = (float(v) for v in feature["geometry"]["coordinates"][:2])
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180) or not isinstance(p.get("name"), str):
      return None
    row = {"name": p["name"].strip()[:256], "address": str(p.get("full_address") or p.get("place_formatted") or "")[:512],
           "latitude": lat, "longitude": lon}
    if type(p.get("distance")) in (int, float) and math.isfinite(p["distance"]):
      row["distanceMeters"] = float(p["distance"])
    if isinstance(p.get("maki"), str):
      row["maki"] = p["maki"][:40]
    if isinstance(p.get("poi_category"), list) and p["poi_category"] and isinstance(p["poi_category"][0], str):
      row["category"] = p["poi_category"][0][:60]
    return row
  except (KeyError, TypeError, ValueError, IndexError):
    return None


def remove_leftovers() -> None:
  for path in OLD_FILES:
    try:
      os.unlink(path)
    except OSError:
      pass
  for path in OLD_DIRS:
    shutil.rmtree(path, ignore_errors=True)
