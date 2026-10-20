"""The StarView tablet's navigation map, on StarPilot 7's own navigation (starpilot/navigation).

  tablet --control "nav_state" {routeKey?, detailKey?}--> destination, status, the route choices (time, usual time,
                                     distance, "via", road kinds), the chosen one, the route options, and - only when
                                     they changed - each route's full line, live traffic, closures, incidents and steps
         --control "nav_set" {name, address?, latitude, longitude}   StarPilot's destination (Galaxy's way: owner.select)
         --control "nav_cancel"                                      ends the route
         --control "nav_route" {index}                               drive another of the offered routes
         --control "nav_options" {avoidTolls: true, carpool: 2, ...} route options (upstream's three + StarView's)
         --control "nav_list"                                        favourites and recent destinations
         --GET /nav/tile/{style}/{z}/{x}/{y}.png-->                  Mapbox map tiles through owner.map_tile (cached,
                                                                     counted in the comma's Mapbox usage)
navigationd plans the route, offers the alternatives, follows the drive and asks again for live traffic every 5 minutes
(runtime.py); this module only reads its results and changes its settings, like Galaxy does.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading

from openpilot.starpilot.navigation.owner import (ConflictError, NavigationOwner, ROUTE_AVOIDANCES, ROUTE_MORE_KEYS,
                                                  ValidationError, route_more)
from openpilot.starpilot.navigation.wire import navigation_state

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

  def search_position(self):
    return None

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

  @property
  def owner(self) -> NavigationOwner:
    with self._lock:
      if self._owner is None:
        self._owner = NavigationOwner(runtime_source=_HubNavigation(self._newest))
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
    out["routeKey"] = _key([out["revision"], routes, out["selectedRoute"], out["status"], out["destination"]])
    out["detailKey"] = _key([(r["durationSeconds"], r["distanceMeters"]) for r in routes] +
                            [hashlib.sha256((x or {}).get("polyline", "").encode()).hexdigest()[:8] + _key((x or {}).get("traffic"))
                             for x in lines])
    if route_key is not None and route_key == out["routeKey"] and detail_key == out["detailKey"]:
      return {"ok": True, "unchanged": True, "routeKey": route_key, "detailKey": out["detailKey"]}
    if detail_key is None or detail_key != out["detailKey"]:
      out["details"] = lines
    return out

  def lists(self) -> dict:
    doc = self.owner.read()
    return {"ok": True, "favorites": doc.get("favorites", []), "recents": doc.get("recents", [])}

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


def remove_leftovers() -> None:
  for path in OLD_FILES:
    try:
      os.unlink(path)
    except OSError:
      pass
  for path in OLD_DIRS:
    shutil.rmtree(path, ignore_errors=True)
