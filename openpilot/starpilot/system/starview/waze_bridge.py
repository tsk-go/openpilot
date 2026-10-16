"""Waze <-> StarPilot navigation bridge, on StarPilot 7.

  tablet (StarView, Waze reader) --POST /waze--> starviewd: WazeFeed.ingest()
     - parses the snapshot (waze_parser.py), writes /dev/shm/starview_waze.json (+ recordings for tuning)
     - Waze shows a route + its destination -> looked up with 7.0's own place search (NavigationOwner.search, near the
       last position) and set as StarPilot's destination (NavigationOwner.select), so the route (steps, turn desires,
       slowing for turns) is ready from the start of the drive. Waze's driving screen doesn't show the destination:
       it's on the bottom sheet, which the reader opens for a moment when the reply says needDestination.
     - Waze ends the route (on screen, not navigating, 15 s) -> a destination this bridge set is cleared again.
  WazeFeed.fields(nav_state): Waze's next maneuver against StarPilot's (street / distance / side) -> the waze* fields
     of the tablet's NavInstructionState (compat.py). The tablet's automatic turn signals only signal a turn Waze
     agrees with.

Not on 7.0 (yet): "Waze wins" (rerouting StarPilot through Waze's road on a lasting disagreement). 7.0's route engine
asks Mapbox for a single leg without via points.

Off switch on the comma: touch /data/starview/no_waze  (the tablet also has its own switch).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import threading
import time
from typing import Any

from openpilot.starpilot.system.starview import waze_parser


def _wall() -> float:
  # wall clock only for what people read (log names, times shown on the tablet); every timer uses time.monotonic()
  return time.time()  # noqa: TID251


STATE_PATH = "/dev/shm/starview_waze.json"
LOG_DIR = "/data/media/0/waze_logs"
LOG_CAP_BYTES = 300 * 1024 * 1024
OUR_DEST_PATH = "/data/starview/waze_destination.json"
OFF_FLAG = "/data/starview/no_waze"
FRESH_S = 3.0
END_CLEAR_S = 15.0
TABLET_GRACE_S = 90.0  # a destination StarView just set: Waze is still calculating / waiting for "Go" - don't clear it
GEOCODE_RETRY_S = 60.0   # address not found
NET_RETRY_S = 15.0       # network error
DISAGREE_LOG_S = 10.0


def _atomic_write(path: str, text: str) -> None:
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = f"{path}.tmp{os.getpid()}"
  with open(tmp, "w") as f:
    f.write(text)
  os.replace(tmp, path)


def _read_json(path: str) -> Any:
  try:
    with open(path) as f:
      return json.load(f)
  except Exception:
    return None


def _warn(msg: str) -> None:
  try:
    from openpilot.common.swaglog import cloudlog
    cloudlog.warning(f"waze: {msg}")
  except Exception:
    pass


class _SavedPosition:
  """NavigationOwner's runtime source without live subscribers here: place search uses its saved last position, and
  the snapshot select()/clear() return has no live route (the bridge reads the destination itself)."""
  def search_position(self):
    return None

  def map_position(self):
    return None

  def network_status(self):
    return "unknown"

  def snapshot(self):
    return None


class NavDestinations:
  """StarPilot 7's destination, through its navigation owner (starpilot/navigation/owner.py), like Galaxy sets it."""

  def __init__(self, owner=None):
    self._owner = owner

  @property
  def owner(self):
    if self._owner is None:
      from openpilot.starpilot.navigation.owner import NavigationOwner
      self._owner = NavigationOwner(runtime_source=_SavedPosition())
    return self._owner

  def current(self) -> dict | None:
    return self.owner.read().get("destination")

  def _change(self, fn):
    from openpilot.starpilot.navigation.owner import ConflictError
    for _ in range(3):   # someone else (Galaxy, the comma's screen) changed navigation in between: read again
      try:
        return fn(self.owner.read()["revision"])
      except ConflictError:
        continue
    raise RuntimeError("navigation kept changing")

  def set(self, name: str, address: str, lat: float, lon: float) -> dict:
    value = {"name": name, "latitude": lat, "longitude": lon}
    if address:
      value["address"] = address
    self._change(lambda rev: self.owner.select(value, rev, True))
    return self.owner.read()["destination"]

  def clear_if(self, dest_id: str) -> bool:
    cur = self.current()
    if not cur or cur.get("id") != dest_id:
      return False
    self._change(lambda rev: self.owner.clear(rev, True))
    return True

  def geocode(self, text: str) -> tuple[float, float, str] | None:
    """(lon, lat, label) of the best match for an address (Mapbox search with 7.0's key and usage budget)."""
    hits = self.owner.search(text[:256])
    if not hits:
      return None
    h = hits[0]
    return h["longitude"], h["latitude"], h.get("address") or h["name"]

  def position(self) -> dict | None:
    try:
      return self.owner.position_store.read()
    except Exception:
      return None


