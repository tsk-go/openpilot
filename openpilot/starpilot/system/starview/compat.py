"""StarView on StarPilot 7.0: the tablet keeps its wire format.

The tablet decodes raw log.Event bytes with the schema it was built with. 7.0 (a rebase on openpilot master) renamed
services but kept their Event ordinals and field layouts, so the old reader decodes the new bytes as they are; only
the name the tablet asks for differs (roadCameraState is narrowRoadCameraState now, liveCalibration is
extrinsicsCalibration, ...). starviewd subscribes to the 7.0 name and delivers it under the tablet's name.

What 7.0 removed is rebuilt here, from what replaced it:
  starpilotPlan        Event @113 is CustomReserved6 now: the old starpilotPlan's first 27 fields, layout frozen for
                       replays. Filled from slcState (speed limits, curve speed, conditional mode) and
                       starpilotLongitudinalPlan (forced stop), with a small starpilotToggles document.
  memory params        7.0 has none. CEStatus, NavInstructionState and SwitchbackModeEnabled come from slcState and
                       starpilotNavigation; the few the tablet writes are kept here (in this process only).
  IsOnroad             gone: not IsOffroad.
"""
from __future__ import annotations

import json
import math
import threading
import time

from openpilot.cereal import messaging
from openpilot.cereal.services import SERVICE_LIST
from openpilot.common.swaglog import cloudlog

# tablet's service name -> 7.0 service (same Event ordinal, same layout: checked field by field against both schemas)
RENAMED = {
  "roadCameraState": "narrowRoadCameraState",
  "roadEncodeIdx": "narrowRoadEncodeIdx",
  "roadEncodeData": "narrowRoadEncodeData",
  "qRoadEncodeData": "qNarrowRoadEncodeData",
  "driverCameraState": "cabinCameraState",
  "driverEncodeIdx": "cabinEncodeIdx",
  "driverEncodeData": "cabinEncodeData",
  "livestreamRoadEncodeIdx": "livestreamNarrowRoadEncodeIdx",
  "livestreamRoadEncodeData": "livestreamNarrowRoadEncodeData",
  "livestreamDriverEncodeIdx": "livestreamCabinEncodeIdx",
  "livestreamDriverEncodeData": "livestreamCabinEncodeData",
  "liveCalibration": "extrinsicsCalibration",
  "liveParameters": "vehicleParameters",
  "liveTorqueParameters": "lateralTorqueParameters",
  "livePose": "deviceMotion",
  "liveTracks": "radarTracks",
  "liveDelay": "lateralDelay",
  "androidLog": "operatingSystemLog",
}

# built from other services (tablet name -> the 7.0 services it is made from)
BUILT = {
  "starpilotPlan": ("slcState", "starpilotLongitudinalPlan"),
}

# 7.0 services whose Event ordinal used to hold something else: never deliver them under their own name to an old
# tablet (it would decode starpilotLongitudinalPlan as starpilotDeviceState)
NOT_FOR_OLD_TABLETS = {"starpilotLongitudinalPlan", "customReserved5", "customReserved6", "starpilotNavigation",
                       "autoSteeringLearning", "slcVisionObservation", "chestnutGpuState"}


def known(name: str) -> bool:
  """The tablet may subscribe to this name."""
  if name in BUILT:
    return True
  if name in NOT_FOR_OLD_TABLETS:
    return False
  return name in SERVICE_LIST or RENAMED.get(name) in SERVICE_LIST


def sources(name: str) -> tuple[str, ...]:
  """7.0 services to read for the tablet's `name`."""
  if name in BUILT:
    return tuple(s for s in BUILT[name] if s in SERVICE_LIST)
  if name in SERVICE_LIST and name not in NOT_FOR_OLD_TABLETS:
    return (name,)
  new = RENAMED.get(name)
  return (new,) if new in SERVICE_LIST else ()


def frequency(name: str) -> float:
  for s in sources(name):
    return SERVICE_LIST[s].frequency
  return 0.0


def tablet_services() -> dict[str, float]:
  """hello's service list, in the tablet's names."""
  out = {k: SERVICE_LIST[k].frequency for k in SERVICE_LIST if k not in NOT_FOR_OLD_TABLETS}
  for old, new in RENAMED.items():
    if new in SERVICE_LIST:
      out[old] = SERVICE_LIST[new].frequency
  for old in BUILT:
    out[old] = frequency(old)
  return out