# ------------------------------------------------------------------ starviewd side
class WazeFeed:
  """Receives tablet snapshots: parses, keeps the latest for the comparison, follows Waze's destination."""

  def __init__(self, nav_state=None, dest: NavDestinations | None = None):
    self.nav_state = nav_state or (lambda: None)   # () -> StarPilot's NavInstructionState without waze fields
    self.dest = dest or NavDestinations()
    self._lock = threading.Lock()
    self._last_hash = ""
    self._last_log = float("-inf")  # monotonic
    self._last: dict[str, Any] = {}
    self._count = 0
    # current Waze route
    self.route_dest = ""          # destination text read for the route Waze is on now (kept after the sheet closes)
    self.route_label = ""
    self._handled_dest = ""       # destination already handed to StarPilot
    self._geocode_inflight = False
    self._geocode_failed_at = float("-inf")  # monotonic
    self._geocode_failed_for = ""
    self._retry_s = GEOCODE_RETRY_S
    self._not_nav_since: float | None = None
    self.last_handoff = ""
    self._tablet_route = False    # the destination came from the tablet's own search, with exact coordinates
    self._tablet_set_at = float("-inf")  # monotonic
    self._disagree_since: float | None = None
    self._disagree_logged_at = 0.0

  def ingest(self, snap: dict[str, Any]) -> dict[str, Any]:
    now = _wall()
    mono = time.monotonic()
    parsed = waze_parser.parse(snap)
    off = os.path.exists(OFF_FLAG)
    nav_state = None
    try:
      nav_state = self.nav_state()
      if not off:
        self._route_tracking(parsed)
      if snap.get("record"):
        self._record(snap, parsed, now, mono, nav_state)
    except Exception as e:
      parsed["error"] = str(e)[:200]
    if parsed.get("navigating") and not parsed.get("destination") and self.route_dest:
      parsed["destination"], parsed["destinationLabel"] = self.route_dest, self.route_label
      parsed["via"].append("destination:remembered")
    state = {"receivedAt": now, "receivedMono": mono, "tabletT": snap.get("t"), "app": snap.get("app", ""), "parsed": parsed}
    _atomic_write(STATE_PATH, json.dumps(state))
    cmp = waze_parser.compare(parsed, nav_state if isinstance(nav_state, dict) else None)
    need = bool(parsed.get("navigating")) and not self.route_dest and not off
    with self._lock:
      self._count += 1
      self._last = {"at": now, "parsed": parsed, "compare": cmp, "count": self._count, "handoff": self.last_handoff}
    return {"ok": True, "parsed": parsed, "compare": cmp, "off": off, "needDestination": need, "handoff": self.last_handoff}

  # ---- the comparison, merged into the tablet's NavInstructionState
  def fields(self, nav_state: dict[str, Any] | None) -> dict[str, Any]:
    st = load_state() if not os.path.exists(OFF_FLAG) else None
    if st is None or not isinstance(nav_state, dict):
      self._disagree_since = None
      return {"wazeFresh": False}
    res = waze_parser.compare(st.get("parsed") or {}, nav_state)
    res["wazeFresh"] = True
    now = time.monotonic()
    if res["wazeAgree"] is False:
      self._disagree_since = self._disagree_since or now
      if now - self._disagree_since > DISAGREE_LOG_S and now - self._disagree_logged_at > DISAGREE_LOG_S:
        self._disagree_logged_at = now
        sp = f"starpilot {nav_state.get('maneuverPrimaryText')!r} {float(nav_state.get('maneuverDistance') or 0):.0f} m"
        _warn(f"disagree {now - self._disagree_since:.0f}s: waze {res['wazeStreet']!r} {res['wazeDistance']} m vs {sp}")
    else:
      self._disagree_since = None
    res["wazeDisagreeS"] = round(now - self._disagree_since, 1) if self._disagree_since else 0.0
    return res

  # ---- destination handoff
  def _route_tracking(self, parsed: dict[str, Any]) -> None:
    if not parsed.get("present"):
      return                                   # Waze not on screen: no news, keep everything
    now = time.monotonic()
    if parsed.get("navigating") or parsed.get("sheetOpen"):
      self._not_nav_since = None
      dest = str(parsed.get("destination") or "").strip()
      if dest and dest != self.route_dest:
        self.route_dest, self.route_label = dest, str(parsed.get("destinationLabel") or "")
      dest = dest or self.route_dest          # the sheet is closed again: keep trying with what was read
      if dest and dest != self._handled_dest and not self._tablet_route and not self._geocode_inflight and \
         not (dest == self._geocode_failed_for and time.monotonic() - self._geocode_failed_at < self._retry_s):
        self._start_geocode(dest)
      return
    self._not_nav_since = self._not_nav_since or now
    if now - self._not_nav_since < END_CLEAR_S or now - self._tablet_set_at < TABLET_GRACE_S:
      return
    ours = _read_json(OUR_DEST_PATH)
    if isinstance(ours, dict) and ours.get("id"):
      try:
        if self.dest.clear_if(ours["id"]):
          self.last_handoff = "Waze route ended: destination cleared"
          _warn(self.last_handoff)
      except Exception as e:
        _warn(f"clearing the destination: {e}")
    if self.route_dest or self._handled_dest:
      self.route_dest = self.route_label = self._handled_dest = ""
      self._tablet_route = False
      self.last_handoff = ""
      try:
        os.unlink(OUR_DEST_PATH)
      except OSError:
        pass
    self._not_nav_since = None

  def _start_geocode(self, text: str) -> None:
    self._geocode_inflight = True

    def worker():
      try:
        hit = self.dest.geocode(text)
        if hit is None:
          self._geocode_failed_at, self._geocode_failed_for, self._retry_s = time.monotonic(), text, GEOCODE_RETRY_S
          self.last_handoff = f"could not find {text!r}"
          _warn(self.last_handoff)
          return
        lon, lat, name = hit
        cur = self.dest.current()
        if cur and abs(cur["latitude"] - lat) < 1e-4 and abs(cur["longitude"] - lon) < 1e-4:
          dest = cur                     # already StarPilot's destination (set on the comma or in Galaxy)
        else:
          dest = self.dest.set(self.route_label or name, name if self.route_label else "", lat, lon)
        _atomic_write(OUR_DEST_PATH, json.dumps(dest))
        self._handled_dest = text
        label = f"{self.route_label}: {name}" if self.route_label else name
        self.last_handoff = f"destination set: {label}"
        _warn(f"{self.last_handoff} ({lat:.5f},{lon:.5f})")
      except Exception as e:
        # network trouble (no internet yet, DNS) or no Mapbox key: retry soon; never show a URL (it carries the token)
        self._geocode_failed_at, self._geocode_failed_for, self._retry_s = time.monotonic(), text, NET_RETRY_S
        msg = str(e)
        if "token" in msg.lower():
          why = "no Mapbox key on the comma (Galaxy > Navigation)"
        elif "respond" in msg or "complete this request" in msg:
          why = "can't reach Mapbox (no internet?)"
        else:
          why = type(e).__name__
        self.last_handoff = f"{why}: retrying in {int(NET_RETRY_S)} s"
        _warn(f"geocode {text!r}: {why}")
      finally:
        self._geocode_inflight = False

    threading.Thread(target=worker, daemon=True).start()

  def set_tablet_destination(self, name: str, address: str, lat: float, lon: float) -> dict[str, Any]:
    """StarView's destination search: the place picked on the tablet (which also starts Waze on it), set with its exact
    coordinates. Cleared again like one read from Waze when Waze's route ends."""
    name, address = (name or "").strip(), (address or "").strip()
    if not (math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0) or not (name or address):
      return {"ok": False, "error": "bad destination"}
    try:
      dest = self.dest.set(name or address, address if name else "", lat, lon)
    except Exception as e:
      return {"ok": False, "error": str(e)[:200]}
    _atomic_write(OUR_DEST_PATH, json.dumps(dest))
    self.route_dest, self.route_label = (address or name), (name if address and name != address else "")
    self._handled_dest = self.route_dest
    self._tablet_route, self._tablet_set_at, self._not_nav_since = True, time.monotonic(), None
    label = name if not address or address == name else (f"{name}: {address}" if name else address)
    self.last_handoff = f"destination from StarView: {label}"
    _warn(f"{self.last_handoff} ({lat:.5f},{lon:.5f})")
    return {"ok": True, "destination": dest}

  def status(self) -> dict[str, Any]:
    with self._lock:
      return dict(self._last)

  def _record(self, snap, parsed, now, mono, nav_state) -> None:
    nodes_hash = hashlib.sha1(json.dumps(snap.get("nodes") or [], sort_keys=True).encode()).hexdigest()[:16]
    shot = snap.get("shot")
    if nodes_hash == self._last_hash and mono - self._last_log < 10.0 and not shot:
      return
    self._last_hash, self._last_log = nodes_hash, mono
    os.makedirs(LOG_DIR, exist_ok=True)
    day = time.strftime("%Y%m%d", time.localtime(now))
    try:
      dest = self.dest.current()
    except Exception:
      dest = None
    rec = {"t": now, "hash": nodes_hash, "snap": {k: v for k, v in snap.items() if k != "shot"}, "parsed": parsed,
           "gps": self.dest.position(), "navState": nav_state, "navDestination": dest}
    if shot:
      try:
        os.makedirs(f"{LOG_DIR}/shots", exist_ok=True)
        name = f"shots/{int(now * 1000)}.jpg"
        with open(f"{LOG_DIR}/{name}", "wb") as f:
          f.write(base64.b64decode(shot))
        rec["shot"] = name
      except Exception:
        pass
    with open(f"{LOG_DIR}/waze-{day}.jsonl", "a") as f:
      f.write(json.dumps(rec) + "\n")
    self._trim()

  def _trim(self) -> None:
    files = []
    for root, _, names in os.walk(LOG_DIR):
      for n in names:
        p = os.path.join(root, n)
        try:
          st = os.stat(p)
          files.append((st.st_mtime, st.st_size, p))
        except OSError:
          pass
    total = sum(f[1] for f in files)
    for _, size, p in sorted(files):
      if total <= LOG_CAP_BYTES:
        break
      try:
        os.unlink(p)
        total -= size
      except OSError:
        pass


def load_state(max_age: float = FRESH_S) -> dict[str, Any] | None:
  try:
    with open(STATE_PATH) as f:
      st = json.load(f)
  except Exception:
    return None
  if "receivedMono" not in st or time.monotonic() - float(st["receivedMono"]) > max_age:
    return None
  return st