def is_onroad(params) -> bool:
  try:
    return not params.get_bool("IsOffroad")
  except Exception:
    return False


def _f(v, default=0.0):
  try:
    v = float(v)
    return v if math.isfinite(v) else default
  except (TypeError, ValueError):
    return default


class Translator:
  """Raw 7.0 messages in, (tablet name, raw bytes) out. Runs on starviewd's reader thread."""

  PLAN_MIN_DT = 0.05   # starpilotPlan at most 20 Hz (slcState's rate)
  TOGGLES_EVERY = 2.0

  def __init__(self, params=None, toggles=None):
    self.params = params
    self._toggles_fn = toggles or (dict)
    self.by_source: dict[str, list[str]] = {}
    self._slc = None          # newest slcState (reader)
    self._lp = None           # newest starpilotLongitudinalPlan (reader)
    self._plan_t = 0.0
    self._toggles = "{}"
    self._toggles_t = -1e9
    self.lock = threading.Lock()

  def route(self, wanted: set[str]) -> set[str]:
    """Which 7.0 services to open for the tablet names in `wanted`; remembers how to map them back."""
    by_source: dict[str, list[str]] = {}
    for name in wanted:
      for s in sources(name):
        by_source.setdefault(s, []).append(name)
    with self.lock:
      self.by_source = by_source
    return set(by_source)

  def feed(self, service: str, msgs: list[bytes], now: float) -> list[tuple[str, list[bytes]]]:
    with self.lock:
      names = list(self.by_source.get(service, ()))
    out = []
    for name in names:
      if name in BUILT:
        built = self._build(name, service, msgs[-1], now)
        if built is not None:
          out.append((name, [built]))
      else:
        out.append((name, msgs))
    return out

  # ---- starpilotPlan ----
  def _build(self, name, service, raw, now):
    try:
      evt = messaging.log_from_bytes(raw)
      if service == "slcState":
        self._slc = evt.slcState
      elif service == "starpilotLongitudinalPlan":
        self._lp = evt.starpilotLongitudinalPlan
        return None   # sent with the next slcState
    except Exception as e:
      cloudlog.warning(f"starview compat: {service} unreadable: {e}")
      return None
    if name != "starpilotPlan" or now - self._plan_t < self.PLAN_MIN_DT:
      return None
    self._plan_t = now
    if now - self._toggles_t >= self.TOGGLES_EVERY:
      self._toggles_t = now
      try:
        self._toggles = json.dumps(self._toggles_fn())
      except Exception:
        self._toggles = "{}"
    return build_plan(self._slc, self._lp, self._toggles)


def build_plan(slc, lp, toggles_json: str) -> bytes:
  """An old-layout starpilotPlan (7.0's customReserved6) from slcState + starpilotLongitudinalPlan."""
  msg = messaging.new_message("customReserved6", valid=True)
  p = msg.customReserved6
  p.starpilotToggles = toggles_json
  if slc is not None:
    try:
      if slc.hasAccepted:
        p.slcSpeedLimit = _f(slc.acceptedSpeedLimit)
      elif str(slc.observationKind) == "valid":
        p.slcSpeedLimit = _f(slc.speedLimit)
      p.slcSpeedLimitOffset = _f(slc.offset)
      p.slcSpeedLimitSource = str(slc.acceptedSource or slc.source or "")
      if slc.hasPending:
        p.slcNextSpeedLimit = _f(slc.pendingSpeedLimit)
      if slc.driverOverrideActive and slc.hasCeiling:
        p.slcOverriddenSpeed = _f(slc.effectiveCap)
      c = slc.curve
      if c.hasCeiling:
        p.cscSpeed = _f(c.ceilingMps)
      p.cscTraining = bool(c.training)
      p.cscControllingSpeed = bool(c.controlling)
      if c.hasRoadCurvature:
        p.roadCurvature = _f(c.roadCurvature)
      p.experimentalMode = bool(slc.conditionalMode.experimental)
    except Exception as e:
      cloudlog.warning(f"starview compat: slcState fields: {e}")
  if lp is not None:
    try:
      p.forcingStop = bool(lp.forceStopHolding)
    except Exception:
      pass
  return msg.to_bytes()


# ------------------------------------------------------------------------------------------ memory params
NO_SOURCE = object()   # MemParams.source: "not replaying, read msgq"


class MemParams:
  """The old in-memory params the tablet reads and writes. Read: built from 7.0 messages (one conflated socket each,
  made on first use and kept). Write: kept in this process (only the tablet itself reads them back)."""

  READ_EVERY = 0.5

  def __init__(self):
    self._socks = {}
    self._last = {}
    self._read_t = {}
    self._local: dict[str, object] = {}
    self.lock = threading.Lock()
    self.nav_extra = None     # callable(base state) -> dict merged into NavInstructionState (the Waze bridge's fields)
    # callable(service) -> (time, event) | None, or NO_SOURCE: while a drive replay plays, its messages (or nothing)
    # instead of msgq's live ones
    self.source = None

  def _newest(self, service):
    if service not in SERVICE_LIST:
      return None
    if self.source is not None:
      try:
        got = self.source(service)
      except Exception:
        got = None
      if got is not NO_SOURCE:
        return got
    now = time.monotonic()
    with self.lock:   # executor threads and the snapshot share these sockets: one reader at a time
      if now - self._read_t.get(service, -1e9) >= self.READ_EVERY:
        self._read_t[service] = now
        sock = self._socks.get(service)
        if sock is None:
          sock = self._socks[service] = messaging.sub_sock(service, conflate=True)
        try:
          m = messaging.recv_one_or_none(sock)
        except Exception:
          m = None
        if m is not None:
          self._last[service] = (now, m)
      got = self._last.get(service)
    return got if got is not None and now - got[0] < 5.0 else None

  def _slc(self):
    m = self._newest("slcState")
    return m[1].slcState if m else None

  def get(self, key, *_a, default=None, **_k):
    if key in self._local:
      return self._local[key]
    if key == "CEStatus":
      s = self._slc()
      return int(s.conditionalMode.statusCode) if s is not None else default
    if key == "SwitchbackModeEnabled":
      s = self._slc()
      return bool(s.switchbackMode.effective) if s is not None else default
    if key == "NavInstructionState":
      return self.nav_state()
    return default

  def get_bool(self, key, *_a, **_k):
    return bool(self.get(key, default=False))

  def get_int(self, key, *_a, default=0, **_k):
    v = self.get(key, default=default)
    try:
      return int(v)
    except (TypeError, ValueError):
      return default

  def put(self, key, val, *_a, **_k):
    self._local[key] = val

  put_bool = put_int = put_nonblocking = put_bool_nonblocking = put

  def remove(self, key):
    self._local.pop(key, None)

  def nav_base(self):
    """StarPilot's turn instruction in the old NavInstructionState form (no Waze fields)."""
    m = self._newest("starpilotNavigation")
    return nav_instruction_state(m[1].starpilotNavigation.navigation) if m is not None else None

  def nav_state(self):
    base = self.nav_base()
    if base is not None and self.nav_extra is not None:
      try:
        base.update(self.nav_extra(base))
      except Exception as e:
        cloudlog.warning(f"starview compat: waze fields: {e}")
    return base


def nav_instruction_state(nav, extra=None):
  """7.0's starpilotNavigation -> the old NavInstructionState JSON (what the tablet's turn card and turn signals read)."""
  try:
    if nav.version != 2 or not nav.enabled or str(nav.status) != "guiding" or not nav.instruction.text:
      return None
    i, n = nav.instruction, nav.nextManeuver
    state = {
      "valid": True,
      "updatedAtMonotonic": nav.frameMonoTime / 1e9,
      "maneuverType": str(i.maneuverType),
      "maneuverModifier": str(i.maneuverModifier),
      "maneuverPrimaryText": str(i.text),
      "maneuverSecondaryText": "",
      "maneuverDistance": _f(i.distanceMeters),
      "nextManeuverType": str(n.maneuverType),
      "nextManeuverModifier": str(n.maneuverModifier),
      "nextManeuverDistance": _f(n.distanceMeters),
      "distanceRemaining": _f(i.remainingDistanceMeters),
      "timeRemaining": _f(i.remainingDurationSeconds),
      "destination": str(nav.destinationName),
    }
    if extra:
      state.update(extra)
    return state
  except Exception:
    return None
